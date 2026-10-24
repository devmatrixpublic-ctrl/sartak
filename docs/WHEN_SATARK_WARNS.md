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
| New payee, Rs 50,000 | **hold** | nudge |
| New payee, Rs 100,000 | **hold** | **hold** |
| Known payee, Rs 50,000 | quiet | quiet |
| Known caller (in contacts), new payee, Rs 50,000 | quiet | quiet |

## Installs
| Situation | Result |
|---|---|
| Unknown call + app from outside Google Play (no payment needed) | **hold** |
| Unknown text, then an app from outside Google Play within minutes | **hold** |
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
| 3 x Rs 3,000 | nudge | nudge |
| 3 x Rs 10,000 | **hold** (split guard) | nudge |
| 3 x Rs 25,000 | **hold** (split guard) | **hold** |

## Gaps this exposed (said openly)
- A payment **after the unknown call or text has ended** is quiet, even for Rs 50,000 to a new payee. The payment checks need the
  unknown contact to be active at the moment of payment.
- A stranger text on its own never changes a payment decision. It only matters together with a sideloaded app install.
- Nudge and hold thresholds are higher for the 60+ band.
