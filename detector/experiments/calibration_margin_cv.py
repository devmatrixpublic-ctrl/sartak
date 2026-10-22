#!/usr/bin/env python3
"""Choose the conformal calibration margin by cross-validation on train+calibration data only (validation never used).

Why: thresholds calibrated at alpha = 0.001 give an EXPECTED false-alarm rate of 0.1%, but one calibration draw lands above
or below it (validation showed 0.111%). The plan's target is "false alarms <= 0.1%", so a calibration margin (alpha' < 0.001)
is needed to leave room for that sampling noise. alpha' is a calibration parameter; the TARGET stays 0.1%.

Selection rule, fixed before the run: over the grid below, take the LARGEST alpha' (best recall) whose pooled cross-validated
false-alarm rate is <= 0.09% (0.1% minus a 10% safety margin). Recall at that alpha' is reported, not used to choose.

Procedure: 5 repeats of a user-level random split of the train+calibration sessions into fit 60% / calibration 20% / test 20%;
fit the logistic model on `fit`, set per-age-band thresholds on the legitimate `calibration` sessions, score the `test` sessions.

Usage (repo root): python detector/experiments/calibration_margin_cv.py
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

GRID = [0.0010, 0.0009, 0.0008, 0.0007, 0.0006, 0.0005, 0.0004]
FA_LIMIT = 0.0009
REPEATS = 5


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

    pool = sessions[sessions.split.isin(["train", "calibration"])]
    uids = np.array(sorted(pool.user_id.unique()))
    tot = {a: dict(fa=0, nleg=0, rec=0, nsc=0, per=[]) for a in GRID}
    for rep in range(REPEATS):
        rng = np.random.default_rng(1000 + rep)
        perm = rng.permutation(uids)
        n = len(perm)
        fit_u, cal_u, test_u = set(perm[: int(.6 * n)]), set(perm[int(.6 * n): int(.8 * n)]), set(perm[int(.8 * n):])
        sid = lambda us: set(pool[pool.user_id.isin(us)].session_id)
        fit, cal, test = sid(fit_u), sid(cal_u), sid(test_u)
        det = sd.Detector().fit(pay, sessions, fit)
        for a in GRID:
            det.calibrate(pay, sessions, cal, a)
            res = sd.decide(det, pay, alerts, first_pay, sessions)
            t = res[res.session_id.isin(test)]
            sc, lg = t[t.label == "scam"], t[t.label == "legit"]
            r = tot[a]
            r["fa"] += int(lg.alarm.sum()); r["nleg"] += len(lg); r["rec"] += int(sc.alarm.sum()); r["nsc"] += len(sc)
            r["per"].append(lg.alarm.mean())
        print(f"repeat {rep + 1}/{REPEATS} done", flush=True)

    chosen = None
    L = ["# Calibration margin chosen by cross-validation (validation split never used)", "",
         f"5 repeats, user-level 60/20/20 split of train+calibration. Rule fixed in advance: largest alpha' with pooled false-alarm <= {FA_LIMIT:.2%}.", "",
         "| alpha' (calibration) | CV false alarms (95% CI) | worst repeat | CV recall (95% CI) |", "|---|---|---|---|"]
    for a in GRID:
        r = tot[a]
        flo, fhi = cp(r["fa"], r["nleg"]); rlo, rhi = cp(r["rec"], r["nsc"])
        L.append(f"| {a:.4f} | {r['fa']}/{r['nleg']} = {100*r['fa']/r['nleg']:.3f}% [{100*flo:.3f}, {100*fhi:.3f}] | {100*max(r['per']):.3f}% | "
                 f"{100*r['rec']/r['nsc']:.2f}% [{100*rlo:.2f}, {100*rhi:.2f}] |")
        if chosen is None and r["fa"] / r["nleg"] <= FA_LIMIT:
            chosen = a
    L += ["", f"**Chosen alpha' = {chosen}**" if chosen else "**No alpha' in the grid meets the false-alarm limit.**", "",
          "The repeats share users, so the intervals are optimistic; treat them as a guide, not a guarantee."]
    out = ROOT / "detector" / "experiments" / "calibration_margin_cv.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
