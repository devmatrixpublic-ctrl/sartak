# SatarkSim v2: merged dataset

One event table that merges every Satark data source that can validly be merged, plus the frozen held-out test set kept separately.

## What's inside `data/`

| File | Rows | What it is |
|---|---|---|
| `satarksim_events.csv` | ~110k | One row per event (call, app install, video session, new payee, payment), with `day`, `ts_abs`, `is_duplicate` |
| `satarksim_sessions.csv` | 53,000 | One row per session: `label` (true), `label_observed` (2% noisy), playbook, ICFD scam type, cohort, day/week, device flags, split |
| `satarksim_users.csv` | 15,000 | Per-user age band, activity, history median/MAD from the user's own distribution, known payees, device flags, split |
| `sensitivity_report.md` | — | Results under scam timings scaled 0.5×, 1× and 2× |
| `baf_report.md` | — | BAF benchmark: calibration and age-group fairness |
| `amount_model.json` | — | Fitted lognormal parameters for legit amounts |
| `validation_report.md` | — | Calibration, split integrity, artefact probe and difficulty probe |
| `detector_report.md` | — | **Reference detector results** (`satark_detector.py`): recall, false alarms, lead time, per playbook, drift, sensitivity |
| `detector_test_vectors_events.csv` / `_expected.csv` | 36 sessions | Inputs and expected decisions for verifying the on-phone port |
| `heldout/heldout_events.csv` + `SHA256` | 43 events, 10 cases | Real reconstructed cases. **Frozen; run once, at the end** |

## How each source was merged

| Source | How it's used | Status |
|---|---|---|
| NPCI statistics | Average ticket **₹1,402** from the official NPCI product-statistics workbook (Apr 2024–Mar 2025, value ÷ volume). P2M share (63%) and the under-₹500 shares (86% P2M, 59% P2P) are from a secondary summary of NPCI data | Done |
| ICFD-31k | Its 10 fraud umbrellas become `scam_type_icfd`, mapped to Satark playbooks | Done. Taxonomy only; the licence forbids generating scam scripts |
| Your generator (v2) | 50,000 legit sessions (incl. ~6,000 hard negatives of 8 kinds) and 3,000 scam sessions across 5 playbooks, over a 12-week calendar with drift and device noise (details below) | Done |
| Kaggle UPI Transactions 2024 | Hour-of-day and P2M merchant-category mix. **Not amounts**: its amounts are one distribution for every type (43% under ₹500 vs NPCI's 86%). **Not its fraud flag**: a model on every column predicts it at AUC 0.475, i.e. it is random | Done |
| Held-out real cases | Copied untouched, with a SHA-256 fingerprint | Done. Not used in the build |
| BAF (NeurIPS 2022) | Separate benchmark track (`baf_fairness.py` → `data/baf_report.md`): validates the calibration method, not scam detection | Done |
| IEEE-CIS | Benchmark track (`ieee_cis_benchmark.py` → `data/ieee_cis_report.md`): full-feature baseline, median/MAD vs mean/SD ablation, conformal check | Done. AUC 0.888; median/MAD and mean/SD tied (CI includes 0); 5.5% false-flag rate against a 5% target |

## Rebuild

```bash
python build_satarksim.py --heldout heldout_events.csv \
    --kaggle-upi upi_transactions_2024.csv \
    --npci-xlsx Product-Statistics-UPI-2024-25-Monthly.xlsx --out data
python sensitivity.py --kaggle-upi upi_transactions_2024.csv \
    --npci-xlsx Product-Statistics-UPI-2024-25-Monthly.xlsx --out data/sensitivity_report.md
python baf_fairness.py --base Base.csv --alpha 0.05 --out data/baf_report.md
python ieee_cis_benchmark.py --train train_transaction.csv --out data/ieee_cis_report.md
python satark_detector.py --data data --alpha 0.001 --out data/detector_report.md \
    --sensitivity --kaggle-upi upi_transactions_2024.csv --npci-xlsx Product-Statistics-UPI-2024-25-Monthly.xlsx
```

`build_satarksim_v1.py` and `params_v1.json` reproduce the v1 dataset. Raw files are not included in this package: Kaggle's licence is unstated, BAF's forbids redistributing modified data, and they're large.

## BAF result (`data/baf_report.md`)

AUC 0.888. With a 5% false-alarm target, one global threshold flags legitimate applicants aged 50+ at **3.08×** the rate of under-50s, which fails the 1.5× gate. Per-group (Mondrian) conformal thresholds bring this to **1.10×**, which passes. Recall drops from 0.561 to 0.529. The empirical false-alarm rate was 5.8% against the 5% target, because of month-to-month drift; this is why the design recalibrates on a rolling window. BAF is account-opening fraud, so this validates the calibration method, not scam detection.

## IEEE-CIS result (`data/ieee_cis_report.md`)

590,540 real transactions (3.5% fraud), split by time.
- **Full-feature model:** test AUC **0.888**.
- **median/MAD vs mean/SD:** 0.761 vs 0.759, a difference of +0.0024 with 95% CI [−0.0013, +0.0062]. That is **not significant**. Say "the robust statistic costs no accuracy", not "it detects better".
- **Conformal threshold:** a 5% target gave 5.5% empirical false flags, with 63% recall.

## What v2 adds (realism)

| Feature | What it does | Check in `validation_report.md` |
|---|---|---|
| Per-user consistency | Each user has a stable spending scale and a fixed list of known payees; their history stats come from the same distribution as their sessions | History vs session median: Spearman **0.62** (≈0 in v1) |
| Realistic hard negatives | COD delivery calls, **genuine family emergencies**, rent/salary day, festival spikes, IT support, out-of-order sessions, long gaps, family video calls. Timings are randomised, not fixed templates | Naive rule false-flags 91% of genuine family emergencies |
| Device noise | 10% of users have no call state (OEM); 5% have no usage access; 20% of timestamps jittered; 2% duplicate events; 2% of `label_observed` flipped | §2a |
| Calendar and drift | 84 days. From day 42, half of remote-access scams use a new app that isn't on the watch-list, and the malicious-APK share rises | Watch-list recall falls from **1.00 to 0.49** after day 42 |
| Five playbooks | remote access, malicious APK, digital arrest, **family-emergency scam** (the evil twin of the genuine emergency), screen share | §4 |
| Timing sensitivity | `sensitivity.py` rebuilds with scam timings ×0.5, ×1 and ×2 | `sensitivity_report.md` |
| Realism check | A classifier can't separate SatarkSim P2M rows from Kaggle rows on hour and merchant | AUC **0.498** |

**Sensitivity finding:** under any fixed-window rule, recall on malicious-APK scams swings from 0.77 to 0.05 as the timing scale goes 0.5× → 2×. For remote access it swings from 0.81 to 0.61. Detection that relies on time windows is fragile for these playbooks. This is the case for the timing-independent install-during-call signal (master doc §4.1).

Scam timings were **not** fitted to the held-out cases; doing so would leak the test set into training.

## Rules for using it

1. **Splits are by user.**
   - Fit on `train`.
   - Set the conformal threshold on **legit** sessions from `calibration`.
   - Report results on `validation`.
   - For drift, also report results from calibrating on weeks 0–5 and testing on weeks 6–11.
2. **Train on `label_observed`; evaluate on `label`.**
3. **Never use `age_band` as a scoring feature.** It is deliberately skewed for scams (an assumption) and exists only for per-cohort calibration.
4. **Ignore `is_duplicate=True` rows**, or better, have the detector deduplicate events itself, as it must on real devices.
5. **Don't touch `heldout/`** until the final run. Check that the SHA-256 still matches first.
6. **Report SatarkSim results as simulated:** they show the logic works, not real-world accuracy.
7. **All timing and scam-amount values in `params.json` are labelled assumptions.** Vary them in a sensitivity check; never tune them to the held-out cases.

## Baseline to beat (from `validation_report.md`)

The naive co-occurrence rule (unknown call + new payee + payment within 60 minutes of the call, order ignored) on the validation split:

| | Value |
|---|---|
| Overall recall | **0.53** |
| False flags on legit sessions | **3.9%** |
| Recall: digital arrest | 0.00 |
| Recall: malicious APK | 0.26 |
| Recall: remote access | 0.81 |
| Recall: family-emergency scam | 0.89 |
| Recall: screen share | 1.00 |
| False flags: COD delivery | 0.91 |
| False flags: genuine family emergency | 0.91 |
| False flags: out-of-order sessions | 0.61 |

Satark has to beat this on both recall and false flags. The hardest test is separating the genuine family emergency from the family-emergency scam: the event sequence is identical, so only amounts relative to the user's baseline and the number of payments differ.
