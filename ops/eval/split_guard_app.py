"""Split-payment guard: what it gains and what it costs, measured on the simulator.

The AI-variants test showed that paying a new payee in several smaller pieces evaded the detector completely (0 of 90),
because each payment is scored alone. The app now also shows a second copy of the same model the running total paid to a
payee who was new within the last hour (app/.../events/CumulativeNewPayee.kt and SplitGuard.kt), and raises an alarm if either
copy does. This file mirrors that rule and measures it. The model and thresholds are untouched.

Measured here, on simulated data:
  1. the whole SatarkSim validation split, before and after: scam recall and the false-alarm rate (thresholds were calibrated
     WITHOUT the guard, so any added false alarms are a real cost, not hidden by recalibration);
  2. the AI-style variants, before and after.

Usage (repo root):  python ops/eval/split_guard_app.py [--data data/satarksim] [--out ops/eval/reports]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import ai_variants as av  # noqa: E402
from alert_budget import wilson  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
WINDOW_S = 3600   # same as CumulativeNewPayee.WINDOW_MS
RETRY_S = 120     # same as CumulativeNewPayee.RETRY_MS


def apply_guard(ev: pd.DataFrame) -> pd.DataFrame:
    """Mirror of CumulativeNewPayee, applied per session in time order. Returns a copy with the running total shown."""
    ev = ev.sort_values(["session_id", "t_sec"], kind="stable").reset_index(drop=True).copy()
    amount = ev.amount_inr.to_numpy(dtype=float, copy=True)
    is_new = ev.payee_is_new.to_numpy(dtype=object, copy=True)
    payee, etype, sid, t = ev.payee_id.to_numpy(object), ev.event_type.to_numpy(object), ev.session_id.to_numpy(object), ev.t_sec.to_numpy()
    tally: dict[str, list] = {}
    cur = None
    for i in range(len(ev)):
        if sid[i] != cur:
            cur, tally = sid[i], {}
        if etype[i] != "PAYMENT_ATTEMPT" or payee[i] is None or (isinstance(payee[i], float) and np.isnan(payee[i])):
            continue
        a = amount[i]
        if not np.isfinite(a) or a < 0:
            continue
        tr = tally.get(payee[i])
        if tr is None or t[i] - tr[0] > WINDOW_S:
            if is_new[i] is True or is_new[i] == "True":
                tally[payee[i]] = [t[i], a, a, t[i]]      # first time, total, last amount, last time
            else:
                tally.pop(payee[i], None)
            continue
        retry = a == tr[2] and t[i] - tr[3] <= RETRY_S
        if not retry:
            tr[1] += a
        tr[2], tr[3] = a, t[i]
        amount[i], is_new[i] = tr[1], True
    ev["amount_inr"], ev["payee_is_new"] = amount, is_new
    return ev


def sessions_changed(original: pd.DataFrame, guarded: pd.DataFrame) -> int:
    """How many sessions had at least one payment shown with a different amount (rows with no amount never count)."""
    o = original.sort_values(["session_id", "t_sec"], kind="stable").reset_index(drop=True)
    a, b = o.amount_inr.to_numpy(dtype=float), guarded.amount_inr.to_numpy(dtype=float)
    diff = np.isfinite(a) & np.isfinite(b) & (a != b)
    return int(guarded.session_id[diff].nunique())


def combine(main: pd.DataFrame, guard: pd.DataFrame) -> pd.DataFrame:
    """Alarm if either copy alarms; the earlier alarm time wins."""
    g = guard.set_index("session_id")
    out = main.set_index("session_id").copy()
    out["alarm_main"] = out.alarm
    out["alarm_t_main"] = out.alarm_t
    out["alarm"] = out.alarm | g.alarm.reindex(out.index).fillna(False)
    out["alarm_t"] = pd.concat([out.alarm_t_main, g.alarm_t.reindex(out.index)], axis=1).min(axis=1)
    out["mechanism"] = np.where(out.alarm_main, out.mechanism, g.mechanism.reindex(out.index).where(g.alarm.reindex(out.index).fillna(False), "none"))
    out["interdicted"] = out.alarm & (out.first_pay_t.isna() | (out.alarm_t <= out.first_pay_t))
    return out.reset_index()


def rates(res: pd.DataFrame) -> dict:
    v = res[res.split == "validation"]
    s, l = v[v.label == "scam"], v[v.label == "legit"]
    return {"scam": len(s), "scam_alarmed": int(s.alarm.sum()), "recall": float(s.alarm.mean()),
            "legit": len(l), "false_alarms": int(l.alarm.sum()), "false_alarm_rate": float(l.alarm.mean()),
            "false_alarm_ci95": wilson(int(l.alarm.sum()), len(l)), "interdicted": float(s.interdicted.mean())}


def run(data: Path, alpha: float, per_band: int) -> dict:
    sys.path.insert(0, str(REF))
    import satark_detector as sd

    params = json.loads((REF / "params.json").read_text())
    wl = params["watchlisted_remote_apps"]
    det, res, (users, sessions, events, pay, alerts, first_pay) = sd.evaluate(data, alpha, wl)

    # 1. the whole validation split
    val_ids = set(sessions[sessions.split == "validation"].session_id)
    ev_val = events[events.session_id.isin(val_ids)]
    g_ev = apply_guard(ev_val)
    g_pay, g_alerts, g_first = sd.featurize(g_ev, users, wl)
    g_res = sd.decide(det, g_pay, g_alerts, g_first, sessions[sessions.session_id.isin(val_ids)])
    comb = combine(res[res.session_id.isin(val_ids)], g_res)
    changed = comb[(comb.alarm != comb.alarm_main)]
    sim = {"before": rates(res), "after": rates(comb),
           "new_alarms_scam": int((changed.label == "scam").sum()), "new_alarms_legit": int((changed.label == "legit").sum()),
           "sessions_with_a_split": sessions_changed(ev_val, g_ev)}

    # 2. the AI-style variants
    med, mad = float(users.hist_median_inr.median()), float(users.hist_mad_inr.median())
    ranges = av.amount_ranges(data)
    ev, vu, vs = av.build(per_band, med, mad, ranges)
    for c in ("caller_known", "payee_is_new"):
        ev[c] = ev[c].map({True: True, False: False, "True": True, "False": False})
    m_pay, m_alerts, m_first = sd.featurize(ev, vu, wl)
    main = sd.decide(det, m_pay, m_alerts, m_first, vs)
    gev = apply_guard(ev)
    gp, ga, gf = sd.featurize(gev, vu, wl)
    var = combine(main, sd.decide(det, gp, ga, gf, vs))
    before, after = av.summarise(main), av.summarise(var)
    return {"alpha": alpha, "sim": sim, "variants_before": before, "variants_after": after}


def render(m: dict) -> str:
    b, a, s = m["sim"]["before"], m["sim"]["after"], m["sim"]
    pct = lambda x: f"{100 * x:.3f}%"  # noqa: E731
    rows = []
    for x, y in zip(m["variants_before"], m["variants_after"]):
        rows.append(f"| {x['scenario']} | {'scam' if x['group'] == 'scam' else 'genuine'} | {x['alarmed']}/{x['n']} | {y['alarmed']}/{y['n']} |")
    return f"""# Split-payment guard

**Simulated data only.** The guard shows a second copy of the same model the running total paid to a payee who was new within the
last hour; the app alarms if either copy does. Thresholds were calibrated without the guard, so added false alarms are not hidden.

## The whole validation split (SatarkSim)
| | Before | After |
|---|---|---|
| Scam sessions held | {b['scam_alarmed']}/{b['scam']} ({pct(b['recall'])}) | {a['scam_alarmed']}/{a['scam']} ({pct(a['recall'])}) |
| Genuine sessions wrongly held | {b['false_alarms']}/{b['legit']} ({pct(b['false_alarm_rate'])}) | {a['false_alarms']}/{a['legit']} ({pct(a['false_alarm_rate'])}, 95% interval {pct(a['false_alarm_ci95'][0])} to {pct(a['false_alarm_ci95'][1])}) |
| Scams held before the first payment | {pct(b['interdicted'])} | {pct(a['interdicted'])} |

The guard turned on in {s['sessions_with_a_split']} validation sessions (ones with more than one payment to the same new payee within an hour).
It added {s['new_alarms_scam']} scam alarm(s) and {s['new_alarms_legit']} genuine false alarm(s). The deck's target for false alarms is 0.100%.

## The AI-style variants (held / runs)
| Scenario | Kind | Before | After |
|---|---|---|---|
{chr(10).join(rows)}

## Limits
- Simulated sessions and team-written scenarios, not real people. Real users who pay one new payee several times in an hour
  (a shop, a landlord in instalments) would trigger the guard's arithmetic more than the simulator suggests.
- It only adds an alarm when the model also sees an unknown contact or another signal, so a genuine instalment alone stays quiet.
  That is measured above for the simulator, not for real behaviour.
- The Kotlin version (`CumulativeNewPayee`) and this one share the same test cases, but they are separate code.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--per-band", type=int, default=30)
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    alpha = a.alpha if a.alpha is not None else json.loads((REF / "params.json").read_text())["calibration_alpha"]
    m = run(a.data, alpha, a.per_band)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "split_guard.md").write_text(render(m), encoding="utf-8", newline="\n")
    (a.out / "split_guard.json").write_text(json.dumps(m, indent=2, default=float), encoding="utf-8")
    print(render(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
