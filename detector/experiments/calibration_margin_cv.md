# Calibration margin chosen by cross-validation (validation split never used)

5 repeats, user-level 60/20/20 split of train+calibration. Rule fixed in advance: largest alpha' with pooled false-alarm <= 0.09%.

| alpha' (calibration) | CV false alarms (95% CI) | worst repeat | CV recall (95% CI) |
|---|---|---|---|
| 0.0010 | 43/40359 = 0.107% [0.077, 0.143] | 0.181% | 93.54% [92.47, 94.51] |
| 0.0009 | 39/40359 = 0.097% [0.069, 0.132] | 0.181% | 92.95% [91.83, 93.95] |
| 0.0008 | 28/40359 = 0.069% [0.046, 0.100] | 0.145% | 91.83% [90.65, 92.91] |
| 0.0007 | 28/40359 = 0.069% [0.046, 0.100] | 0.145% | 91.83% [90.65, 92.91] |
| 0.0006 | 27/40359 = 0.067% [0.044, 0.097] | 0.145% | 91.32% [90.11, 92.43] |
| 0.0005 | 12/40359 = 0.030% [0.015, 0.052] | 0.072% | 90.64% [89.38, 91.79] |
| 0.0004 | 12/40359 = 0.030% [0.015, 0.052] | 0.072% | 90.64% [89.38, 91.79] |

**Chosen alpha' = 0.0008**

The repeats share users, so the intervals are optimistic; treat them as a guide, not a guarantee.
