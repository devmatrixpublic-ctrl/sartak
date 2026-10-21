#!/usr/bin/env python3
"""Explicit training run for the Satark detector, with metrics on every split.

Fits the 16-feature logistic regression on the SatarkSim TRAIN split (labels = label_observed, which has 2% noise),
chooses the regularisation strength C on the CALIBRATION split (never on validation), compares against a gradient-boosted
model as a sanity check (not shipped: the on-device port is logistic), and reports payment-level and session-level
metrics on train / calibration / validation. Writes detector/training_report.md.

Usage (repo root):  python detector/tools/train_report.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
import satark_detector as sd  # noqa: E402

DATA = ROOT / "data" / "satarksim"
SEED = 0


def load():
    users = pd.read_csv(DATA / "satarksim_users.csv")
    sessions = pd.read_csv(DATA / "satarksim_sessions.csv")
    events = pd.read_csv(DATA / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())
    pay, alerts, first_pay = sd.featurize(events, users, params["watchlisted_remote_apps"])
    return sessions, pay


def split_rows(pay, sessions, name):
    ids = set(sessions[sessions.split == name].session_id)
    d = pay[pay.session_id.isin(ids)].merge(sessions[["session_id", "label", "label_observed", "age_band"]], on="session_id")
    return d


def row_metrics(model_scores, d, thr=None):
    y_true = (d.label == "scam").astype(int).to_numpy()
    out = {"rows": len(d), "scam_rows": int(y_true.sum()),
           "AUC": roc_auc_score(y_true, model_scores), "AP": average_precision_score(y_true, model_scores)}
    return out


def fit_lr(train, C):
    sc = StandardScaler().fit(train[sd.FEATURES])
    lr = LogisticRegression(max_iter=2000, C=C).fit(sc.transform(train[sd.FEATURES]), (train.label_observed == "scam").astype(int))
    return sc, lr


def main():
    t0 = time.time()
    sessions, pay = load()
    train, cal, val = (split_rows(pay, sessions, s) for s in ("train", "calibration", "validation"))
    ytr = (train.label_observed == "scam").astype(int)
    L = ["# Satark detector: training report", "",
         "Simulated data (SatarkSim v2). Everything here is about the model's fit on simulated sessions, not real-world accuracy.", "",
         "## 1. Data", "",
         "| Split | Payment rows | Scam rows (true label) | Sessions |", "|---|---|---|---|"]
    for n, d in (("train", train), ("calibration", cal), ("validation", val)):
        L.append(f"| {n} | {len(d):,} | {int((d.label == 'scam').sum()):,} | {d.session_id.nunique():,} |")
    L += ["", f"Training target: `label_observed` (2% of labels deliberately flipped). Rows are payment attempts; the 16 features are in `contracts`/`model.json` order. "
          "Class balance in training is "
          f"{ytr.mean():.1%} scam, so the logistic model is unweighted: the decision threshold comes from conformal calibration on legitimate sessions, not from 0.5.", ""]

    # 2. choose C on the calibration split (log-loss + AUC), never on validation
    L += ["## 2. Regularisation chosen on the calibration split", "",
          "| C | Train log-loss | Calibration log-loss | Calibration AUC | Calibration AP |", "|---|---|---|---|---|"]
    best = None
    ycal_obs = (cal.label_observed == "scam").astype(int)
    for C in (0.01, 0.1, 1.0, 10.0, 100.0):
        sc, lr = fit_lr(train, C)
        ptr = lr.predict_proba(sc.transform(train[sd.FEATURES]))[:, 1]
        pca = lr.predict_proba(sc.transform(cal[sd.FEATURES]))[:, 1]
        ll = log_loss(ycal_obs, pca)
        L.append(f"| {C} | {log_loss(ytr, ptr):.4f} | {ll:.4f} | {roc_auc_score((cal.label == 'scam').astype(int), pca):.4f} | "
                 f"{average_precision_score((cal.label == 'scam').astype(int), pca):.4f} |")
        if best is None or ll < best[0]:
            best = (ll, C)
    L += ["", f"Lowest calibration log-loss at C = **{best[1]}**. The shipped model uses C = 1.0 (the reference's setting). "
          + ("These agree." if best[1] == 1.0 else "They differ; changing C would change the weights, thresholds and the 36 expected vectors, so it was NOT applied. Treat it as a tuning option to decide on."), ""]

    # 3. the shipped model (C = 1.0), metrics on every split
    sc, lr = fit_lr(train, 1.0)
    L += ["## 3. Shipped model (logistic regression, C = 1.0): metrics on every split", "",
          "Payment-level discrimination (score every payment attempt; true label). Accuracy is shown at the probability cut 0.5 only to answer the question; "
          "it is not the operating point (the real threshold is conformal) and is dominated by the majority class.", "",
          "| Split | AUC | Average precision | Accuracy @0.5 | Majority-class accuracy |", "|---|---|---|---|---|"]
    for n, d in (("train", train), ("calibration", cal), ("validation", val)):
        p = lr.predict_proba(sc.transform(d[sd.FEATURES]))[:, 1]
        y = (d.label == "scam").astype(int)
        L.append(f"| {n} | {roc_auc_score(y, p):.4f} | {average_precision_score(y, p):.4f} | {accuracy_score(y, (p >= 0.5).astype(int)):.4f} | {max(y.mean(), 1 - y.mean()):.4f} |")

    # 4. session-level at the real operating point (conformal thresholds, alpha = 0.1%)
    det = sd.Detector().fit(pay, sessions, set(sessions[sessions.split == "train"].session_id))
    det.calibrate(pay, sessions, set(sessions[sessions.split == "calibration"].session_id), 0.001)
    L += ["", "## 4. Operating point: per-cohort conformal thresholds at alpha = 0.1% (payment-score alarms only)", "",
          "| Split | Sessions with a payment | Scam recall (payment score) | False alarms on legit | Session accuracy |", "|---|---|---|---|---|"]
    for n in ("train", "calibration", "validation"):
        d = split_rows(pay, sessions, n)
        d["score"] = det.score(d)
        d["thr"] = d.age_band.map(det.thr)
        s = d.groupby("session_id").agg(score=("score", "max"), thr=("thr", "first"), label=("label", "first"))
        alarm = s.score >= s.thr
        scam, leg = s.label == "scam", s.label == "legit"
        acc = ((alarm & scam) | (~alarm & leg)).mean()
        L.append(f"| {n} | {len(s):,} | {alarm[scam].mean():.1%} ({int(alarm[scam].sum())}/{int(scam.sum())}) | "
                 f"{alarm[leg].mean():.3%} ({int(alarm[leg].sum())}/{int(leg.sum())}) | {acc:.2%} |")
    L += ["", "Train false alarms are optimistic by construction only for the threshold sets calibrated on a *different* split; the calibration row is the data the thresholds were set on. "
          "Validation is the honest row. The full detector also has two rules (sideload during call, long session) which catch scams with no payment at all; their effect is in `detector_report.md`.", ""]

    # 5. comparison with a nonlinear model, on the same 16 features (not shipped)
    gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=SEED).fit(train[sd.FEATURES], ytr)
    L += ["## 5. Sanity check: gradient boosting on the same features (not shipped)", "",
          "| Split | Logistic AUC | Boosting AUC | Logistic AP | Boosting AP |", "|---|---|---|---|---|"]
    for n, d in (("validation", val),):
        y = (d.label == "scam").astype(int)
        pl = lr.predict_proba(sc.transform(d[sd.FEATURES]))[:, 1]
        pg = gb.predict_proba(d[sd.FEATURES])[:, 1]
        L.append(f"| {n} | {roc_auc_score(y, pl):.4f} | {roc_auc_score(y, pg):.4f} | {average_precision_score(y, pl):.4f} | {average_precision_score(y, pg):.4f} |")
    L += ["", "If boosting is not clearly better, the logistic model is not leaving accuracy on the table on these features, and it keeps the on-device port tiny, deterministic and explainable. "
          "Because the data is simulated, a nonlinear model could also just learn the simulator's quirks, so a better score here would not by itself justify switching.", ""]

    # 6. learned weights
    w = pd.Series(lr.coef_[0], index=sd.FEATURES).sort_values(ascending=False)
    L += ["## 6. Learned weights (standardised coefficients; intercept %.3f)" % lr.intercept_[0], "", "| Feature | Weight |", "|---|---|"]
    L += [f"| {k} | {v:+.3f} |" for k, v in w.items()]
    shipped = json.loads((ROOT / "detector" / "src" / "main" / "resources" / "model.json").read_text())
    diff = float(np.max(np.abs(np.array(shipped["logistic"]["coef"]) - lr.coef_[0])))
    L += ["", f"Max difference from the coefficients in `model.json`: {diff:.2e} (should be ~0: this script trains the same model).", "",
          f"Training run took {time.time() - t0:.0f} s on CPU (scikit-learn {__import__('sklearn').__version__})."]
    out = ROOT / "detector" / "training_report.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
