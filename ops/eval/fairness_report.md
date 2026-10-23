# Fairness report (simulated data)

Validation split of SatarkSim, per cohort. **All numbers are from a simulator, not real users.** Language is skipped (SatarkSim has no language field) and there is no device-tier column, so call-state availability, a device-capability flag, is shown instead. The gate is the ratio max/min of a rate across the cohorts of one dimension, on point estimates, and fails above 1.5. A cohort with zero false alarms makes the false-alarm ratio undefined (infinite), which fails the gate as written. Per-cohort false-alarm counts are 0 to 5, so these ratios are noisy.

**Gate: FAIL**

## age band

| cohort | scam sessions | recall (95% CI) | legit sessions | false alarms | false-alarm rate (95% CI) |
|---|---|---|---|---|---|
| 18-35 | 148 | 95.3% (90.5%-98.1%) | 4404 | 3 | 0.068% (0.014%-0.199%) |
| 36-59 | 220 | 95.5% (91.8%-97.8%) | 3990 | 4 | 0.100% (0.027%-0.256%) |
| 60+ | 210 | 89.0% (84.0%-92.9%) | 1493 | 0 | 0.000% (0.000%-0.247%) |

Recall max/min: **1.07**. False-alarm max/min: **undefined (a cohort has zero)**.

## activity tier

| cohort | scam sessions | recall (95% CI) | legit sessions | false alarms | false-alarm rate (95% CI) |
|---|---|---|---|---|---|
| high | 210 | 92.9% (88.5%-95.9%) | 7257 | 5 | 0.069% (0.022%-0.161%) |
| low | 200 | 92.5% (87.9%-95.7%) | 454 | 0 | 0.000% (0.000%-0.809%) |
| medium | 168 | 94.0% (89.3%-97.1%) | 2176 | 2 | 0.092% (0.011%-0.332%) |

Recall max/min: **1.02**. False-alarm max/min: **undefined (a cohort has zero)**.

## call-state availability

| cohort | scam sessions | recall (95% CI) | legit sessions | false alarms | false-alarm rate (95% CI) |
|---|---|---|---|---|---|
| False | 77 | 85.7% (75.9%-92.6%) | 1016 | 0 | 0.000% (0.000%-0.362%) |
| True | 501 | 94.2% (91.8%-96.1%) | 8871 | 7 | 0.079% (0.032%-0.163%) |

Recall max/min: **1.10**. False-alarm max/min: **undefined (a cohort has zero)**.

## Gate failures

- fairness: false-alarm rate max/min across age band is undefined (a cohort has none) (limit 1.5)
- fairness: false-alarm rate max/min across activity tier is undefined (a cohort has none) (limit 1.5)
- fairness: false-alarm rate max/min across call-state availability is undefined (a cohort has none) (limit 1.5)

