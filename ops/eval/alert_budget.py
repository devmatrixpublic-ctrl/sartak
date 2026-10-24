"""Alert budget: how often would a person be interrupted? (problem statement: "without creating alert fatigue")

The Round 1 deck set design budgets: a Nudge at most once per user per month, a Pause at most once per user per quarter.
This turns the SatarkSim evaluation into those units. It does NOT measure real users.

What is measured, and what is assumed:
  * MEASURED on the simulator (validation split): the share of legitimate payment sessions that raised an alarm
    (a Pause), and the share that would show a Nudge (a new payee while an unknown call is active, no alarm).
  * ASSUMED: every payment a person makes in Satark is one scored session, so a user making N payments a month gets
    N chances. N comes from each simulated user's `payments_per_month`. The false-alarm rate is taken as constant per
    payment and independent between payments. The simulator holds only a few sessions per user, so counting alerts per
    user directly would understate the burden; projecting from a per-session rate is the fair way to compare to a budget.

Usage (repo root):  python ops/eval/alert_budget.py [--data data/satarksim] [--alpha 0.0008] [--out ops/eval/reports]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
PAUSE_BUDGET_PER_QUARTER = 1.0   # deck: Pause <= 1 / user / quarter
NUDGE_BUDGET_PER_MONTH = 1.0     # deck: Nudge <= 1 / user / month
TIGHT_RATIO = 2.0                # proposed tighter nudge rule: amount at least 2x the user's usual payment


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def expected_alerts(rate: float, payments_per_month: float, months: float) -> float:
    """Expected number of alerts for one user: per-payment alert rate x payments made in the period."""
    return rate * payments_per_month * months


def share_with_at_least_one(lams: np.ndarray) -> float:
    """If each user's alerts are Poisson with mean `lam`, the expected share of users with one or more."""
    lams = np.asarray(lams, dtype=float)
    return float(np.mean(1.0 - np.exp(-lams))) if lams.size else 0.0


def nudge_sessions(events: pd.DataFrame, median_by_user: dict[str, float] | None = None, min_ratio: float = 0.0) -> set[str]:
    """Sessions where the app would show a Nudge: a payment to a new payee while an unknown call is active.

    Mirrors the app's rule (unknown call active + new payee at the payment). With `min_ratio` > 0 it also requires the
    amount to be at least that many times the user's usual payment: a proposed tighter rule, not what the app does today.
    Alarms are removed by the caller.
    """
    out: set[str] = set()
    ev = events[events.event_type.isin(["CALL_START", "CALL_END", "PAYMENT_ATTEMPT"])].sort_values(["session_id", "t_sec"], kind="stable")
    for sid, g in ev.groupby("session_id", sort=False):
        unknown_call = False
        for e in g.itertuples(index=False):
            if e.event_type == "CALL_START":
                unknown_call = e.caller_known is False or e.caller_known == "False"
            elif e.event_type == "CALL_END":
                unknown_call = False
            elif e.event_type == "PAYMENT_ATTEMPT" and unknown_call and (e.payee_is_new is True or e.payee_is_new == "True"):
                if min_ratio > 0 and median_by_user is not None:
                    if float(e.amount_inr or 0) < min_ratio * median_by_user.get(e.user_id, 0.0):
                        continue
                out.add(sid)
                break
    return out


def compute(res: pd.DataFrame, users: pd.DataFrame, events: pd.DataFrame) -> dict:
    v = res[(res.split == "validation") & (res.label == "legit")]
    n = len(v)
    k = int(v.alarm.sum())
    pause_rate = k / n
    pause_lo, pause_hi = wilson(k, n)

    nudge_ids = nudge_sessions(events[events.session_id.isin(v.session_id)])
    nudge_only = v[v.session_id.isin(nudge_ids) & ~v.alarm]
    nudge_rate = len(nudge_only) / n
    nudge_lo, nudge_hi = wilson(len(nudge_only), n)

    u = users[users.split == "validation"]
    ppm = u.payments_per_month.astype(float).to_numpy()
    med = users.set_index("user_id").hist_median_inr.astype(float).to_dict()
    tight_ids = nudge_sessions(events[events.session_id.isin(v.session_id)], med, TIGHT_RATIO)
    tight_only = v[v.session_id.isin(tight_ids) & ~v.alarm]
    tight_rate = len(tight_only) / n
    tight_lo, tight_hi = wilson(len(tight_only), n)
    with_call = events[events.session_id.isin(v.session_id) & events.event_type.isin(["CALL_START", "VIDEO_SESSION_START"])
                       & events.caller_known.map(lambda x: x is False or x == "False")].session_id.nunique()

    def block(rate, hi, months, budget):
        lam = np.array([expected_alerts(rate, x, months) for x in ppm])
        lam_hi = np.array([expected_alerts(hi, x, months) for x in ppm])
        return {
            "mean_per_user": float(lam.mean()), "mean_per_user_upper95": float(lam_hi.mean()),
            "worst_tier_per_user": float(lam.max()), "share_with_one_or_more": share_with_at_least_one(lam),
            "budget": budget, "within_budget_mean": bool(lam.mean() <= budget), "within_budget_upper95": bool(lam_hi.mean() <= budget),
            "within_budget_worst_tier": bool(lam.max() <= budget),
        }

    return {
        "legit_sessions": n,
        "pause": {"false_alarms": k, "rate": pause_rate, "ci95": [pause_lo, pause_hi],
                  **block(pause_rate, pause_hi, 3.0, PAUSE_BUDGET_PER_QUARTER), "unit": "Pauses per user per quarter"},
        "nudge": {"sessions": len(nudge_only), "rate": nudge_rate, "ci95": [nudge_lo, nudge_hi],
                  **block(nudge_rate, nudge_hi, 1.0, NUDGE_BUDGET_PER_MONTH), "unit": "Nudges per user per month"},
        "nudge_tight": {"sessions": len(tight_only), "rate": tight_rate, "ci95": [tight_lo, tight_hi],
                        **block(tight_rate, tight_hi, 1.0, NUDGE_BUDGET_PER_MONTH), "unit": "Nudges per user per month", "min_ratio": TIGHT_RATIO},
        "legit_with_unknown_call_share": with_call / n,
        "users": int(len(u)),
        "payments_per_month": {"min": float(ppm.min()), "median": float(np.median(ppm)), "max": float(ppm.max())},
    }


def render(m: dict, alpha: float) -> str:
    p, nd, nt = m["pause"], m["nudge"], m["nudge_tight"]
    pct = lambda x: f"{100 * x:.3f}%"  # noqa: E731

    def verdict(b: dict) -> str:
        if not b["within_budget_mean"]:
            return "OVER budget on average"
        if not b["within_budget_worst_tier"]:
            return "within on average, OVER for the busiest users"
        return "within budget for every activity tier"
    return f"""# Alert budget

**Simulated data only (SatarkSim). This is a projection from a measured per-payment rate, not a measurement of real people.**
Calibration alpha {alpha}. Validation split: {m['legit_sessions']:,} legitimate sessions, {m['users']:,} simulated users.

## What is measured

| | Count | Rate per legitimate payment | 95% interval |
|---|---|---|---|
| Pause (alarm) on a legitimate session | {p['false_alarms']} | {pct(p['rate'])} | {pct(p['ci95'][0])} to {pct(p['ci95'][1])} |
| Nudge only (new payee during an unknown call, no alarm), today's rule | {nd['sessions']} | {pct(nd['rate'])} | {pct(nd['ci95'][0])} to {pct(nd['ci95'][1])} |
| Nudge only, tighter rule (also needs the amount to be at least {nt['min_ratio']:.0f}x the user's usual payment) | {nt['sessions']} | {pct(nt['rate'])} | {pct(nt['ci95'][0])} to {pct(nt['ci95'][1])} |

{pct(m['legit_with_unknown_call_share'])} of the legitimate simulated sessions contain an unknown call. The simulator includes many such calls on purpose
(bank support, delivery, the genuine family emergency) as hard negatives, so the nudge rate here is likely higher than real life. Treat it as a stress test.

## Projected burden on a legitimate user, against the deck's budget

| Alert | Budget (deck) | Mean per user | Upper-bound (95%) | Worst activity tier | Share of users hit at least once | Verdict |
|---|---|---|---|---|---|---|
| Pause, per quarter | at most {p['budget']:.0f} | {p['mean_per_user']:.3f} | {p['mean_per_user_upper95']:.3f} | {p['worst_tier_per_user']:.3f} | {pct(p['share_with_one_or_more'])} | {verdict(p)} |
| Nudge, per month, today's rule | at most {nd['budget']:.0f} | {nd['mean_per_user']:.3f} | {nd['mean_per_user_upper95']:.3f} | {nd['worst_tier_per_user']:.3f} | {pct(nd['share_with_one_or_more'])} | {verdict(nd)} |
| Nudge, per month, tighter rule | at most {nt['budget']:.0f} | {nt['mean_per_user']:.3f} | {nt['mean_per_user_upper95']:.3f} | {nt['worst_tier_per_user']:.3f} | {pct(nt['share_with_one_or_more'])} | {verdict(nt)} |

**Finding.** Pauses are well inside the budget. The nudge is the fatigue risk: it is a policy in the app (not in the frozen detector),
so it can be tightened without touching the model. The tighter rule above is a proposal; it is measured here but not yet in the app.

## Assumptions (read these)

1. Every payment a person makes in Satark is one scored session. Payments per month per user come from the simulator
   (min {m['payments_per_month']['min']:.0f}, median {m['payments_per_month']['median']:.0f}, max {m['payments_per_month']['max']:.0f}).
2. The alert rate per payment is constant and independent between payments. Real people are bunched (a week of unusual
   spending), so real burden would be lumpier than this average.
3. The simulator holds only a few sessions per user, so alerts were not counted per user directly. They were projected.
4. A Nudge is approximated as "a payment to a new payee while an unknown call is active, with no alarm". The app's
   own rule is the same shape, but real call patterns differ from simulated ones.
5. Repeat alerts within 60 minutes are merged by the app, so one incident is one alert. The simulator also counts the
   first alarm per session only.
6. This says nothing about missed scams. See the main evaluation report for recall.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(REF))
    import satark_detector as sd

    params = json.loads((REF / "params.json").read_text())
    alpha = a.alpha if a.alpha is not None else params["calibration_alpha"]
    _, res, (users, sessions, events, *_rest) = sd.evaluate(a.data, alpha, params["watchlisted_remote_apps"])
    m = compute(res, users, events)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "alert_budget.md").write_text(render(m, alpha), encoding="utf-8", newline="\n")
    (a.out / "alert_budget.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(render(m, alpha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
