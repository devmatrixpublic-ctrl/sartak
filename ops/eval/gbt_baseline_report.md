# Gradient-boosted baseline vs the logistic detector (simulated data)

**All numbers are from SatarkSim, a simulator. They say nothing about real-world accuracy.** Offline comparison only: nothing here runs on the phone and the detector is unchanged.

Same 16 features, same training sessions and `label_observed` labels (38,425 training payment rows), same per-age-band split-conformal calibration at alpha' = 0.08%. Only the model differs. GBT: scikit-learn `GradientBoostingClassifier`, {'n_estimators': 100, 'max_depth': 3, 'learning_rate': 0.1, 'subsample': 1.0, 'random_state': 0}; fixed in advance, not tuned on validation. Validation split, 578 scam and 9887 legitimate sessions.

| Model | Scam recall (95% CI) | False alarms on legitimate sessions (95% CI) |
|---|---|---|
| Logistic, payment score only | 92.7% (90.3%-94.7%) | 7/9887 = 0.071% (0.028%-0.146%) |
| Gradient boosted, payment score only | 96.0% (94.1%-97.5%) | 3/9887 = 0.030% (0.006%-0.089%) |
| Logistic + the two safety rules (the shipped detector) | 93.1% (90.7%-95.0%) | 7/9887 = 0.071% (0.028%-0.146%) |

Reading it: at the same calibrated false-alarm budget, the gradient-boosted model's recall is **+3.3 points** versus the logistic model on payment score alone. The two confidence intervals overlap, so this simulation does not show a real difference. The logistic model is the one on the device because it is a few dozen numbers, deterministic to the bit between Python and Kotlin, and each reason is a single weight times a value; a boosted ensemble would need a new Kotlin evaluator and a new explanation method.

## Which features the boosted model leaned on

| Feature | Importance |
|---|---|
| newpayee_x_amt | 0.931 |
| repeat_to_payee | 0.020 |
| install_play_during_unk | 0.019 |
| is_p2p | 0.006 |
| mins_since_unk_log | 0.005 |
| unk_video_active | 0.004 |
| install_sideload_during_unk | 0.003 |
| watchlist_app | 0.003 |

False alarms: 3 (boosted) vs 7 (logistic) out of 9887 legitimate sessions; with counts this small the difference is within noise.

Caveats: one simulator, one seed, one split. The scam sequences in SatarkSim are design assumptions, so a flexible model may be fitting the simulator's own rules rather than anything that holds for real scams. The result says the boosted model is not worse here; it does not say it would be better on real traffic.
