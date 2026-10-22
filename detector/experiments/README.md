# Experiments (none of these changed the shipped model, except where stated)

All were run on SatarkSim (simulated data). Experiments 2 and 3 predate the calibration margin and use alpha = 0.001 as "shipped".

| Experiment | Question | Result |
|---|---|---|
| `session_total_features` | Do session-running features help the family-emergency scam? | No. Not adopted. |
| `conformal_confidence` | Thresholds with a 90% confidence statement on the false-alarm rate? | False alarms 0.040% but recall 92.6%. Not adopted. |
| `calibration_margin_cv` | Which calibration alpha' keeps false alarms <= 0.1%? Chosen by cross-validation on train+calibration data only, by a rule fixed before the run. | **Adopted: alpha' = 0.0008** (`params.json` `calibration_alpha`). |
