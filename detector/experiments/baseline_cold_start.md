# Experiment: how much does detection depend on the user's own payment history?

Simulated data. Each variant is retrained on train, calibrated on legitimate calibration sessions at the shipped calibration alpha' = 0.08%, and evaluated once on validation (95% Clopper-Pearson intervals). The shipped model is variant A and is unchanged.

| Variant | Scam recall | Interdicted | False alarms | Family-emergency scam recall |
|---|---|---|---|---|
| A. mature personal history (reference; what the shipped numbers use) | 538/578 = 93.1% [90.7, 95.0] | 485/578 = 83.9% [80.7, 86.8] | 7/9887 = 0.071% [0.028, 0.146] | 43/76 = 56.6% [44.7, 67.9] |
| B. brand-new install: population prior for everyone | 548/578 = 94.8% [92.7, 96.5] | 495/578 = 85.6% [82.5, 88.4] | 11/9887 = 0.111% [0.056, 0.199] | 52/76 = 68.4% [56.7, 78.6] |
| C. on-device rule fed by the payments SatarkSim contains | 544/578 = 94.1% [91.9, 95.9] | 488/578 = 84.4% [81.2, 87.3] | 10/9887 = 0.101% [0.049, 0.186] | 50/76 = 65.8% [54.0, 76.3] |

Variant C history size at validation: median 2 prior legitimate payments, 24% of validation sessions have none, 3% have 10 or more (blend weight n/(n+20)).

Reading it: A is a user with a mature, accurate baseline. B and C are what the app has on day one. The recall gap A to B is the price of having no personal history yet; thresholds were recalibrated per variant so false alarms stay comparable. SatarkSim gives each user only a few sessions, so C cannot show how a real month of use closes that gap, and its `hist_*` numbers in A are the generator's own long-run values, which a phone can only approach.

