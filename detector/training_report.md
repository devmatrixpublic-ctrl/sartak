# Satark detector: training report

Simulated data (SatarkSim v2). Everything here is about the model's fit on simulated sessions, not real-world accuracy.

## 1. Data

| Split | Payment rows | Scam rows (true label) | Sessions |
|---|---|---|---|
| train | 38,425 | 7,986 | 31,474 |
| calibration | 12,981 | 2,649 | 10,669 |
| validation | 12,545 | 2,530 | 10,356 |

Training target: `label_observed` (2% of labels deliberately flipped). Rows are payment attempts; the 16 features are in `contracts`/`model.json` order. Class balance in training is 21.8% scam, so the logistic model is unweighted: the decision threshold comes from conformal calibration on legitimate sessions, not from 0.5.

## 2. Regularisation chosen on the calibration split

| C | Train log-loss | Calibration log-loss | Calibration AUC | Calibration AP |
|---|---|---|---|---|
| 0.01 | 0.1183 | 0.1265 | 0.9997 | 0.9988 |
| 0.1 | 0.1168 | 0.1254 | 0.9997 | 0.9989 |
| 1.0 | 0.1165 | 0.1251 | 0.9997 | 0.9989 |
| 10.0 | 0.1165 | 0.1250 | 0.9997 | 0.9989 |
| 100.0 | 0.1165 | 0.1250 | 0.9997 | 0.9989 |

Lowest calibration log-loss at C = **100.0**. The shipped model uses C = 1.0 (the reference's setting). They differ; changing C would change the weights, thresholds and the 36 expected vectors, so it was NOT applied. Treat it as a tuning option to decide on.

## 3. Shipped model (logistic regression, C = 1.0): metrics on every split

Payment-level discrimination (score every payment attempt; true label). Accuracy is shown at the probability cut 0.5 only to answer the question; it is not the operating point (the real threshold is conformal) and is dominated by the majority class.

| Split | AUC | Average precision | Accuracy @0.5 | Majority-class accuracy |
|---|---|---|---|---|
| train | 0.9998 | 0.9991 | 0.9930 | 0.7922 |
| calibration | 0.9997 | 0.9989 | 0.9913 | 0.7959 |
| validation | 0.9998 | 0.9990 | 0.9928 | 0.7983 |

## 4. Operating point: per-cohort conformal thresholds at alpha = 0.1% (payment-score alarms only)

| Split | Sessions with a payment | Scam recall (payment score) | False alarms on legit | Session accuracy |
|---|---|---|---|---|
| train | 31,474 | 92.1% (1678/1822) | 0.101% (30/29652) | 99.45% |
| calibration | 10,669 | 91.7% (550/600) | 0.089% (9/10069) | 99.45% |
| validation | 10,356 | 93.3% (539/578) | 0.112% (11/9778) | 99.52% |

Train false alarms are optimistic by construction only for the threshold sets calibrated on a *different* split; the calibration row is the data the thresholds were set on. Validation is the honest row. The full detector also has two rules (sideload during call, long session) which catch scams with no payment at all; their effect is in `detector_report.md`.

## 5. Sanity check: gradient boosting on the same features (not shipped)

| Split | Logistic AUC | Boosting AUC | Logistic AP | Boosting AP |
|---|---|---|---|---|
| validation | 0.9998 | 0.9998 | 0.9990 | 0.9993 |

If boosting is not clearly better, the logistic model is not leaving accuracy on the table on these features, and it keeps the on-device port tiny, deterministic and explainable. Because the data is simulated, a nonlinear model could also just learn the simulator's quirks, so a better score here would not by itself justify switching.

## 6. Learned weights (standardised coefficients; intercept -2.189)

| Feature | Weight |
|---|---|
| unk_x_newpayee | +1.718 |
| newpayee_x_amt | +1.660 |
| repeat_to_payee | +0.894 |
| install_sideload_during_unk | +0.843 |
| unk_call_active | +0.537 |
| watchlist_app | +0.520 |
| unk_video_active | +0.475 |
| install_play_during_unk | +0.436 |
| ocss_ordered | +0.353 |
| is_p2p | +0.319 |
| new_payee | +0.132 |
| robust_z_pos | +0.093 |
| mins_since_unk_log | -0.106 |
| log_amt_ratio | -0.178 |
| payee_added_after_unk | -0.609 |
| unk_contact_recent | -1.807 |

Max difference from the coefficients in `model.json`: 0.00e+00 (should be ~0: this script trains the same model).

Training run took 66 s on CPU (scikit-learn 1.9.1).
