# Split-payment guard

**Simulated data only.** The guard shows a second copy of the same model the running total paid to a payee who was new within the
last hour; the app alarms if either copy does. Thresholds were calibrated without the guard, so added false alarms are not hidden.

## The whole validation split (SatarkSim)
| | Before | After |
|---|---|---|
| Scam sessions held | 538/578 (93.080%) | 550/578 (95.156%) |
| Genuine sessions wrongly held | 7/9887 (0.071%) | 7/9887 (0.071%, 95% interval 0.034% to 0.146%) |
| Scams held before the first payment | 83.910% | 83.910% |

The guard turned on in 451 validation sessions (ones with more than one payment to the same new payee within an hour).
It added 12 scam alarm(s) and 0 genuine false alarm(s). The deck's target for false alarms is 0.100%.

## The AI-style variants (held / runs)
| Scenario | Kind | Before | After |
|---|---|---|---|
| Family emergency from an unknown caller | scam | 4/90 | 4/90 |
| Digital arrest on a video call | scam | 90/90 | 90/90 |
| Fake customer care with screen-sharing | scam | 90/90 | 90/90 |
| Fake KYC app | scam | 90/90 | 90/90 |
| Text-led, no call | scam | 90/90 | 90/90 |
| Payment split into three | scam | 0/90 | 65/90 |
| Large payment, no screen-sharing app | scam | 28/90 | 28/90 |
| Genuine rent, known caller | genuine | 0/90 | 0/90 |
| Genuine bank-support call, small payment | genuine | 0/90 | 0/90 |
| Genuine wedding payment, no call | genuine | 0/90 | 0/90 |
| Delivery call, shop payment | genuine | 0/90 | 0/90 |
| Play Store install, no payment | genuine | 0/90 | 0/90 |

## Limits
- Simulated sessions and team-written scenarios, not real people. Real users who pay one new payee several times in an hour
  (a shop, a landlord in instalments) would trigger the guard's arithmetic more than the simulator suggests.
- It only adds an alarm when the model also sees an unknown contact or another signal, so a genuine instalment alone stays quiet.
  That is measured above for the simulator, not for real behaviour.
- The Kotlin version (`CumulativeNewPayee`) and this one share the same test cases, but they are separate code.
