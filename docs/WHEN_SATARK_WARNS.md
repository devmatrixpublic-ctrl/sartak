# When Satark warns, and when it stays quiet

Every row below was run through the app's own decision path (`ConditionMatrixTest`): session policy, the detector, the
split guard and the nudge rule, fed the same events the phone's signals produce. A new person is assumed (usual payment
about Rs 160). "60+" is the older age band, which is less sensitive. This is the decision logic, not the on-screen text,
which is checked on a phone.

**Quiet** = nothing shown. **Nudge** = amber "Take a moment". **Hold** = red "Stop. This looks like a scam."

## Payments during an unknown call
| Situation | 36-59 | 60+ |
|---|---|---|
| New payee, Rs 300 (under twice the usual) | quiet | quiet |
| New payee, Rs 5,000 or Rs 20,000 | nudge | nudge |
| New payee, Rs 24,999 | nudge | nudge |
| New payee, Rs 25,000 or more | **hold** | **hold** |
| Known payee, Rs 50,000 | quiet | quiet |
| Known caller (in contacts), new payee, Rs 50,000 | quiet | quiet |

## Payments soon AFTER the unknown call (or video) has ended
| Situation | Result |
|---|---|
| Ended up to 30 min ago, new payee, Rs 25,000 or more | **hold** |
| Ended up to 30 min ago, new payee, Rs 5,000 | nudge |
| Ended more than 30 min ago | quiet |
| The call was from a saved contact | quiet |

## Installs
| Situation | Result |
|---|---|
| Unknown call + app from outside Google Play (no payment needed) | **hold** |
| Unknown call + app from Google Play, or a remote-access app, with no payment | quiet |
| No call, sideloaded or remote-access app only | quiet |

## Video calls
| Situation | Result |
|---|---|
| Unknown video call, then new payee Rs 50,000 | **hold** |
| Unknown video call for 2 hours | **hold** (long-session rule) |
| Known video call for 3 hours | quiet |

## Payments split into pieces (same new payee, unknown call, within an hour)
| Situation | 36-59 | 60+ |
|---|---|---|
| 3 x Rs 1,000 | nudge | nudge |
| 3 x Rs 3,000 (Rs 9,000 in all) | **hold** (split guard) | nudge |
| 3 x Rs 10,000 (Rs 30,000 in all) | **hold** | **hold** |
| 3 x Rs 25,000 | **hold** | **hold** |

## Gaps this exposed (said openly)
- A payment more than **30 minutes after** the unknown call ended is quiet. Text messages never count as unknown contact.
- The same amount to the same payee again **within 2 minutes** is counted as a retry of one payment, not a second piece.
- A stranger text (or, later, a flagged WhatsApp message) never changes a payment decision. It is kept as evidence for a Stop screen
  and counted for the repeated-texts warning, which holds nothing.
- The detector's own payment score is still less sensitive for the 60+ band. The Rs 25,000 rule (`HighValueNewPayee`) is what holds a
  large payment to a new payee for every age; it costs 8 more genuine sessions held in 9,887 (false alarms 0.071% to 0.152%,
  over the 0.100% target), and "Continue anyway" always lets the person go on (`ops/eval/reports/high_value_rule.md`).
