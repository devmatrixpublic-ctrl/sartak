# When Satark warns, and when it stays quiet

Every row below was run through the app's own decision path (`ConditionMatrixTest`): session policy, the detector, the
split guard and the nudge rule, fed the same events the phone's signals produce. A new person is assumed (usual payment
about Rs 160). "60+" is the older age band, which is less sensitive. The tables are for a person who gave no age or is 22 or
older; people under 22 have their own table below. This is the decision logic, not the on-screen text, which is checked on a phone.

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

## People who say they are under 22
The app asks for an optional age (Protection screen; it stays on the phone and is never sent). Under 22 the new-payee hold starts at
Rs 10,000 instead of Rs 25,000, on the assumption of a student whose usual payments are small. Everything else is unchanged.

| Situation (age 21) | Result |
|---|---|
| Unknown call, new payee, Rs 5,000 or Rs 9,999 | nudge |
| Unknown call, new payee, Rs 10,000 or more | **hold** |
| Call ended up to 30 min ago, new payee, Rs 10,000 | **hold** |
| Call ended more than 30 min ago, or a known caller, or no call | quiet |
| 3 x Rs 4,000 (Rs 12,000 in all) | **hold** |
| Age 22, new payee, Rs 10,000 | nudge (22 is held from Rs 25,000) |

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

## The fingerprint lock
The owner check is needed for: **Continue anyway** on a Stop screen, turning protection off, linking or removing a
trusted contact, changing who to call, changing the age, and deleting data. First-run setup cannot finish without it.
The point is a scammer driving the screen through a remote-access app: they cannot present a fingerprint. A phone with an enrolled
fingerprint accepts only the fingerprint (no PIN alternative). A phone with no fingerprint (no sensor, or none enrolled) falls back to its
screen-lock PIN, pattern or password, which is weaker: a PIN typed while the screen is shared is no longer private. It protects
against a remote controller, not against a victim who is being coached and gives the check themselves.

| Situation | Result |
|---|---|
| Stop screen, tap "Continue anyway", right finger | the payment is released to the UPI app |
| Same, wrong finger | the prompt stays open; nothing is released |
| Same, prompt cancelled | the Stop screen stays; nothing is released |
| No fingerprint enrolled, or no sensor | the screen-lock PIN is asked instead; wrong PIN releases nothing |
| No fingerprint and no screen lock | "Set a screen lock first"; nothing is released |

## Turning Satark off, and removing it
A scammer's other goal is to get Satark out of the way. The trusted contact is told at once in each case (one plain line, no name or amount).

| Situation | What happens |
|---|---|
| Turn protection off | owner check, then a **30-minute wait**; protection stays ON during it; the contact is told **immediately** ("asked to turn off"); "Keep protection on" cancels at once |
| The wait ends | protection goes off, the person gets a notification, the contact is told again ("turned off") |
| Turn protection back on | at once, no check |
| Delete my data | owner check; the contact is told first; no wait |
| Uninstall Satark with the removal guard on | Android refuses until the guard is switched off in Settings (Device admin apps); Android shows Satark's warning there; the contact is told the moment it is switched off ("can now be removed") |
| Uninstall with the guard off | Android allows it; Satark cannot stop or announce it (it is gone) |

The wait runs on two clocks, so moving the phone's date does not skip it. A coached person can still wait it out; the point is time and a
witness, not a wall. Not covered: revoking permissions or force-stopping Satark in Settings, and a phone that is offline (the contact's
alert is queued and goes when it is back online).

## Gaps this exposed (said openly)
- A payment more than **30 minutes after** the unknown call ended is quiet. Text messages never count as unknown contact.
- The same amount to the same payee again **within 2 minutes** is counted as a retry of one payment, not a second piece.
- A stranger text (or, later, a flagged WhatsApp message) never changes a payment decision. It is kept as evidence for a Stop screen
  and counted for the repeated-texts warning, which holds nothing.
- The detector's own payment score is still less sensitive for the 60+ band. The Rs 25,000 rule (`HighValueNewPayee`) is what holds a
  large payment to a new payee for every age; it costs 8 more genuine sessions held in 9,887 (false alarms 0.071% to 0.152%,
  over the 0.100% target), and "Continue anyway" always lets the person go on (`ops/eval/reports/high_value_rule.md`).
- **The lower amount for under-22s is not supported by the simulator.** Holding the whole 18-35 band from Rs 10,000 (an upper bound,
  because the simulator has age bands, not ages) holds no extra scams and 12 more genuine sessions (false alarms 0.152% to 0.273%).
  The simulator does not model how scam amounts differ by age, so it cannot show a benefit either; the choice rests on the assumption
  about students, not on a measurement. Set `HighValueNewPayee.YOUNG_THRESHOLD_INR` to 25,000 to switch it off.
- Until now the app never asked for an age, so every phone used the model's pooled threshold. With an age entered, the model's own cohort
  thresholds apply too (the 60+ band is less sensitive; the Rs 25,000 rule covers large payments there).
