# Detector timing sensitivity (computed at calibration alpha = 0.001, NOT re-run)

Carried over from the original SatarkSim `detector_report.md`. It was computed before the calibration margin (alpha' = 0.0008) was adopted, and re-running it needs the raw Kaggle UPI and NPCI workbooks that are not in this repo (`detector/reference/satark_detector.py --sensitivity`). Treat the numbers as indicative of how recall moves with scam timing, not as results of the shipped thresholds.

## Timing sensitivity (trained at 1×, tested on data rebuilt at other timing scales)

| Timing scale | Satark recall | Naive recall |
|---|---|---|
| 0.5× | 93.4% | 69.7% |
| 1.0× | 93.4% | 53.1% |
| 2.0× | 93.3% | 40.1% |

Satark's install-during-call and long-session mechanisms do not depend on time windows, so recall should move far less than the naive rule's.
