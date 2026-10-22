# Experiment: session-running features for the family-emergency scam

Simulated data. Train on train, thresholds on calibration (alpha = 0.1%), validation reported once. 95% Clopper-Pearson intervals in brackets. The shipped model is variant A and is unchanged.

| Variant | Scam recall | Interdicted | False alarms (all legit) | Family scam recall | Family scam interdicted | Genuine family emergency flagged |
|---|---|---|---|---|---|---|
| A. shipped (16 features) | 540/578 = 93.43% [91.09, 95.31] | 487/578 = 84.26% [81.03, 87.13] | 11/9887 = 0.11% [0.06, 0.20] | 44/76 = 57.89% [46.02, 69.14] | 21/76 = 27.63% [17.99, 39.09] | 10/131 = 7.63% [3.72, 13.59] |
| B. + n_pay_sofar | 540/578 = 93.43% [91.09, 95.31] | 487/578 = 84.26% [81.03, 87.13] | 12/9887 = 0.12% [0.06, 0.21] | 44/76 = 57.89% [46.02, 69.14] | 21/76 = 27.63% [17.99, 39.09] | 10/131 = 7.63% [3.72, 13.59] |
| C. + both session features | 540/578 = 93.43% [91.09, 95.31] | 489/578 = 84.60% [81.40, 87.45] | 12/9887 = 0.12% [0.06, 0.21] | 44/76 = 57.89% [46.02, 69.14] | 23/76 = 30.26% [20.25, 41.87] | 10/131 = 7.63% [3.72, 13.59] |

False alarms by age band (validation):

| Variant | 18-35 | 36-59 | 60+ |
|---|---|---|---|
| A. shipped (16 features) | 5/4404 = 0.11% | 6/3990 = 0.15% | 0/1493 = 0.00% |
| B. + n_pay_sofar | 5/4404 = 0.11% | 7/3990 = 0.18% | 0/1493 = 0.00% |
| C. + both session features | 5/4404 = 0.11% | 7/3990 = 0.18% | 0/1493 = 0.00% |

Weights of the added features (variant C): log_cum_ratio +1.66, n_pay_sofar -0.95

