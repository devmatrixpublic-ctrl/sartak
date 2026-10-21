#!/usr/bin/env python3
"""IEEE-CIS benchmark track (Vesta, real e-commerce transactions): tests Satark's payment-context component.

Needs Kaggle's train_transaction.csv (and optionally train_identity.csv). The competition's test labels are
hidden, so this uses a time-ordered split of the labelled train file:
    first 60% by TransactionDT -> fit, next 20% -> calibration, last 20% -> test.

It reports three things:
  1. Full-feature gradient-boosted baseline AUC (a sanity reference for "competitive on real data").
  2. Ablation of the §6.4 design choice: amount deviation as a robust z-score (median/MAD) vs a classic z (mean/SD),
     per card, using statistics from the fit period only. Does the robust version detect better?
  3. Split-conformal check: is the empirical false-positive rate on the test period close to the target alpha?

What it does NOT show: scam detection. There are no calls or app signals in IEEE-CIS.
Usage: python ieee_cis_benchmark.py --train train_transaction.csv [--identity train_identity.csv] --out data/ieee_cis_report.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


def conformal_threshold(legit_scores: np.ndarray, alpha: float) -> float:
    s = np.sort(legit_scores)
    k = int(np.ceil((len(s) + 1) * (1 - alpha)))
    return float(s[min(k, len(s)) - 1])


def amount_z(df: pd.DataFrame, fit: np.ndarray, robust: bool) -> np.ndarray:
    """Per-card amount deviation using fit-period statistics only (no look-ahead into calibration/test)."""
    f = df.loc[fit, ["card1", "TransactionAmt"]]
    if robust:
        center = f.groupby("card1").TransactionAmt.median()
        spread = f.groupby("card1").TransactionAmt.apply(lambda x: (x - x.median()).abs().median() * 1.4826)
        g_center, g_spread = f.TransactionAmt.median(), (f.TransactionAmt - f.TransactionAmt.median()).abs().median() * 1.4826
    else:
        center = f.groupby("card1").TransactionAmt.mean()
        spread = f.groupby("card1").TransactionAmt.std()
        g_center, g_spread = f.TransactionAmt.mean(), f.TransactionAmt.std()
    c = df.card1.map(center).fillna(g_center).to_numpy()
    s = df.card1.map(spread).fillna(g_spread).to_numpy()
    s = np.where((s <= 0) | np.isnan(s), g_spread, s)
    return (df.TransactionAmt.to_numpy() - c) / s


def paired_bootstrap_auc_diff(y, s1, s2, n_boot=300, seed=0):
    """95% CI for AUC(s1) - AUC(s2) on the same test rows."""
    rng = np.random.default_rng(seed)
    n, d = len(y), []
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        if y[i].min() == y[i].max():
            continue
        d.append(roc_auc_score(y[i], s1[i]) - roc_auc_score(y[i], s2[i]))
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def fit_auc(X: pd.DataFrame, y: np.ndarray, fit, test) -> tuple[float, HistGradientBoostingClassifier]:
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, random_state=0,
                                       categorical_features="from_dtype").fit(X[fit], y[fit])
    return roc_auc_score(y[test], m.predict_proba(X[test])[:, 1]), m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--identity", type=Path, default=None)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--out", type=Path, default=Path("data/ieee_cis_report.md"))
    a = ap.parse_args()

    df = pd.read_csv(a.train)
    for c in df.select_dtypes("float64").columns:  # halve memory: 590k x ~400 columns
        df[c] = df[c].astype("float32")
    need = {"TransactionID", "isFraud", "TransactionDT", "TransactionAmt", "card1"}
    if not need.issubset(df.columns) or df["isFraud"].nunique() < 2:
        raise SystemExit(f"{a.train} is not a labelled IEEE-CIS train file (need columns {sorted(need)} "
                         "with real 0/1 labels). sample_submission.csv cannot be used.")
    if a.identity:
        df = df.merge(pd.read_csv(a.identity), on="TransactionID", how="left")
    df = df.sort_values("TransactionDT").reset_index(drop=True)
    y = df["isFraud"].to_numpy()
    n = len(df)
    fit, cal, test = np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool)
    fit[: int(0.6 * n)] = True
    cal[int(0.6 * n): int(0.8 * n)] = True
    test[int(0.8 * n):] = True
    hour = ((df.TransactionDT // 3600) % 24).to_numpy()

    # 1. full-feature baseline
    feats = df.drop(columns=["TransactionID", "isFraud", "TransactionDT"])
    obj = [c for c in feats.columns if feats[c].dtype == object or str(feats[c].dtype) in ("str", "string")]
    low = [c for c in obj if feats[c].nunique() <= 60]
    X_full = feats.drop(columns=[c for c in obj if c not in low])
    for c in low:  # native categorical support instead of one-hot (memory)
        X_full[c] = X_full[c].astype("category")
    auc_full, m_full = fit_auc(X_full, y, fit, test)

    # 2. robust vs classic amount deviation (small, Satark-style payment-context model)
    base = pd.DataFrame({"log_amt": np.log1p(df.TransactionAmt), "hour": hour})
    if "ProductCD" in df:
        base["ProductCD"] = df.ProductCD.astype("category")
    res, scores = {}, {}
    for name, robust in (("median/MAD (Satark §6.4)", True), ("mean/SD (classic)", False)):
        X = base.assign(amt_z=amount_z(df, fit, robust))
        res[name], m = fit_auc(X, y, fit, test)
        scores[name] = m.predict_proba(X[test])[:, 1]
    names = list(res)
    lo, hi = paired_bootstrap_auc_diff(y[test], scores[names[0]], scores[names[1]])

    # 3. conformal check on the full model
    s_cal = m_full.predict_proba(X_full[cal])[:, 1]
    s_te = m_full.predict_proba(X_full[test])[:, 1]
    thr = conformal_threshold(s_cal[y[cal] == 0], a.alpha)
    fpr = (s_te[y[test] == 0] > thr).mean()
    rec = (s_te[y[test] == 1] > thr).mean()

    lines = [
        "# IEEE-CIS benchmark track", "",
        f"Data: {n:,} labelled transactions, fraud rate {y.mean():.2%}. Time-ordered split 60/20/20 "
        "(competition test labels are hidden, so the labelled train file is split by time).", "",
        "## 1. Full-feature baseline", "",
        f"- Test AUC: **{auc_full:.3f}**. Compare with published IEEE-CIS baselines (e.g. Amazon Fraud Dataset Benchmark), "
        "noting that split protocols differ between papers.", "",
        "## 2. Design-choice ablation: robust vs classic amount deviation", "",
        "Same small model (log amount, hour, product code, per-card amount deviation); only the deviation statistic changes.", "",
        "| Amount deviation | Test AUC |", "|---|---|"]
    lines += [f"| {k} | {v:.3f} |" for k, v in res.items()]
    diff = res[names[0]] - res[names[1]]
    if lo > 0:
        verdict = f"**median/MAD is better** (difference {diff:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}] excludes 0)."
    elif hi < 0:
        verdict = f"**mean/SD is better** (difference {diff:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}]). Revisit §6.4."
    else:
        verdict = (f"**No significant difference** (difference {diff:+.4f}, 95% CI [{lo:+.4f}, {hi:+.4f}] includes 0). "
                   "On this data the robust statistic costs nothing; its case rests on resistance to single outliers, not on AUC.")
    lines += ["", f"Paired bootstrap (300 resamples of the test period): {verdict}", "",
              "## 3. Conformal false-positive check", "",
              "| Target FPR (α) | Empirical FPR on test | Recall at that threshold |", "|---|---|---|",
              f"| {a.alpha:.3f} | {fpr:.3f} | {rec:.3f} |", "",
              "A gap between target and empirical FPR indicates drift over time; the design recalibrates on a rolling window.", "",
              "## Scope", "",
              "- This validates the payment-context component and the calibration method on real data. It does not measure scam "
              "detection (no call or app signals in IEEE-CIS).",
              "- Licence: Kaggle competition rules — confirm that use outside the competition is permitted before publishing results.", ""]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
