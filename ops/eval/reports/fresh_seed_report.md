# Results on fresh simulator draws (Person B, phase 1)

**Simulated data throughout.** This is not real-world accuracy and not the sealed held-out run. It re-draws the simulator with new seeds (never seen by the detector) and scores every session with the detector exactly as shipped: nothing was re-tuned. Seeds: 777001, 777002, 777003. Built in 430 s.

The fresh sets lack the Kaggle hour/merchant mix and the NPCI average-ticket calibration the shipped set used (those files are not in the repository), so they also carry a small distribution shift. That is a feature of this test, not a flaw to hide.

## 1. Headline

| Dataset | Scam recall (95% CI) | False alarms on legit (95% CI) | Precision as simulated | Precision at 1 scam in 1,000 | Precision at 1 in 10,000 |
|---|---|---|---|---|---|
| Shipped validation split (reference) | 538/578 = 93.1% (90.7% - 95.0%) | 7/9887 = 0.071% (0.028% - 0.146%) | 98.7% | 56.82% | 11.620% |
| Fresh seed 777001 | 2733/3000 = 91.1% (90.0% - 92.1%) | 32/50000 = 0.064% (0.044% - 0.090%) | 98.8% | 58.76% | 12.462% |
| Fresh seed 777002 | 2730/3000 = 91.0% (89.9% - 92.0%) | 35/50000 = 0.070% (0.049% - 0.097%) | 98.7% | 56.55% | 11.505% |
| Fresh seed 777003 | 2705/3000 = 90.2% (89.0% - 91.2%) | 27/50000 = 0.054% (0.036% - 0.079%) | 99.0% | 62.57% | 14.310% |
| **Fresh seeds pooled** | 8168/9000 = 90.8% (90.1% - 91.3%) | 94/150000 = 0.063% (0.051% - 0.077%) | 98.9% | 59.18% | 12.651% |

Read the precision columns carefully: with a false-alarm rate of 0.063% the share of alarms that are real scams collapses as scams get rarer (59.2% at one scam in 1,000 sessions). That is arithmetic, not a bug, and it is why the app warns and holds rather than blocks. Interdicted before the first payment: 7462/9000 = 82.9%.

## 2. Recall by scam playbook

| Playbook | Fresh seeds, pooled: caught | Recall (95% CI) | Shipped validation split: caught | Recall |
|---|---|---|---|---|
| digital_arrest | 1589/1604 | 99.1% (98.5% - 99.5%) | 90/91 | 98.9% |
| family_emergency_scam | 542/1234 | 43.9% (41.1% - 46.7%) | 43/76 | 56.6% |
| malicious_apk | 2764/2841 | 97.3% (96.6% - 97.9%) | 183/187 | 97.9% |
| remote_access | 2388/2408 | 99.2% (98.7% - 99.5%) | 169/170 | 99.4% |
| screen_share | 885/913 | 96.9% (95.6% - 98.0%) | 53/54 | 98.1% |

## 3. False alarms by kind of legitimate session (pooled)

Look-alike sessions (`hn_*`) are built to resemble scams: a real family emergency, a real remote-support call, rent day.

| Session kind | Sessions | False alarms | Rate |
|---|---|---|---|
| hn_family_emergency | 2234 | 88 | 3.939% |
| plain_payment | 93297 | 6 | 0.006% |
| hn_cod_delivery | 3002 | 0 | 0.000% |
| call_then_known_payment | 38679 | 0 | 0.000% |
| hn_festival_spike | 1489 | 0 | 0.000% |
| hn_family_video | 2218 | 0 | 0.000% |
| hn_legit_remote | 1837 | 0 | 0.000% |
| hn_long_gap | 2318 | 0 | 0.000% |
| hn_out_of_order | 2191 | 0 | 0.000% |
| hn_rent_salary_day | 2735 | 0 | 0.000% |

Which rule fired on the false alarms: payment_score 94.

## 4. What the model gets wrong: missed scams

832 scam sessions were missed. The cause below is a RULE-BASED TAG (first matching reason in a fixed order), so it directs attention but is not proof.

| Likely cause | Missed | Share |
|---|---|---|
| score below the age-band threshold (the payment looked too ordinary) | 575 | 69% |
| phone does not expose call state (the unknown call is invisible) | 207 | 25% |
| usage access off (foreground apps invisible) | 43 | 5% |
| remote-access app that is not on the watch-list (new from week 6) | 7 | 1% |

### Named cases (up to 3 per playbook and cause; the full list is in the JSON next to this report)

| Dataset | Session | Playbook | Age band | Week | Likely cause | Short of threshold |
|---|---|---|---|---|---|---|
| seed 777001 | S051905 | digital_arrest | 60+ | 4 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S051036 | digital_arrest | 60+ | 0 | usage access off (foreground apps invisible) |  |
| seed 777001 | S052164 | digital_arrest | 36-59 | 7 | usage access off (foreground apps invisible) |  |
| seed 777001 | S052624 | digital_arrest | 60+ | 3 | usage access off (foreground apps invisible) |  |
| seed 777001 | S050677 | family_emergency_scam | 36-59 | 5 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050688 | family_emergency_scam | 18-35 | 8 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050910 | family_emergency_scam | 18-35 | 1 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050004 | family_emergency_scam | 18-35 | 2 | score below the age-band threshold (the payment looked too ordinary) | 0.06 |
| seed 777001 | S050005 | family_emergency_scam | 60+ | 2 | score below the age-band threshold (the payment looked too ordinary) | 1.00 |
| seed 777001 | S050009 | family_emergency_scam | 60+ | 8 | score below the age-band threshold (the payment looked too ordinary) | 1.27 |
| seed 777001 | S050590 | family_emergency_scam | 60+ | 3 | usage access off (foreground apps invisible) |  |
| seed 777001 | S050621 | family_emergency_scam | 18-35 | 11 | usage access off (foreground apps invisible) |  |
| seed 777001 | S051363 | family_emergency_scam | 18-35 | 7 | usage access off (foreground apps invisible) |  |
| seed 777001 | S050314 | malicious_apk | 36-59 | 4 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050339 | malicious_apk | 36-59 | 3 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050343 | malicious_apk | 60+ | 10 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050204 | remote_access | 60+ | 2 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050776 | remote_access | 18-35 | 7 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S052126 | remote_access | 60+ | 5 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050122 | remote_access | 60+ | 9 | remote-access app that is not on the watch-list (new from week 6) |  |
| seed 777001 | S050980 | remote_access | 60+ | 6 | remote-access app that is not on the watch-list (new from week 6) |  |
| seed 777001 | S051231 | remote_access | 36-59 | 8 | remote-access app that is not on the watch-list (new from week 6) |  |
| seed 777001 | S050338 | screen_share | 60+ | 11 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050638 | screen_share | 36-59 | 0 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777001 | S050906 | screen_share | 60+ | 3 | phone does not expose call state (the unknown call is invisible) |  |
| seed 777002 | S050722 | screen_share | 60+ | 11 | score below the age-band threshold (the payment looked too ordinary) | 0.52 |
| seed 777002 | S052623 | screen_share | 36-59 | 10 | score below the age-band threshold (the payment looked too ordinary) | 0.65 |
| seed 777003 | S052710 | screen_share | 36-59 | 9 | score below the age-band threshold (the payment looked too ordinary) | 0.49 |
| seed 777001 | S050128 | screen_share | 60+ | 0 | usage access off (foreground apps invisible) |  |
| seed 777001 | S051224 | screen_share | 60+ | 11 | usage access off (foreground apps invisible) |  |
| seed 777001 | S052208 | screen_share | 60+ | 1 | usage access off (foreground apps invisible) |  |

Per playbook, how the misses split by cause:

| Playbook | Missed | Of which: score below threshold |
|---|---|---|
| digital_arrest | 15 | 0 |
| family_emergency_scam | 692 | 572 |
| malicious_apk | 77 | 0 |
| remote_access | 20 | 0 |
| screen_share | 28 | 3 |

## 5. What this does and does not show

- It shows the recall and false-alarm figures are not an accident of one random draw: across independent draws they move by the amounts in section 1.
- It does not show real-world accuracy. Both the training data and this test come from the same simulator and share its assumptions.
- Section 4 is the honest list of where the detector fails; each cause is a known limitation, not a surprise.
- The sealed held-out run is still to do, and can only be done once. It is blocked on purpose until the `detector-freeze` tag exists.

