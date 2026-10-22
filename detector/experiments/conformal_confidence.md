# Experiment: thresholds with a confidence statement about the false-alarm rate

Simulated data. Rule chosen from calibration data only; validation evaluated once per variant; 95% Clopper-Pearson intervals.

| Cohort | Calibration n | Threshold rank k | P(true false-alarm rate <= 0.1%) | Shipped threshold | Variant threshold |
|---|---|---|---|---|---|
| 18-35 | 4512 | 4511 (n-1) | 94% | 0.915 | 1.297 |
| 36-59 | 4246 | 4245 (n-1) | 92% | 0.769 | 1.082 |
| 60+ | 1398 | 1398 (n-0) | 75% | 1.530 | 1.530 |

| Variant | Scam recall | Interdicted | False alarms | Family-emergency scam recall |
|---|---|---|---|---|
| shipped (expected FA <= 0.1%) | 540/578 = 93.426% [91.088, 95.306] | 487/578 = 84.256% [81.026, 87.130] | 11/9887 = 0.111% [0.056, 0.199] | 44/76 = 57.895% [46.017, 69.138] |
| 90%-confidence variant | 535/578 = 92.561% [90.110, 94.564] | 475/578 = 82.180% [78.812, 85.215] | 4/9887 = 0.040% [0.011, 0.104] | 41/76 = 53.947% [42.125, 65.452] |

False alarms by band: shipped (expected FA <= 0.1%): 18-35 5/4404, 36-59 6/3990, 60+ 0/1493; 90%-confidence variant: 18-35 1/4404, 36-59 3/3990, 60+ 0/1493

