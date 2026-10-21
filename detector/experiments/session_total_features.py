#!/usr/bin/env python3
"""Experiment: do session-running features improve the weak family-emergency playbook? (Does NOT change the shipped model.)

Adds, at every payment attempt:
  n_pay_sofar      number of payment attempts in the session so far, including this one (capped at 10)
  log_cum_ratio    log((total attempted so far + 1) / (user median + 1)), clipped to [-5, 12]
Trains each variant on TRAIN, sets per-age-band conformal thresholds (alpha = 0.1%) on CALIBRATION legit sessions,
and reports VALIDATION once. Simulated data: separation of scams that make several larger payments is partly a
property of the generator, so treat gains as an upper bound.

Usage (repo root):  python detector/experiments/session_total_features.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
import satark_detector as sd  # noqa: E402

BASE = list(sd.FEATURES)
EXTRA = ["n_pay_sofar", "log_cum_ratio"]


def featurize_extra(events, users, watchlist):
    ev = sd.dedupe(events)
    u = users.set_index("user_id")
    wl = set(watchlist)
    pay_rows, alert_rows = [], []
    for sid, g in ev.groupby("session_id", sort=False):
        uid = g.user_id.iloc[0]
        med = float(u.at[uid, "hist_median_inr"])
        rows, alerts = sd.session_features(g, med, float(u.at[uid, "hist_mad_inr"]), wl)
        amts = g[g.event_type == "PAYMENT_ATTEMPT"].amount_inr.fillna(0).to_numpy(dtype=float)
        assert len(amts) == len(rows)
        cum = 0.0
        for k, r in enumerate(rows):
            cum += amts[k]
            r["n_pay_sofar"] = float(min(k + 1, 10))
            r["log_cum_ratio"] = float(np.clip(math.log((cum + 1) / (med + 1)), -5, 12))
            r["session_id"] = sid
        pay_rows += rows
        alert_rows += [{"session_id": sid, "t": t, "rule": rule} for t, rule in alerts]
    pay = pd.DataFrame(pay_rows)
    alerts = pd.DataFrame(alert_rows, columns=["session_id", "t", "rule"])
    first_pay = ev[ev.event_type == "PAYMENT_ATTEMPT"].groupby("session_id").t_sec.min().rename("first_pay_t")
    return pay, alerts, first_pay


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def evaluate(features, pay, alerts, first_pay, sessions):
    sd.FEATURES = features
    by = sessions.groupby("split").session_id.apply(set)
    det = sd.Detector().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], 0.001)
    res = sd.decide(det, pay, alerts, first_pay, sessions)
    v = res[res.split == "validation"]
    sc, lg = v[v.label == "scam"], v[v.label == "legit"]
    fe_s = sc[sc.playbook == "family_emergency_scam"]
    fe_l = lg[lg.session_kind == "hn_family_emergency"]
    out = {"recall": (int(sc.alarm.sum()), len(sc)), "interdicted": (int(sc.interdicted.sum()), len(sc)),
           "false_alarm": (int(lg.alarm.sum()), len(lg)),
           "fam_scam_recall": (int(fe_s.alarm.sum()), len(fe_s)), "fam_scam_interdicted": (int(fe_s.interdicted.sum()), len(fe_s)),
           "fam_genuine_flagged": (int(fe_l.alarm.sum()), len(fe_l)),
           "by_band_fa": {b: (int(g.alarm.sum()), len(g)) for b, g in lg.groupby("age_band")},
           "thr": det.thr, "weights": det.weights().to_dict()}
    return out


def fmt(kn, ci=True):
    k, n = kn
    s = f"{k}/{n} = {100 * k / n:.2f}%"
    if ci:
        lo, hi = cp(k, n)
        s += f" [{100 * lo:.2f}, {100 * hi:.2f}]"
    return s


def main():
    d = ROOT / "data" / "satarksim"
    users = pd.read_csv(d / "satarksim_users.csv")
    sessions = pd.read_csv(d / "satarksim_sessions.csv")
    events = pd.read_csv(d / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    wl = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())["watchlisted_remote_apps"]
    pay, alerts, first_pay = featurize_extra(events, users, wl)

    variants = {"A. shipped (16 features)": BASE, "B. + n_pay_sofar": BASE + ["n_pay_sofar"], "C. + both session features": BASE + EXTRA}
    results = {name: evaluate(f, pay, alerts, first_pay, sessions) for name, f in variants.items()}

    L = ["# Experiment: session-running features for the family-emergency scam", "",
         "Simulated data. Train on train, thresholds on calibration (alpha = 0.1%), validation reported once. 95% Clopper-Pearson intervals in brackets. "
         "The shipped model is variant A and is unchanged.", "",
         "| Variant | Scam recall | Interdicted | False alarms (all legit) | Family scam recall | Family scam interdicted | Genuine family emergency flagged |", "|---|---|---|---|---|---|---|"]
    for n, r in results.items():
        L.append(f"| {n} | {fmt(r['recall'])} | {fmt(r['interdicted'])} | {fmt(r['false_alarm'])} | {fmt(r['fam_scam_recall'])} | "
                 f"{fmt(r['fam_scam_interdicted'])} | {fmt(r['fam_genuine_flagged'])} |")
    L += ["", "False alarms by age band (validation):", "", "| Variant | " + " | ".join(results[next(iter(results))]["by_band_fa"]) + " |", "|---|---|---|---|"]
    for n, r in results.items():
        L.append(f"| {n} | " + " | ".join(fmt(v, ci=False) for v in r["by_band_fa"].values()) + " |")
    L += ["", "Weights of the added features (variant C): " + ", ".join(f"{k} {v:+.2f}" for k, v in results["C. + both session features"]["weights"].items() if k in EXTRA), ""]
    out = ROOT / "detector" / "experiments" / "session_total_features.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
