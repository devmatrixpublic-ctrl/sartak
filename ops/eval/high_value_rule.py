"""High-value new-payee rule: what it gains and what it costs, measured on the simulator.

The condition matrix showed two gaps in the payment checks: a payment made shortly AFTER an unknown call has ended was never
checked against the call, and the older age band needed a much higher amount before a hold (Rs 100,000, against Rs 50,000).
The app now also holds a payment to a payee who was new within the last hour (running total, as the split guard) when an
unknown call or video is active, or ended within the last 30 minutes, once the amount reaches a fixed threshold, the same for
every age band (app/.../events/HighValueNewPayee.kt). It only ever adds a hold; "Continue anyway" still lets a person go on.
This file mirrors that rule and measures it against the shipped decisions. The model and its thresholds are untouched.

Measured on simulated data only: extra scams held, and genuine sessions held that were not before (the cost), for several
thresholds so the chosen one is a visible choice, not a hidden one.

Usage (repo root):  python ops/eval/high_value_rule.py [--data data/satarksim] [--out ops/eval/reports]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from alert_budget import wilson  # noqa: E402
from split_guard_app import apply_guard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
RECENT_S = 30 * 60                       # same as HighValueNewPayee.RECENT_MS
THRESHOLDS = (10_000, 20_000, 25_000, 30_000, 50_000)
CHOSEN = 25_000
YOUNG_INR = 10_000                       # HighValueNewPayee.YOUNG_THRESHOLD_INR, for a person who says they are under 22
YOUNG_BAND = "18-35"                     # the simulator has age bands only, so "under 22" is bounded by the whole band


def unknown_contact_state(ev: pd.DataFrame) -> pd.DataFrame:
    """For every row: is an unknown call/video open, and when did the last one end (seconds, NaN if none)."""
    ev = ev.sort_values(["session_id", "t_sec"], kind="stable").reset_index(drop=True)
    active = np.zeros(len(ev), dtype=bool)
    last_end = np.full(len(ev), np.nan)
    sid, kind, known = ev.session_id.to_numpy(), ev.event_type.to_numpy(), ev.caller_known.to_numpy()
    t = ev.t_sec.to_numpy(dtype=float)
    cur, open_unknown, end_t = None, False, np.nan
    for i in range(len(ev)):
        if sid[i] != cur:
            cur, open_unknown, end_t = sid[i], False, np.nan
        k = kind[i]
        if k in ("CALL_START", "VIDEO_SESSION_START") and known[i] in (False, "False"):
            open_unknown = True
        elif k in ("CALL_END", "VIDEO_SESSION_END") and open_unknown:
            open_unknown, end_t = False, t[i]
        active[i], last_end[i] = open_unknown, end_t
    ev["unknown_active"], ev["unknown_ended_at"] = active, last_end
    return ev


def fires(ev: pd.DataFrame, threshold: float) -> pd.Series:
    """Session id -> time of the first payment the rule would hold (NaN when none)."""
    g = apply_guard(ev).sort_values(["session_id", "t_sec"], kind="stable").reset_index(drop=True)
    s = unknown_contact_state(ev).sort_values(["session_id", "t_sec"], kind="stable").reset_index(drop=True)
    pay = (g.event_type == "PAYMENT_ATTEMPT") & g.payee_is_new.map(lambda v: v is True or v == "True") & (g.amount_inr.astype(float) >= threshold)
    recent = s.unknown_active | (s.t_sec.astype(float) - s.unknown_ended_at <= RECENT_S)
    hit = g[pay & recent.fillna(False)]
    return hit.groupby("session_id").t_sec.min()


def run(data: Path, alpha: float) -> dict:
    sys.path.insert(0, str(REF))
    import satark_detector as sd

    params = json.loads((REF / "params.json").read_text())
    det, res, (users, sessions, events, pay, alerts, first_pay) = sd.evaluate(data, alpha, params["watchlisted_remote_apps"])
    val_ids = set(sessions[sessions.split == "validation"].session_id)
    ev = events[events.session_id.isin(val_ids)]
    base = res[res.session_id.isin(val_ids)].set_index("session_id")
    rows = []
    for th in THRESHOLDS:
        f = fires(ev, th)
        add = base.index.isin(f.index) & ~base.alarm.to_numpy()
        scam, legit = base.label.to_numpy() == "scam", base.label.to_numpy() == "legit"
        s_new, l_new = int((add & scam).sum()), int((add & legit).sum())
        n_s, n_l = int(scam.sum()), int(legit.sum())
        rows.append({
            "threshold_inr": th, "scam_sessions": n_s, "scams_held_before": int(base.alarm[scam].sum()), "extra_scams_held": s_new,
            "recall_after": float((base.alarm[scam].sum() + s_new) / n_s),
            "legit_sessions": n_l, "false_alarms_before": int(base.alarm[legit].sum()), "extra_false_alarms": l_new,
            "false_alarm_rate_after": float((base.alarm[legit].sum() + l_new) / n_l),
            "false_alarm_ci95_after": wilson(int(base.alarm[legit].sum() + l_new), n_l),
        })
    # Under-22 policy. The simulator has no exact ages, only bands, so the whole 18-35 band is held from YOUNG_INR: an upper bound
    # on the cost (and on the gain), because the real group, people under 22, is smaller than that band.
    band = sessions.set_index("session_id").age_band.reindex(base.index)
    in_band = (band == YOUNG_BAND).to_numpy()
    f_low, f_high = fires(ev, YOUNG_INR), fires(ev, CHOSEN)
    held = (in_band & base.index.isin(f_low.index)) | (~in_band & base.index.isin(f_high.index))
    add = held & ~base.alarm.to_numpy()
    scam, legit = base.label.to_numpy() == "scam", base.label.to_numpy() == "legit"
    n_s, n_l = int(scam.sum()), int(legit.sum())
    s_new, l_new = int((add & scam).sum()), int((add & legit).sum())
    only_high_add = base.index.isin(f_high.index) & ~base.alarm.to_numpy()
    young = {
        "young_inr": YOUNG_INR, "other_inr": CHOSEN, "band": YOUNG_BAND,
        "scam_sessions_in_band": int((in_band & scam).sum()), "legit_sessions_in_band": int((in_band & legit).sum()),
        "extra_scams_held": s_new, "extra_scams_held_single_threshold": int((only_high_add & scam).sum()),
        "recall_after": float((base.alarm[scam].sum() + s_new) / n_s),
        "extra_false_alarms": l_new, "extra_false_alarms_single_threshold": int((only_high_add & legit).sum()),
        "false_alarm_rate_after": float((base.alarm[legit].sum() + l_new) / n_l),
        "false_alarm_ci95_after": wilson(int(base.alarm[legit].sum() + l_new), n_l),
    }
    return {"alpha": alpha, "chosen_inr": CHOSEN, "rows": rows, "young": young}


def render(m: dict) -> str:
    pct = lambda x: f"{100 * x:.3f}%"  # noqa: E731
    lines = []
    for r in m["rows"]:
        mark = " (chosen)" if r["threshold_inr"] == m["chosen_inr"] else ""
        lo, hi = r["false_alarm_ci95_after"]
        lines.append(f"| Rs {r['threshold_inr']:,}{mark} | {r['extra_scams_held']} | {pct(r['recall_after'])} | {r['extra_false_alarms']} | "
                     f"{pct(r['false_alarm_rate_after'])} ({pct(lo)} to {pct(hi)}) |")
    r0 = m["rows"][0]
    y = m["young"]
    ylo, yhi = y["false_alarm_ci95_after"]
    return f"""# High-value new-payee rule

**Simulated data only (SatarkSim, validation split).** The rule holds a payment to a payee who was new within the last hour
(running total) when an unknown call or video is open, or ended within 30 minutes, and the amount reaches the threshold. It is the
same for every age band and only adds holds. Today: {r0['scams_held_before']}/{r0['scam_sessions']} scams held and
{r0['false_alarms_before']}/{r0['legit_sessions']} genuine sessions held. The deck's target for false alarms is 0.100%.

| Threshold | Extra scams held | Scam recall after | Extra genuine sessions held | False-alarm rate after (95% interval) |
|---|---|---|---|---|
{chr(10).join(lines)}

## Lower amount for people under 22

The app asks for an optional age. A person who says they are under 22 is held from Rs {y['young_inr']:,} instead of Rs {y['other_inr']:,}.
The simulator has age bands, not exact ages, so this measures the whole {y['band']} band at Rs {y['young_inr']:,} and everyone else at
Rs {y['other_inr']:,}. Under-22s are only part of that band, so these figures are an **upper bound** on both the gain and the cost.

| Policy | Extra scams held | Scam recall after | Extra genuine sessions held | False-alarm rate after (95% interval) |
|---|---|---|---|---|
| One amount, Rs {y['other_inr']:,} for everyone | {y['extra_scams_held_single_threshold']} | {pct(r0['scams_held_before'] / r0['scam_sessions'] + y['extra_scams_held_single_threshold'] / r0['scam_sessions'])} | {y['extra_false_alarms_single_threshold']} | {pct(r0['false_alarms_before'] / r0['legit_sessions'] + y['extra_false_alarms_single_threshold'] / r0['legit_sessions'])} |
| Rs {y['young_inr']:,} for the {y['band']} band, Rs {y['other_inr']:,} for the rest (upper bound) | {y['extra_scams_held']} | {pct(y['recall_after'])} | {y['extra_false_alarms']} | {pct(y['false_alarm_rate_after'])} ({pct(ylo)} to {pct(yhi)}) |

The {y['band']} band holds {y['scam_sessions_in_band']} of the scam sessions and {y['legit_sessions_in_band']} of the genuine ones.

Read it as a trade: a lower threshold holds more scams and more genuine payments. A held genuine payment is not lost, because the
person can choose "Continue anyway", but it is friction and it counts against the alert budget.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    alpha = a.alpha if a.alpha is not None else json.loads((REF / "params.json").read_text())["calibration_alpha"]
    m = run(a.data, alpha)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "high_value_rule.md").write_text(render(m), encoding="utf-8", newline="\n")
    (a.out / "high_value_rule.json").write_text(json.dumps(m, indent=2, default=float), encoding="utf-8")
    print(render(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
