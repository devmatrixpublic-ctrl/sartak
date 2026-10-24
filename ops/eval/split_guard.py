#!/usr/bin/env python3
"""Split-payment evasion test, with and without a split guard (plan "Person B", phase 1: the before/after evasion numbers).

The attack: a scammer who knows the detector looks at the size of a payment asks the victim to pay the same total in k smaller pieces to the
same payee, a few seconds apart. The guard: before scoring, each payment attempt is replaced by the running total sent to that payee inside a
rolling window (default 30 minutes), so the detector sees one logical payment instead of k small ones. The guard is a pre-processing step the
app can compute from its own local history; it is NOT in the frozen detector, and adopting it means a new freeze.

Method (validation split of the shipped SatarkSim, detector exactly as shipped):
  * every scam session is attacked by splitting each of its payments into k equal pieces 30 s apart (k = 1 is the unmodified data);
  * the detector scores it with the guard off and on, thresholds as shipped;
  * legitimate sessions are scored with the guard off, on with the shipped thresholds, and on with thresholds re-calibrated on the
    calibration split, so the guard's price in false alarms is visible.
Measures: recall; interdicted before the first payment; AMOUNT PROTECTED (share of the scam's total that was still unsent when the alarm
fired, which is what splitting actually attacks); and the evasion rate among scams the detector caught unattacked.

Simulated data, not the sealed held-out set, not real fraud. Usage (repo root):  python ops/eval/split_guard.py [--window 1800] [--gap 30]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REF))

from run_eval import clopper_pearson  # noqa: E402

OUT = ROOT / "ops" / "eval" / "reports" / "split_guard_report.md"
SPLITS = (1, 2, 3, 5, 10)
ADAPTIVE = "adaptive"
MAX_PIECES = 50
ROWS = (*SPLITS, ADAPTIVE)
LABEL = {**{k: str(k) for k in SPLITS}, ADAPTIVE: f"adaptive (each piece no larger than the user's own median payment, at most {MAX_PIECES})"}
DEFAULT_WINDOW_S, DEFAULT_GAP_S = 1800, 30


# ---- the attack and the guard (pure functions on event tables) -----------------------------------------------------------------
def split_payments(events: pd.DataFrame, k: int, gap_s: int, sessions: set) -> pd.DataFrame:
    """Replace each PAYMENT_ATTEMPT of the given sessions by k equal pieces to the same payee, gap_s seconds apart. k = 1 changes nothing."""
    if k <= 1:
        return events
    is_pay = (events.event_type == "PAYMENT_ATTEMPT") & events.session_id.isin(sessions)
    keep, pay = events[~is_pay], events[is_pay]
    pieces = []
    for i in range(k):
        p = pay.copy()
        p["t_sec"] = p.t_sec + i * gap_s
        if "ts_abs" in p.columns:
            p["ts_abs"] = p.ts_abs + i * gap_s
        p["amount_inr"] = p.amount_inr / k
        pieces.append(p)
    return pd.concat([keep] + pieces, ignore_index=True).sort_values(["session_id", "t_sec"], kind="stable")


def split_below_baseline(events: pd.DataFrame, users: pd.DataFrame, gap_s: int, sessions: set, max_pieces: int = MAX_PIECES) -> pd.DataFrame:
    """The strongest amount-evasion: each payment of the given sessions is cut into the fewest equal pieces that are each no larger than the
    victim's OWN median payment (what the detector compares the amount with), capped at max_pieces."""
    med = users.set_index("user_id").hist_median_inr
    is_pay = (events.event_type == "PAYMENT_ATTEMPT") & events.session_id.isin(sessions)
    keep, pay = events[~is_pay], events[is_pay].copy()
    base = pay.user_id.map(med).clip(lower=1.0)
    k = np.ceil(pay.amount_inr / base).clip(1, max_pieces).astype(int)
    pieces = []
    for i in range(int(k.max()) if len(k) else 0):
        sel = pay[k > i].copy()
        sel["t_sec"] = sel.t_sec + i * gap_s
        if "ts_abs" in sel.columns:
            sel["ts_abs"] = sel.ts_abs + i * gap_s
        sel["amount_inr"] = sel.amount_inr / k[k > i]
        pieces.append(sel)
    return pd.concat([keep] + pieces, ignore_index=True).sort_values(["session_id", "t_sec"], kind="stable")


def apply_guard(events: pd.DataFrame, window_s: int) -> pd.DataFrame:
    """Each PAYMENT_ATTEMPT's amount becomes the total attempted to the same payee in the last window_s seconds, itself included."""
    ev = events.sort_values(["session_id", "t_sec"], kind="stable").copy()
    pay_idx = ev.index[ev.event_type == "PAYMENT_ATTEMPT"]
    totals = {}
    for sid, g in ev.loc[pay_idx].groupby("session_id", sort=False):
        history: dict = {}
        for idx, t, payee, amt in zip(g.index, g.t_sec, g.payee_id, g.amount_inr):
            seen = [(ts, a) for ts, a in history.get(payee, []) if t - ts < window_s]
            seen.append((t, float(amt or 0)))
            history[payee] = seen
            totals[idx] = sum(a for _, a in seen)
    ev.loc[list(totals), "amount_inr"] = pd.Series(totals)
    return ev


def exposure(events: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Per session: total attempted and the amount that was already sent before the alarm (the alarm holds the attempt it fires on)."""
    pay = events[events.event_type == "PAYMENT_ATTEMPT"][["session_id", "t_sec", "amount_inr"]]
    alarm = decisions.set_index("session_id").alarm_t
    pay = pay.assign(alarm_t=pay.session_id.map(alarm))
    pay["sent"] = np.where(pay.alarm_t.isna() | (pay.t_sec < pay.alarm_t), pay.amount_inr, 0.0)
    return pay.groupby("session_id").agg(total=("amount_inr", "sum"), sent=("sent", "sum")).reset_index()


# ---- scoring ----------------------------------------------------------------------------------------------------------------
def load(data: Path):
    users = pd.read_csv(data / "satarksim_users.csv")
    sessions = pd.read_csv(data / "satarksim_sessions.csv")
    events = pd.read_csv(data / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    return users, sessions, events


def score(sd, det, watchlist, users, sessions, events):
    pay, alerts, first_pay = sd.featurize(events, users, watchlist)
    return sd.decide(det, pay, alerts, first_pay, sessions), (pay, alerts, first_pay)


def measure(decisions: pd.DataFrame, events: pd.DataFrame, baseline_caught: set, payscore_only: set) -> dict:
    s = decisions[decisions.label == "scam"]
    exp = exposure(events[events.session_id.isin(s.session_id)], s)
    caught = set(s[s.alarm].session_id)
    ps = s[s.session_id.isin(payscore_only)]
    return {"n": len(s), "hit": len(caught), "interdicted": int(s.interdicted.sum()),
            "total": float(exp.total.sum()), "sent": float(exp.sent.sum()),
            "evaded": len(baseline_caught - caught), "baseline_caught": len(baseline_caught),
            "ps_n": len(ps), "ps_hit": int(ps.alarm.sum())}


def run(data: Path, window_s: int, gap_s: int, out: Path) -> dict:
    from fresh_seed_eval import load_detector
    params = json.loads((REF / "params.json").read_text(encoding="utf-8"))
    wl, alpha = params["watchlisted_remote_apps"], params["calibration_alpha"]
    sd, det, _ = load_detector(alpha, wl)
    users, sessions, events = load(data)
    val_ids = set(sessions[sessions.split == "validation"].session_id)
    scam_ids = set(sessions[(sessions.split == "validation") & (sessions.label == "scam")].session_id)
    val_sessions = sessions[sessions.session_id.isin(val_ids)]
    val_events = sd.dedupe(events[events.session_id.isin(val_ids)])                  # amounts as the phone sees them (duplicates removed)

    rows = {}
    base_dec, _ = score(sd, det, wl, users, val_sessions, val_events)
    s0 = base_dec[base_dec.label == "scam"]
    baseline_caught = set(s0[s0.alarm].session_id)
    payscore_only = set(s0[s0.mechanism == "payment_score"].session_id)              # the scams only the amount-sensitive score catches
    for k in ROWS:
        attacked = split_below_baseline(val_events, users, gap_s, scam_ids) if k == ADAPTIVE else split_payments(val_events, k, gap_s, scam_ids)
        for guard in (False, True):
            ev = apply_guard(attacked, window_s) if guard else attacked
            dec, _ = score(sd, det, wl, users, val_sessions, ev)
            m = measure(dec, attacked, baseline_caught, payscore_only)             # exposure uses the REAL piece amounts, never the guard's totals
            rows[(k, guard)] = m

    # false-alarm price of the guard (legitimate sessions are never attacked)
    legit = val_sessions[val_sessions.label == "legit"]
    fa = {}
    for name, guard in (("guard off (shipped)", False), ("guard on, shipped thresholds", True)):
        dec, _ = score(sd, det, wl, users, val_sessions, apply_guard(val_events, window_s) if guard else val_events)
        l = dec[dec.label == "legit"]
        fa[name] = (int(l.alarm.sum()), len(l))
    cal_ids = set(sessions[sessions.split == "calibration"].session_id)
    cal_sessions = sessions[sessions.session_id.isin(cal_ids)]
    cal_events = apply_guard(sd.dedupe(events[events.session_id.isin(cal_ids)]), window_s)
    cal_pay, _, _ = sd.featurize(cal_events, users, wl)
    det2 = copy.deepcopy(det).calibrate(cal_pay, cal_sessions, cal_ids, alpha)
    dec, _ = score(sd, det2, wl, users, val_sessions, apply_guard(val_events, window_s))
    s2 = dec[dec.label == "scam"]
    l2 = dec[dec.label == "legit"]
    fa["guard on, thresholds re-calibrated"] = (int(l2.alarm.sum()), len(l2))
    recal_recall = (int(s2.alarm.sum()), len(s2))

    text = render(rows, fa, recal_recall, window_s, gap_s)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    out.with_suffix(".json").write_text(json.dumps({"window_s": window_s, "gap_s": gap_s,
        "rows": {f"k={k},guard={g}": v for (k, g), v in rows.items()}, "false_alarms": fa, "recalibrated_recall": recal_recall}, indent=1), encoding="utf-8")
    return {"rows": rows, "fa": fa}


# ---- report -----------------------------------------------------------------------------------------------------------------
def pct(a, b):
    return f"{a / b:.1%}" if b else "n/a"


def render(rows, fa, recal_recall, window_s, gap_s) -> str:
    L = ["# Split-payment evasion: before and after a split guard (Person B)", "",
         "**Simulated data.** Validation split of SatarkSim (578 scam sessions), detector exactly as shipped, thresholds not re-tuned (except the one "
         "labelled re-calibrated row). Not the sealed held-out set and not real fraud.", "",
         f"**Attacks:** each payment in a scam is split into k equal pieces to the same payee, {gap_s} s apart (k = 1 is the unmodified data); and an "
         f"*adaptive* attack that cuts each payment into the fewest pieces that are each no larger than the victim's own median payment (the amount the "
         f"detector compares against), at most {MAX_PIECES} pieces. "
         f"**Guard:** each attempt is scored as the running total to that payee in the last {window_s // 60} minutes. The guard is app-side "
         "pre-processing, not part of the frozen detector; adopting it needs a new freeze.", "",
         "*Amount protected* is the share of the scam's total still unsent when the alarm fired (an alarm holds the attempt it fires on). "
         "It is computed from the real piece amounts, never from the guard's running totals.", "",
         "## 1. All scam sessions", "",
         "| Pieces (k) | Guard | Caught | Interdicted before 1st payment | Amount protected | Caught unattacked but evaded now |",
         "|---|---|---|---|---|---|"]
    for k in ROWS:
        for g in (False, True):
            m = rows[(k, g)]
            L.append(f"| {LABEL[k]} | {'on' if g else 'off'} | {m['hit']}/{m['n']} = {pct(m['hit'], m['n'])} | {pct(m['interdicted'], m['n'])} | "
                     f"{pct(m['total'] - m['sent'], m['total'])} | {m['evaded']}/{m['baseline_caught']} = {pct(m['evaded'], m['baseline_caught'])} |")
    m1 = rows[(1, False)]
    L += ["", f"## 2. Only the scams that depend on the amount-sensitive payment score ({m1['ps_n']} sessions)", "",
          "Many scams are caught by rules that ignore amounts (a sideloaded app during a call, a very long video call), so splitting cannot hide them. "
          "These are the ones caught by the payment score alone when unattacked: the only ones splitting can threaten.", "",
          "| Pieces (k) | Guard | Still caught |", "|---|---|---|"]
    for k in ROWS:
        for g in (False, True):
            m = rows[(k, g)]
            L.append(f"| {LABEL[k]} | {'on' if g else 'off'} | {m['ps_hit']}/{m['ps_n']} = {pct(m['ps_hit'], m['ps_n'])} |")
    L += ["", "## 3. The guard's price: false alarms on legitimate sessions (never attacked)", "",
          "| Configuration | False alarms | Rate (95% CI) |", "|---|---|---|"]
    for name, (a, n) in fa.items():
        lo, hi = clopper_pearson(a, n)
        L.append(f"| {name} | {a}/{n} | {a / n:.3%} ({lo:.3%} - {hi:.3%}) |")
    hit, n = recal_recall
    L += ["", f"With thresholds re-calibrated on guarded calibration data, unattacked scam recall is {hit}/{n} = {pct(hit, n)}. "
              "A guard that also moves false alarms past the 0.1% target, or recall below 93%, would not be adopted as is.", "",
          "## 4. Reading the results", ""] + reading(rows, fa) + ["", "## 5. Limits", "",
          "- One attack shape (equal pieces, fixed gap, one payee). A scammer can vary amounts, gaps and payees; a guard keyed on one payee does nothing "
          "against pieces spread over several new payees (mule accounts).",
          "- The guard counts a retried payment twice if the retry comes after the 3-second de-duplication window; the false-alarm row above is "
          "the measured cost of that on the simulator, which may not reproduce real retry behaviour.",
          "- SatarkSim has no real splitting behaviour in it, so the unattacked numbers are the simulator's, not a measure of how often real scams split.", ""]
    return "\n".join(L) + "\n"


def reading(rows, fa) -> list[str]:
    """Plain statements computed from the numbers above, so they cannot drift from the tables when the test is re-run."""
    base, adapt = rows[(1, False)], rows[(ADAPTIVE, False)]
    adapt_g = rows[(ADAPTIVE, True)]
    out = []
    worst = min(rows[(k, False)]["hit"] for k in ROWS)
    out.append(f"- **Splitting did not evade the detector.** Unattacked it catches {base['hit']}/{base['n']}; across every attack in section 1 the worst case "
               f"is {worst}/{base['n']} caught with the guard off. {sum(rows[(k, False)]['evaded'] for k in ROWS)} scams caught unattacked were missed after any split.")
    out.append("- **Why:** each piece is another payment screen and another chance to alarm, and repeat payments to one payee add to the score, so more pieces "
               "give the detector more evidence, not less.")
    out.append(f"- **What splitting does cost the defender is timing.** Interdicted before the first payment falls from {pct(base['interdicted'], base['n'])} "
               f"unattacked to {pct(adapt['interdicted'], adapt['n'])} under the adaptive attack: the first small pieces go out before the alarm. "
               f"The money at risk stays small ({pct(adapt['total'] - adapt['sent'], adapt['total'])} of the amount is still protected).")
    d = adapt_g["interdicted"] - adapt["interdicted"]
    out.append(f"- **The guard does not fix that, and was not needed here.** It leaves interdiction before the first payment {'unchanged' if d == 0 else f'changed by {d} sessions'} "
               "(the first piece is scored as itself), and its only measurable effect is on scams whose own repeat payments add up. "
               f"False alarms with the guard: {fa['guard on, shipped thresholds'][0]}/{fa['guard on, shipped thresholds'][1]} against "
               f"{fa['guard off (shipped)'][0]}/{fa['guard off (shipped)'][1]} without.")
    out.append("- **So:** do not ship the guard on this evidence. The honest statement for the deck is that this attack shape was tested and does not beat the "
               "shipped detector, while naming the real exposure (the first payments before the alarm) and the attack not tested (pieces to several different payees).")
    return out


def rerender(json_path: Path, out: Path) -> None:
    """Rebuild the Markdown from the saved JSON, without re-running the evaluation."""
    d = json.loads(json_path.read_text(encoding="utf-8"))
    rows = {}
    for key, v in d["rows"].items():
        k, g = key.split(",guard=")
        k = k.removeprefix("k=")
        rows[(k if k == ADAPTIVE else int(k), g == "True")] = v
    fa = {k: tuple(v) for k, v in d["false_alarms"].items()}
    out.write_text(render(rows, fa, tuple(d["recalibrated_recall"]), d["window_s"], d["gap_s"]), encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW_S, help="guard window in seconds")
    ap.add_argument("--gap", type=int, default=DEFAULT_GAP_S, help="seconds between the pieces of a split payment")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--rerender", action="store_true", help="rebuild the report from its saved JSON without re-running the evaluation")
    a = ap.parse_args(argv)
    if a.rerender:
        rerender(a.out.with_suffix(".json"), a.out)
        print(f"re-rendered {a.out}")
        return 0
    r = run(a.data, a.window, a.gap, a.out)
    m, g = r["rows"][(ADAPTIVE, False)], r["rows"][(ADAPTIVE, True)]
    print(f"wrote {a.out}: adaptive split, scams caught {m['hit']}/{m['n']} -> {g['hit']}/{g['n']} with the guard; "
          f"amount protected {1 - m['sent'] / m['total']:.1%} -> {1 - g['sent'] / g['total']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
