# SatarkSim v2 build report

Average-ticket source: official NPCI workbook (April-2024 to March-2025): ₹1,402. Timing scale: 1.0×.

## 1. Calibration against NPCI targets (regular legit payments)

| Quantity | Target | SatarkSim |
|---|---|---|
| P2M share of volume | 0.63 | 0.63 |
| P2M payments < ₹500 | 0.86 | 0.86 |
| P2P payments < ₹500 | 0.59 | 0.59 |
| Average ticket (₹) | 1402 | 1427 (sample; heavy tail varies by seed) |

## 1a. Per-user consistency (v1 bug fixed)

- Spearman correlation between each user's history median and the median of their session payments (4,085 users with ≥5 payments): **0.62**. In v1 this was ≈0 because amounts ignored the user.

## 1b. Can the false-pause target be certified per cohort?

Split-conformal needs ≥ 1/α − 1 = **999** legit calibration sessions per cohort (α = 0.1%).

| Age band | Legit calibration sessions | Enough? |
|---|---|---|
| 18-35 | 4512 | yes |
| 36-59 | 4246 | yes |
| 60+ | 1398 | yes |

## 2. Split integrity

- Users in more than one split: **0** (must be 0)

| Split | Legit | Scam |
|---|---|---|
| calibration | 10156 | 600 |
| train | 29957 | 1822 |
| validation | 9887 | 578 |

## 2a. Device noise applied

- Users without call state (OEM): 10.2% · without usage access: 5.0%
- Duplicate events: 1.9% · timestamp jitter on 20% of events (≤30 s)
- Observed labels flipped: 2.0%. **Train on `label_observed`; evaluate on `label`.**

## 3. Artefact probe

- AUC predicting scam from start hour alone: **0.511** (≈0.5 expected; hour is drawn independently of the label).
- Not probed, because they carry signal by design: age band (scams target older users), activity tier (scams are a larger share of low-activity users' sessions), and week (scam mix drifts after week 6). Never use age band as a feature.

## 3a. Realism check against Kaggle UPI 2024

- Classifier separating SatarkSim P2M rows from Kaggle P2M rows on hour + merchant category: **AUC 0.498** (≈0.5 = indistinguishable).
- Amounts are checked against NPCI quantiles in §1 instead: no row-level real UPI data exists to compare against.

## 4. Difficulty probe (naive rule, validation split)

Rule: unknown call + new payee + payment within 60 min of the call, order ignored. This is the baseline to beat.

- Recall: **0.53** · False-flag rate on legit: **0.039**

| Scam playbook | Naive recall |
|---|---|
| digital_arrest | 0.00 |
| family_emergency_scam | 0.89 |
| malicious_apk | 0.26 |
| remote_access | 0.81 |
| screen_share | 1.00 |

| Legit kind | Naive false-flag rate |
|---|---|
| call_then_known_payment | 0.00 |
| hn_cod_delivery | 0.91 |
| hn_family_emergency | 0.91 |
| hn_family_video | 0.00 |
| hn_festival_spike | 0.00 |
| hn_legit_remote | 0.00 |
| hn_long_gap | 0.00 |
| hn_out_of_order | 0.61 |
| hn_rent_salary_day | 0.00 |
| plain_payment | 0.00 |

`hn_family_emergency` vs `family_emergency_scam` is the hardest pair by design: same event sequence, differing only in amounts relative to the user and number of payments.

## 4a. Drift probe

Watch-list rule (unknown call + install of a named remote-access app) on remote-access scams: **1.00** recall before day 42, **0.49** after (a new app appears). A static watch-list decays; this is what the install-during-call signal and rolling recalibration are for. For drift tests, calibrate on weeks 0–5 and test on weeks 6–11.

## 5. Held-out set

- Copied untouched to `heldout/`. SHA-256: `3382c295484981f5b04abdfb3cc358f8114d1fcc9fa2cf5986b2f15bc813a475`. Not used in this build.

## 6. Provenance

- Every row is `linkage=synthetic`: SatarkSim shows the logic works on simulated data, not real-world accuracy.
- Scam timings and amounts are labelled assumptions in `params.json`; see `sensitivity_report.md`. They were deliberately NOT fitted to the held-out cases.
- ICFD-31k: umbrella names only. Kaggle UPI: hour-of-day and merchant mix only (amounts and fraud flag unused).
