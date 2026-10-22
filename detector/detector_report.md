# Satark detector report (M2)

**All numbers below are from SatarkSim v2, a simulator. They show the detection logic separates the simulated scam playbooks and hard negatives; they do not measure real-world accuracy.** Scam event sequences and timings are design assumptions (no public data of real coached-scam sequences exists), and legitimate behaviour is fitted to a few published aggregates. The sealed held-out cases were not used.

Regenerate: `python detector/tools/make_detector_report.py` (fresh reference run; sections 2-6 and 8 are the reference's own output). Thresholds are calibrated at alpha' = 0.08%, a margin below the 0.1% target (see section 4).

## 1. Headline (validation split, 10,465 sessions: 578 scams, 9,887 legitimate), with 95% intervals

| Metric | Result | 95% CI (Clopper-Pearson) | Plan target | Met? |
|---|---|---|---|---|
| Scam recall (any alarm) | 538/578 = **93.1%** | 90.7 - 95.0% | >= 93% | Point estimate yes; the interval's lower end is below 93% |
| Interdicted (alarm at or before first payment) | 485/578 = **83.9%** | 80.7 - 86.8% | none | n/a |
| False alarms on legitimate sessions | 7/9,887 = **0.071%** | 0.028 - 0.146% | <= 0.1% | Point estimate yes; the interval's upper end is above 0.1% |
| Median lead time before first payment | 20.2 min | - | none | n/a |
| Naive co-occurrence baseline | recall 53.1%, false alarms 3.9% | - | - | Satark is far better on both |

**Cross-validation (independent of validation).** Over 5 user-level splits of the train and calibration data, alpha' = 0.0008 gave false alarms 28/40359 = 0.069% [0.046, 0.100] and recall 91.83% [90.65, 92.91] (`detector/experiments/calibration_margin_cv.md`). Recall in cross-validation is about a point lower than on this validation split, so treat the 93% target as borderline, not secured.

6 of the 7 false alarms are the *genuine family emergency* hard negative (6/131 = 4.6%); that case is built to look identical to the family-emergency scam, so it is the expected weak spot. The family-emergency scam is caught 43/76 = 56.6% (20/76 before the first payment).

## 2. Per playbook

| Playbook | n | Naive recall | **Satark recall** | Interdicted | Main mechanism |
|---|---|---|---|---|---|
| digital_arrest | 91 | 0.0% | **98.9%** | 97.8% | long_session |
| family_emergency_scam | 76 | 89.5% | **56.6%** | 26.3% | payment_score |
| malicious_apk | 187 | 25.7% | **97.9%** | 93.0% | sideload_during_call |
| remote_access | 170 | 80.6% | **99.4%** | 88.2% | payment_score |
| screen_share | 54 | 100.0% | **98.1%** | 96.3% | payment_score |

## 3. False alarms by legit kind (hard negatives)

| Legit kind | n | Naive | **Satark** |
|---|---|---|---|
| call_then_known_payment | 2651 | 0.0% | **0.0%** |
| hn_cod_delivery | 192 | 91.1% | **0.0%** |
| hn_family_emergency | 131 | 90.8% | **4.6%** |
| hn_family_video | 139 | 0.0% | **0.0%** |
| hn_festival_spike | 96 | 0.0% | **0.0%** |
| hn_legit_remote | 139 | 0.0% | **0.0%** |
| hn_long_gap | 144 | 0.0% | **0.0%** |
| hn_out_of_order | 144 | 61.1% | **0.0%** |
| hn_rent_salary_day | 197 | 0.0% | **0.0%** |
| plain_payment | 6054 | 0.0% | **0.0%** |

## 4. Why alpha' is 0.08% and not 0.1%, and what precision looks like

Conformal calibration at alpha = 0.001 makes the **expected** false-alarm rate 0.1%, but one calibration draw lands above or below it. Cross-validation (`detector/experiments/calibration_margin_cv.md`) measured calibration at alpha = 0.001 giving **0.107%** false alarms, just over the target, in agreement with the earlier validation figure of 0.111%. Following a rule fixed before the run (largest alpha' with cross-validated false alarms <= 0.09%), alpha' = 0.0008 was chosen. Two other options were tried and not adopted: thresholds with a 90% confidence statement (`detector/experiments/conformal_confidence.md`: false alarms 0.040%, recall 92.6%) and session-total features (`detector/experiments/session_total_features.md`: no gain).

False alarms of 0.07% are rates **among legitimate sessions in the simulator**. At a real fraud rate of about 6.8e-06 per transaction (a rough, second-hand prior, order of magnitude only), with recall 93.1% and false alarms 0.071%, precision is about **0.89%, roughly one true alert per 113 alerts**. A 0.1% false-alarm target is not a precision target.

## 5. Calibration and fairness (false-alarm guarantee)

Target false-pause rate per cohort: 0.10%. Thresholds are calibrated at the margin α' = 0.08% so that sampling noise does not push the realised rate over the target (see `detector/experiments/calibration_margin_cv.md`). Payment-score alarms only (rule alarms reported separately).

| Age band | Threshold | Legit validation sessions | Empirical false-alarm rate (one-sided binomial test that the true rate exceeds the 0.10% target) |
|---|---|---|---|
| 18-35 | 1.03 | 4,404 | 0.1% (3 sessions; p = 0.82 vs target) |
| 36-59 | 1.01 | 3,990 | 0.1% (4 sessions; p = 0.56 vs target) |
| 60+ | 1.53 | 1,493 | 0.0% (0 sessions; p = 1.00 vs target) |

Rule alarms (sideload-during-call, long-session) on legit sessions: 0.0%. **Caveat:** SatarkSim contains no genuine sideloads or long unknown-number video calls, so this is optimistic; measure it on real devices before claiming it.

Each cohort's threshold is the k-th smallest legitimate calibration score, k = ceil((n+1)(1-alpha')); `detector/src/main/resources/model.json` records n and k per cohort. For the 60+ cohort (n = 1,398) k equals n, so its threshold is the single highest calibration score: valid but noisy, and unchanged by the margin. The pooled threshold is exported as the fallback for an unknown age band.

## 6. Drift (calibrate on weeks 0–5, test on weeks 6–11)

After a new remote-access app appears and the malicious-APK share rises: recall **91.4%**, false alarms **0.0%**. (A static watch-list's recall on remote-access scams falls 1.00 → 0.49 in the same period.)

## 7. Timing sensitivity

Not re-run at the new calibration (it needs the raw Kaggle UPI and NPCI files); the earlier table, computed at alpha = 0.001, is in `data/satarksim/detector_sensitivity_alpha0.001.md`.

## 8. Learned weights of evidence (standardised logistic coefficients)

| Feature | Weight |
|---|---|
| unk_x_newpayee | +1.72 |
| newpayee_x_amt | +1.66 |
| repeat_to_payee | +0.89 |
| install_sideload_during_unk | +0.84 |
| unk_call_active | +0.54 |
| watchlist_app | +0.52 |
| unk_video_active | +0.48 |
| install_play_during_unk | +0.44 |
| ocss_ordered | +0.35 |
| is_p2p | +0.32 |
| new_payee | +0.13 |
| robust_z_pos | +0.09 |
| mins_since_unk_log | -0.11 |
| log_amt_ratio | -0.18 |
| payee_added_after_unk | -0.61 |
| unk_contact_recent | -1.81 |

Read these jointly, not one by one: several features are correlated by construction (e.g. `unk_contact_recent` and `unk_x_newpayee`), so individual signs can flip. For explanations (L5), each alarm cites its own top terms by contribution (weight × standardised value), which is well-defined per decision.

## 9. On-device Kotlin port (`detector/`)

| Check | Result |
|---|---|
| `model.json` reproduces reference scores | max difference ~1.8e-15 over the validation payments (target <= 1e-9); `detector/tools/export_model.py` asserts it |
| 36 test vectors (decision, level, mechanism, alarm time, interdiction) | 36/36 match exactly (`ReferenceVectorsTest`); unchanged by the calibration margin |
| 732 golden simulated sessions | every session decision matches; payment features and scores within ~1.8e-15 (`GoldenParityTest`) |
| Determinism, 1,000-stream fuzz, missing signals, explainer, integration hazards | pass (`cd detector && gradle test`) |
| Cross-module run | the Kotlin detector's decisions drive the real server in `ops/e2e/run_e2e.py` (57 checks) |

Not yet done: the instrumented run of the 36 vectors on the two **physical** phones (M1 has run it 36/36 on an Android 15 emulator, `app/e2e_log.md`). The detector is a plain Kotlin/JVM library consumed by `app/` through `includeBuild`, not an Android library module.

## 10. Open items

- **Levels:** the detector emits `NONE` or `HARD`. `NUDGE` and `TRUSTED_CONTACT` (in `contracts/api.yaml`) are not produced.
- **Baseline (tested, result is uncomfortable):** the rolling last-50 median/MAD with an `n/(n+20)` blend toward a population prior is a design choice of the port. `detector/experiments/baseline_cold_start.md` compares a mature personal history with a brand-new install (population prior for everyone), each recalibrated: recall 93.1% vs 94.8% and false alarms 0.071% vs 0.111%, with overlapping intervals. **SatarkSim therefore shows no benefit from personalised baselines**, and with this data it cannot show they are useless either: its scam amounts are far above any user's normal, so the amount baseline barely matters. Do not present "adaptive per-user thresholds" as a measured result; it remains a design hypothesis until real or better-simulated data tests it.
- **Session boundaries:** undefined by the reference; the app decides (`app/.../SessionPolicy.kt`).
- **Rule false alarms:** SatarkSim has no genuine sideloads or long unknown-number video calls, so the rules' 0% false-alarm rate is untested against real behaviour.
- **Unknown video origin:** the app infers it (`VideoOrigin`); the platform cannot say who is on a video call.
- **Tag:** `detector-freeze` is not set; set it only after the run on physical phones and sign-off.
