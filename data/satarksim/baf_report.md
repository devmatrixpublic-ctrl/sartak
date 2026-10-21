# BAF benchmark track: calibration and fairness

Dataset: BAF Base.csv (1,000,000 applications, fraud rate 1.10%). Train months 0–4, calibrate month 5, test months 6–7. Model: gradient-boosted trees. Target false-positive rate α = 5%.

**Test AUC: 0.888**

## 1. Does the conformal threshold hold its promise?

| | Nominal FPR (α) | Empirical FPR on test | Recall at that threshold |
|---|---|---|---|
| Global threshold | 0.050 | 0.058 | 0.561 |

Note: the guarantee assumes exchangeability; BAF has month-to-month drift, so a small gap is expected and is exactly why the design recalibrates on a rolling window.

## 2. Fairness across age groups (FPR = legitimate applicants wrongly flagged)

| Thresholding | FPR <50 | FPR 50+ | Worst/best FPR ratio | Overall recall | Gate (≤1.5×) |
|---|---|---|---|---|---|
| One global threshold | 0.044 | 0.134 | 3.08× | 0.561 | FAIL |
| Mondrian (per group) | 0.058 | 0.063 | 1.10× | 0.529 | PASS |

Test legit applicants: <50 = 169,343, 50+ = 32,790. Recall by group (Mondrian): <50 0.536, 50+ 0.517.

## What to claim, and what not to

- Claim: *Satark's calibration method (split-conformal, per-cohort) was validated on BAF, a NeurIPS 2022 benchmark from real bank data: it held the false-alarm rate near target and closed the age-group gap.*
- Do not claim: that this measures scam detection. BAF is account-opening fraud.
- Licence: BAF is CC BY-NC-ND 4.0 (non-commercial, no redistribution of modified data).
