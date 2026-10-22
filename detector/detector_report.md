# Satark detector report (M2)

**All numbers below are from SatarkSim v2, a simulator. They show the detection logic separates the simulated playbooks and hard negatives; they do not measure real-world accuracy.** Scam event sequences and timings are design assumptions (no public data of real coached-scam sequences exists), and legitimate behaviour is fitted to a few published aggregates (see the research report). The sealed held-out cases were not used.

Reproduce: `python detector/reference/satark_detector.py --data data/satarksim --alpha 0.001 --out <path>` regenerates sections 2-6 and 8 exactly (checked: identical to the shipped report). Section 7 needs the raw Kaggle UPI and NPCI files, which are not in the repo, and is carried over from the shipped report, not re-run.

## 1. Headline (validation split, 10,465 sessions: 578 scams, 9,887 legitimate), with 95% intervals

| Metric | Result | 95% CI (Clopper-Pearson) | Plan target | Met? |
|---|---|---|---|---|
| Scam recall (any alarm) | 540/578 = **93.4%** | 91.1% - 95.3% | >= 93% | Point estimate yes; the interval's lower end is below 93% |
| Interdicted (alarm at or before first payment) | 487/578 = **84.3%** | 81.0% - 87.1% | none | n/a |
| False alarms on legitimate sessions | 11/9,887 = **0.111%** | 0.056% - 0.199% | <= 0.1% | **Point estimate is slightly above 0.1%; the interval contains both sides, so the target is neither shown nor refuted** |
| Median lead time before first payment | 19.1 min | - | none | n/a |
| Naive co-occurrence baseline | recall 53.1%, false alarms 3.9% | - | - | Satark is far better on both |

Ten of the 11 false alarms are the *genuine family emergency* hard negative (10/131 = 7.6%); the other is one plain payment. That case is built to look identical to the family-emergency scam, so it is the expected weak spot.

## 2. Per playbook

| Playbook | n | Naive recall | **Satark recall** | Interdicted | Main mechanism |
|---|---|---|---|---|---|
| digital_arrest | 91 | 0.0% | **98.9%** | 97.8% | long_session |
| family_emergency_scam | 76 | 89.5% | **57.9%** | 27.6% | payment_score |
| malicious_apk | 187 | 25.7% | **97.9%** | 93.0% | sideload_during_call |
| remote_access | 170 | 80.6% | **100.0%** | 88.8% | payment_score |
| screen_share | 54 | 100.0% | **98.1%** | 96.3% | payment_score |

The family-emergency scam (57.9% recall, 27.6% interdicted) remains the weak playbook. The optional experiment to improve it (a first-payment-to-new-payee-over-N-times-median rule) was not done.

## 3. False alarms by legit kind (hard negatives)

| Legit kind | n | Naive | **Satark** |
|---|---|---|---|
| call_then_known_payment | 2651 | 0.0% | **0.0%** |
| hn_cod_delivery | 192 | 91.1% | **0.0%** |
| hn_family_emergency | 131 | 90.8% | **7.6%** |
| hn_family_video | 139 | 0.0% | **0.0%** |
| hn_festival_spike | 96 | 0.0% | **0.0%** |
| hn_legit_remote | 139 | 0.0% | **0.0%** |
| hn_long_gap | 144 | 0.0% | **0.0%** |
| hn_out_of_order | 144 | 61.1% | **0.0%** |
| hn_rent_salary_day | 197 | 0.0% | **0.0%** |
| plain_payment | 6054 | 0.0% | **0.0%** |

## 4. Precision at the real base rate

False alarms of about 0.11% are rates **among legitimate sessions in the simulator**. At a real fraud rate of about 6.8e-6 per transaction (a rough prior derived from Indian fraud counts and UPI volume; second-hand, order of magnitude only), with recall 93.4% and false alarms 0.111%, precision is about **0.57%, roughly one true alert per 176 alerts**. A 0.1% false-alarm target is not a precision target. Say this before anyone quotes "0.1%".

## 5. Calibration and fairness (false-alarm guarantee)

Target false-pause rate per cohort: α = 0.1%. Payment-score alarms only (rule alarms reported separately).

| Age band | Threshold | Legit validation sessions | Empirical false-alarm rate (one-sided binomial test that the true rate exceeds α) |
|---|---|---|---|
| 18-35 | 0.92 | 4,404 | 0.1% (5 sessions; p = 0.45 vs α) |
| 36-59 | 0.77 | 3,990 | 0.2% (6 sessions; p = 0.21 vs α) |
| 60+ | 1.53 | 1,493 | 0.0% (0 sessions; p = 1.00 vs α) |

Rule alarms (sideload-during-call, long-session) on legit sessions: 0.0%. **Caveat:** SatarkSim contains no genuine sideloads or long unknown-number video calls, so this is optimistic; measure it on real devices before claiming it.

Each cohort's threshold is the k-th smallest legitimate calibration score, k = ceil((n+1)(1-alpha)); `detector/src/main/resources/model.json` records n and k per cohort. Calibration set sizes are 4,512 (18-35), 4,246 (36-59) and 1,398 (60+). For 60+, k equals n, so the threshold is the single highest calibration score: valid but noisy. The pooled threshold is exported as the fallback for an unknown age band.

## 6. Drift (calibrate on weeks 0–5, test on weeks 6–11)

After a new remote-access app appears and the malicious-APK share rises: recall **91.4%**, false alarms **0.0%**. (A static watch-list's recall on remote-access scams falls 1.00 → 0.49 in the same period.)

## 7. Timing sensitivity (trained at 1×, tested on data rebuilt at other timing scales)

| Timing scale | Satark recall | Naive recall |
|---|---|---|
| 0.5× | 93.4% | 69.7% |
| 1.0× | 93.4% | 53.1% |
| 2.0× | 93.3% | 40.1% |

Satark's install-during-call and long-session mechanisms do not depend on time windows, so recall should move far less than the naive rule's.

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

## 9. On-device Kotlin port (this repo, `detector/`)

| Check | Result |
|---|---|
| `model.json` reproduces reference scores | max difference 1.8e-15 over 12,545 validation payments (target <= 1e-9) |
| 36 test vectors (decision, level, mechanism, alarm time, interdiction) | 36/36 match exactly |
| 732 golden simulated sessions (every kind and playbook; 36 vectors included) | all session decisions match; 1,257 payments: features and scores within 1.8e-15 |
| Determinism (same input twice) | identical |
| Fuzz: 1,000 random or partial event streams (nulls, NaN/infinite/negative amounts, unordered times, unknown age bands) | no exceptions, no NaN scores |
| Missing signals (call-state events removed; call/install/package fields null) | valid decisions on all 36 vectors |
| Mutation check | disabling the sideload rule makes the vector and parity tests fail |

Not yet done: the instrumented run of the 36 vectors on the two physical phones (plan 2.7); this needs the Android app and devices. The Android SDK is not available in the build container, so `detector` is a plain Kotlin/JVM library; building it as an Android library module and consuming it from `app/` is for M1 to wire up.

## 10. Open items and decisions

- **Levels:** the reference only has an alarm. The detector emits `NONE` or `HARD`. `NUDGE` and `TRUSTED_CONTACT` (in `contracts/api.yaml`) are not produced; a nudge tier would be a new design with its own calibration.
- **Baseline:** the reference takes fixed per-user history statistics. The rolling last-50 median/MAD with an `n/(n+20)` blend toward a population prior is a design choice of the port, unit-tested but not validated on simulated or real data.
- **Session boundaries:** undefined by the reference; the app decides when to call `reset()`/`finish()`.
- **Rule false alarms:** SatarkSim has no genuine sideloads or long unknown-number video calls, so the 0% false-alarm rate of the two rules is untested against real behaviour.
- **Watch-list:** the model knows 3 remote-access apps (from `params.json`); drift shows a static list loses coverage. M1 owns the real list; unverified package names in the research notes must be checked on a device.
- **Tag:** `detector-freeze` is not set; it should be set only after the on-phone run and sign-off. M1 has run the 36 vectors 36/36 on an Android 15 emulator (JVM and instrumented, `app/e2e_log.md`); physical phones remain.
- **False-alarm target:** `detector/experiments/conformal_confidence.md` tried thresholds with a 90% confidence statement on the false-alarm rate: false alarms 0.040% (CI 0.011-0.104%) but recall 92.6% (CI 90.1-94.6%). Neither this nor the shipped thresholds meets both plan targets on SatarkSim; the choice is a team decision and the shipped model is unchanged.
- **Held-out baselines:** with no per-user history, `ops/heldout/run_heldout.py` scores each case as a brand-new user, as the phone does: the cold-start prior in `model.json` and an unknown age band (pooled threshold).
