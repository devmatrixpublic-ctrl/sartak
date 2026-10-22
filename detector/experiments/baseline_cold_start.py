#!/usr/bin/env python3
"""Experiment: how much does detection depend on knowing the user's own payment history? (Does NOT change the shipped model.)

The reference scores each payment against a per-user median/MAD (SatarkSim `hist_median_inr`, `hist_mad_inr`: the user's long-run
history). On a phone a fresh install has none: `Baseline.coldStart` returns the population prior from model.json and then blends
toward the user's own completed payments with weight n/(n+20) over the last 50.

Variants, each retrained on train and calibrated on the legitimate calibration sessions at the shipped calibration alpha, then
evaluated once on validation:
  A  static per-user history (the reference, what the shipped numbers use): a user with a long, mature history
  B  population prior for EVERYONE: a brand-new install (nothing learned yet)
  C  the on-device rule, fed only by the payments SatarkSim contains: for each session, the same user's earlier LEGITIMATE
     payments (last 50), blended n/(n+20) with the prior. SatarkSim holds only a few sessions per user, so this stays close to B;
     it shows how fast the blend moves, not what a month of real use would do.

Usage (repo root): python detector/experiments/baseline_cold_start.py
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

BLEND_K, WINDOW_N = 20, 50


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def fmt(k, n, d=1):
    lo, hi = cp(k, n)
    return f"{k}/{n} = {100*k/n:.{d}f}% [{100*lo:.{d}f}, {100*hi:.{d}f}]"


def rolling_stats(events, sessions, prior_med, prior_mad):
    """Per-session (median, MAD, n) from the same user's earlier legitimate payments, blended with the prior."""
    pay = events[events.event_type == "PAYMENT_ATTEMPT"][["session_id", "user_id", "amount_inr"]]
    first_ts = events.groupby("session_id").ts_abs.min().rename("t0")
    s = sessions[["session_id", "user_id", "label"]].merge(first_ts, on="session_id").sort_values(["user_id", "t0"])
    amounts = pay.groupby("session_id").amount_inr.apply(list).to_dict()
    out = {}
    for uid, g in s.groupby("user_id", sort=False):
        history: list[float] = []
        for r in g.itertuples(index=False):
            win = history[-WINDOW_N:]
            n = len(win)
            if n:
                own_med = float(np.median(win))
                own_mad = float(np.median(np.abs(np.array(win) - own_med)))
                w = n / (n + BLEND_K)
                med, mad = w * own_med + (1 - w) * prior_med, w * own_mad + (1 - w) * prior_mad
            else:
                med, mad = prior_med, prior_mad
            out[r.session_id] = (med, mad, n)
            if r.label == "legit":                                    # only legitimate payments define "normal"
                history += [a for a in amounts.get(r.session_id, []) if a == a]
    return out


def run(events, users, sessions, wl, alpha):
    pay, alerts, first_pay = sd.featurize(events, users, wl)
    by = sessions.groupby("split").session_id.apply(set)
    det = sd.Detector().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], alpha)
    res = sd.decide(det, pay, alerts, first_pay, sessions)
    v = res[res.split == "validation"]
    sc, lg = v[v.label == "scam"], v[v.label == "legit"]
    fam = sc[sc.playbook == "family_emergency_scam"]
    return dict(rec=(int(sc.alarm.sum()), len(sc)), inter=(int(sc.interdicted.sum()), len(sc)), fa=(int(lg.alarm.sum()), len(lg)),
                fam=(int(fam.alarm.sum()), len(fam)),
                thr={b: round(float(t), 3) for b, t in det.thr.items()})


def main():
    params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())
    alpha = params["calibration_alpha"]
    wl = json.loads((ROOT / "contracts" / "watchlist.json").read_text())["packages"]
    d = ROOT / "data" / "satarksim"
    users = pd.read_csv(d / "satarksim_users.csv")
    sessions = pd.read_csv(d / "satarksim_sessions.csv")
    events = pd.read_csv(d / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    model = json.loads((ROOT / "detector" / "src" / "main" / "resources" / "model.json").read_text())
    pm, pa = model["baseline"]["prior_median_inr"], model["baseline"]["prior_mad_inr"]

    results = {}
    print("A: static per-user history", flush=True)
    results["A. mature personal history (reference; what the shipped numbers use)"] = run(events, users, sessions, wl, alpha)

    print("B: population prior for everyone", flush=True)
    ub = users.copy(); ub["hist_median_inr"], ub["hist_mad_inr"] = pm, pa
    results["B. brand-new install: population prior for everyone"] = run(events, ub, sessions, wl, alpha)

    print("C: on-device rolling rule over in-simulation payments", flush=True)
    st = rolling_stats(events, sessions, pm, pa)
    ev_c = events.copy(); ev_c["user_id"] = ev_c.session_id
    uc = pd.DataFrame({"user_id": list(st), "hist_median_inr": [v[0] for v in st.values()], "hist_mad_inr": [v[1] for v in st.values()]})
    uc = uc.merge(sessions[["session_id", "age_band"]].rename(columns={"session_id": "user_id"}), on="user_id", how="left")
    results["C. on-device rule fed by the payments SatarkSim contains"] = run(ev_c, uc, sessions, wl, alpha)
    val_ids = set(sessions[sessions.split == "validation"].session_id)
    ns = np.array([st[s][2] for s in val_ids if s in st])

    L = ["# Experiment: how much does detection depend on the user's own payment history?", "",
         "Simulated data. Each variant is retrained on train, calibrated on legitimate calibration sessions at the shipped calibration "
         f"alpha' = {alpha:.2%}, and evaluated once on validation (95% Clopper-Pearson intervals). The shipped model is variant A and is unchanged.", "",
         "| Variant | Scam recall | Interdicted | False alarms | Family-emergency scam recall |", "|---|---|---|---|---|"]
    for name, r in results.items():
        L.append(f"| {name} | {fmt(*r['rec'])} | {fmt(*r['inter'])} | {fmt(*r['fa'], d=3)} | {fmt(*r['fam'])} |")
    L += ["", f"Variant C history size at validation: median {int(np.median(ns))} prior legitimate payments, "
          f"{100*np.mean(ns == 0):.0f}% of validation sessions have none, {100*np.mean(ns >= 10):.0f}% have 10 or more (blend weight n/(n+{BLEND_K})).", "",
          "Reading it: A is a user with a mature, accurate baseline. B and C are what the app has on day one. The recall gap A to B is the price "
          "of having no personal history yet; thresholds were recalibrated per variant so false alarms stay comparable. SatarkSim gives each "
          "user only a few sessions, so C cannot show how a real month of use closes that gap, and its `hist_*` numbers in A are the generator's "
          "own long-run values, which a phone can only approach.", ""]
    out = ROOT / "detector" / "experiments" / "baseline_cold_start.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
