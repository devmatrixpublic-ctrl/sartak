# Satark reference detector: results on SatarkSim v2 (validation split)

Simulated data, not real-world accuracy. Trained on `label_observed` (2% noisy) from the train split; Hard-intervention thresholds per age cohort by split-conformal calibration on legit calibration sessions at α = 0.1%; evaluated on the true `label` of 10,465 validation sessions (578 scams). Held-out real cases NOT used.

## 1. Headline vs the naive baseline

| Metric | Naive co-occurrence rule | **Satark** |
|---|---|---|
| Scam recall (any alarm) | 53.1% | **93.4%** |
| Interdicted (alarm at or before first payment) | — | **84.3%** |
| False alarms on legit sessions | 3.9% | **0.1%** |
| Median lead time before first payment (interdicted scams) | — | **19.1 min** |

## 2. Per playbook

| Playbook | n | Naive recall | **Satark recall** | Interdicted | Main mechanism |
|---|---|---|---|---|---|
| digital_arrest | 91 | 0.0% | **98.9%** | 97.8% | long_session |
| family_emergency_scam | 76 | 89.5% | **57.9%** | 27.6% | payment_score |
| malicious_apk | 187 | 25.7% | **97.9%** | 93.0% | sideload_during_call |
| remote_access | 170 | 80.6% | **100.0%** | 88.8% | payment_score |
| screen_share | 54 | 100.0% | **98.1%** | 96.3% | payment_score |

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

## 4. The hardest pair: genuine family emergency vs family-emergency scam

Identical event sequence. Naive rule: flags 90.8% of genuine and 89.5% of scams (cannot separate). **Satark: flags 7.6% of genuine and catches 57.9% of scams** — separation comes from amount relative to the user's own baseline and repeat payments.

## 5. Calibration and fairness (false-alarm guarantee)

Target false-pause rate per cohort: α = 0.1%. Payment-score alarms only (rule alarms reported separately).

| Age band | Threshold | Legit validation sessions | Empirical false-alarm rate (one-sided binomial test that the true rate exceeds α) |
|---|---|---|---|
| 18-35 | 0.92 | 4,404 | 0.1% (5 sessions; p = 0.45 vs α) |
| 36-59 | 0.77 | 3,990 | 0.2% (6 sessions; p = 0.21 vs α) |
| 60+ | 1.53 | 1,493 | 0.0% (0 sessions; p = 1.00 vs α) |

Rule alarms (sideload-during-call, long-session) on legit sessions: 0.0%. **Caveat:** SatarkSim contains no genuine sideloads or long unknown-number video calls, so this is optimistic; measure it on real devices before claiming it.

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

## 9. What this does and does not show

- Shows the v6 design separates the playbooks and hard negatives that a co-occurrence rule cannot, on simulated data.
- Does not show real-world accuracy: SatarkSim timings and amounts are assumptions; only a consented pilot can.
- The held-out real cases remain frozen for the team's single final run.
