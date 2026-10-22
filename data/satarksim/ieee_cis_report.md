# IEEE-CIS benchmark track

Data: 590,540 labelled transactions, fraud rate 3.50%. Time-ordered split 60/20/20 (competition test labels are hidden, so the labelled train file is split by time).

## 1. Full-feature baseline

- Test AUC: **0.888**. Compare with published IEEE-CIS baselines (e.g. Amazon Fraud Dataset Benchmark), noting that split protocols differ between papers.

## 2. Design-choice ablation: robust vs classic amount deviation

Same small model (log amount, hour, product code, per-card amount deviation); only the deviation statistic changes.

| Amount deviation | Test AUC |
|---|---|
| median/MAD (Satark §6.4) | 0.761 |
| mean/SD (classic) | 0.759 |

Paired bootstrap (300 resamples of the test period): **No significant difference** (difference +0.0024, 95% CI [-0.0013, +0.0062] includes 0). On this data the robust statistic costs nothing; its case rests on resistance to single outliers, not on AUC.

## 3. Conformal false-positive check

| Target FPR (α) | Empirical FPR on test | Recall at that threshold |
|---|---|---|
| 0.050 | 0.055 | 0.629 |

A gap between target and empirical FPR indicates drift over time; the design recalibrates on a rolling window.

## Scope

- This validates the payment-context component and the calibration method on real data. It does not measure scam detection (no call or app signals in IEEE-CIS).
- Licence: Kaggle competition rules — confirm that use outside the competition is permitted before publishing results.
