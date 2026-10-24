# Rising-pattern detection

**Simulated experiment. A new scam pattern is injected into counts built from SatarkSim's scam mix. This says how the
detector behaves, not how real scams grow.**

## Method
Each pattern's daily count is watched with a CUSUM (slack k = 0.5, alarm at h = 5.0), judged against its own first
28 days. A new pattern appears on day 56 and ramps over 7 days to
8 signatures a day, on top of about 60 a day across the normal
patterns. 300 random runs of 84 days.

## Result
| | |
|---|---|
| New pattern noticed | 300 of 300 runs (100.0%) |
| Days from its first appearance to the flag | median 3, 90th percentile 4 |
| False flags on the normal patterns | 223 in total, 0.97 per pattern per year |


## How small a new scam can it catch?
(same method, only the size of the new pattern changes; the number is where it levels off)

| New pattern size | Noticed | Median days | 90th percentile days | False flags per pattern per year |
|---|---|---|---|---|
| 2 a day | 93.5% | 12 | 21 | 1.06 |
| 4 a day | 100.0% | 6 | 8 | 1.06 |
| 8 a day | 100.0% | 3 | 4 | 1.06 |
| 16 a day | 100.0% | 2 | 3 | 1.06 |

## The normal mix used (SatarkSim scam playbooks)
| Pattern | Share |
|---|---|
| malicious_apk | 31.2% |
| remote_access | 28.3% |
| digital_arrest | 17.1% |
| family_emergency_scam | 13.8% |
| screen_share | 9.6% |

## Limits
- Counts are assumed to be roughly Poisson. Real signature counts are likely burstier, which would raise false flags.
- The thresholds (k, h) were set once and not tuned to this experiment.
- A very slow rise is caught late; a pattern that is already common at the start is treated as normal.
- The pattern key (mechanism plus the three highest features) is a design choice. Different keys group scams differently.
