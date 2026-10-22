#!/usr/bin/env python3
"""Experiment: thresholds with a confidence statement about the false-alarm rate (does NOT change the shipped model).

The shipped rule sets each cohort's threshold at the k-th smallest legitimate calibration score, k = ceil((n+1)(1-0.001)).
That makes the EXPECTED false-alarm rate <= 0.1%, but the realised rate of one calibration draw varies around it (it is
Beta-distributed), so a validation run can land slightly above (it did: 0.111%).

Pre-specified alternative (uses calibration data only, never validation): per cohort, take the largest a (= number of
calibration scores allowed at or above the threshold) such that P(true false-alarm rate <= 0.1%) >= 90%, where for the
k-th order statistic of n exchangeable scores the exceedance mass is Beta(n-k+1, k). If even a=1 (the maximum score) cannot
reach 90% (n too small, here n < 2303) the cohort uses the maximum, the best this sample size allows.
Validation is evaluated once per variant and reported with 95% Clopper-Pearson intervals.

Usage (repo root): python detector/experiments/conformal_confidence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
import satark_detector as sd  # noqa: E402

TARGET, CONFIDENCE = 0.001, 0.90


def pick_k(n: int) -> tuple[int, float]:
    """Smallest threshold rank k (most permissive threshold) whose exceedance mass is <= TARGET with prob >= CONFIDENCE."""
    best = n  # the maximum score is always allowed
    for a in range(1, n + 1):
        if beta.cdf(TARGET, a, n + 1 - a) >= CONFIDENCE:
            best = n + 1 - a
        else:
            break
    return best, float(beta.cdf(TARGET, n + 1 - best, best))


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def main():
    d = ROOT / "data" / "satarksim"
    users = pd.read_csv(d / "satarksim_users.csv")
    sessions = pd.read_csv(d / "satarksim_sessions.csv")
    events = pd.read_csv(d / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    wl = json.loads((ROOT / "contracts" / "watchlist.json").read_text())["packages"]
    pay, alerts, first_pay = sd.featurize(events, users, wl)
    by = sessions.groupby("split").session_id.apply(set)
    det = sd.Detector().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], 0.001)
    shipped = dict(det.thr)

    s = pay.assign(score=det.score(pay)).groupby("session_id").score.max()
    cal = sessions[sessions.session_id.isin(by["calibration"]) & (sessions.label == "legit")]
    cal = cal.assign(score=cal.session_id.map(s).fillna(-np.inf))
    alt, info = {}, {}
    for band, g in cal.groupby("age_band"):
        sc = np.sort(g.score.to_numpy())
        k, conf = pick_k(len(sc))
        alt[band] = float(sc[k - 1])
        info[band] = (len(sc), k, conf)

    rows = {}
    for name, thr in (("shipped (expected FA <= 0.1%)", shipped), ("90%-confidence variant", alt)):
        det.thr = thr
        res = sd.decide(det, pay, alerts, first_pay, sessions)
        v = res[res.split == "validation"]
        sc_, lg = v[v.label == "scam"], v[v.label == "legit"]
        rows[name] = dict(rec=(int(sc_.alarm.sum()), len(sc_)), inter=(int(sc_.interdicted.sum()), len(sc_)),
                          fa=(int(lg.alarm.sum()), len(lg)),
                          fam=(int(sc_[sc_.playbook == "family_emergency_scam"].alarm.sum()), int((sc_.playbook == "family_emergency_scam").sum())),
                          bands={b: (int(g.alarm.sum()), len(g)) for b, g in lg.groupby("age_band")})

    def f(kn):
        k, n = kn
        lo, hi = cp(k, n)
        return f"{k}/{n} = {100*k/n:.3f}% [{100*lo:.3f}, {100*hi:.3f}]"

    L = ["# Experiment: thresholds with a confidence statement about the false-alarm rate", "",
         "Simulated data. Rule chosen from calibration data only; validation evaluated once per variant; 95% Clopper-Pearson intervals.", "",
         "| Cohort | Calibration n | Threshold rank k | P(true false-alarm rate <= 0.1%) | Shipped threshold | Variant threshold |", "|---|---|---|---|---|---|"]
    for b, (n, k, conf) in info.items():
        L.append(f"| {b} | {n} | {k} (n-{n-k}) | {conf:.0%} | {shipped[b]:.3f} | {alt[b]:.3f} |")
    L += ["", "| Variant | Scam recall | Interdicted | False alarms | Family-emergency scam recall |", "|---|---|---|---|---|"]
    for name, r in rows.items():
        L.append(f"| {name} | {f(r['rec'])} | {f(r['inter'])} | {f(r['fa'])} | {f(r['fam'])} |")
    L += ["", "False alarms by band: " + "; ".join(f"{n}: " + ", ".join(f"{b} {k}/{m}" for b, (k, m) in r["bands"].items()) for n, r in rows.items()), ""]
    out = ROOT / "detector" / "experiments" / "conformal_confidence.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
