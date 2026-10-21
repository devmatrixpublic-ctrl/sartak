# Timing-assumption sensitivity

Every scam timing range in `params.json` was multiplied by the scale below; everything else was held fixed (same seed). Metric: naive co-occurrence baseline on the validation split (a stand-in until the detector exists).

| Timing scale | overall recall | false-flag rate | digital_arrest | family_emergency_scam | malicious_apk | remote_access | screen_share |
|---|---|---|---|---|---|---|---|
| 0.5× | 0.70 | 0.04 | 0.00 | 0.89 | 0.77 | 0.81 | 1.00 |
| 1.0× | 0.53 | 0.04 | 0.00 | 0.89 | 0.26 | 0.81 | 1.00 |
| 2.0× | 0.40 | 0.04 | 0.00 | 0.89 | 0.05 | 0.61 | 0.93 |
| **max − min** | **0.30** | **0.00** | **0.00** | **0.00** | **0.72** | **0.19** | **0.07** |

## Reading it

- Sensitive to timing assumptions (spread > 0.15): **overall recall, malicious_apk, remote_access**. Results for these playbooks depend on how fast scams unfold, so report them with this caveat.
- The false-flag rate does not depend on scam timings (legit sessions are unchanged); it is shown as a control.
- Rerun with the real Satark detector once it exists; the naive rule only shows how much the data itself shifts.
