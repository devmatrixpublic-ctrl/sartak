# AI-style scam variants

**Team-written scenarios on the reference detector fitted on SatarkSim. Simulated events, never used to train or calibrate. Not real-world accuracy.**
Calibration alpha 0.0008. Typical user: usual payment about Rs 161. Each scenario is run 30 times in each age band.

## Where the amounts come from
Taken from SatarkSim itself, as multiples of the user's usual payment, never hand-picked. Scams: the middle half (25th to 75th
percentile) of the matching playbook. Genuine large payments: the 90th to 99th percentile of legitimate payments.
- family emergency: 58x to 280x
- family emergency, upper half: 130x to 527x
- digital arrest: 3,199x to 26,197x
- remote access: 71x to 351x
- malicious app: 168x to 833x
- genuine large payment: 14x to 173x

## Scam workflows (the detector should hold the payment)
| Scenario | What happens | Held | By age band (18-35 / 36-59 / 60+) | Fired by |
|---|---|---|---|---|
| Family emergency from an unknown caller | Unknown caller (a real or a cloned voice looks the same to Satark), no app, one large payment to a new payee | 4/90 (4%, 2% to 11%) | 3% / 10% / 0% | payment_score 4 |
| Digital arrest on a video call | Unknown video call, a long wait, a very large payment | 90/90 (100%, 96% to 100%) | 100% / 100% / 100% | payment_score 90 |
| Fake customer care with screen-sharing | Unknown call, screen-sharing app opened, large payment to a new payee | 90/90 (100%, 96% to 100%) | 100% / 100% / 100% | payment_score 90 |
| Fake KYC app | Unknown call, app from outside Google Play, payment to a new payee | 90/90 (100%, 96% to 100%) | 100% / 100% / 100% | sideload_during_call 90 |
| Text-led, no call | A stranger's text, an unsafe app, payment to a new payee | 90/90 (100%, 96% to 100%) | 100% / 100% / 100% | sideload_during_call 90 |
| Payment split into three | Unknown call, three smaller transfers to the same new payee | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |
| Large payment, no screen-sharing app | Unknown call, no app at all, very large payment to a new payee | 28/90 (31%, 22% to 41%) | 43% / 50% / 0% | payment_score 28 |

**Overall: 392 of 630 scam runs held (62%).**

## Genuine look-alikes (the detector should stay quiet)
| Scenario | What happens | Wrongly held | By age band | Fired by |
|---|---|---|---|---|
| Genuine rent, known caller | Known caller, new payee, large | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |
| Genuine bank-support call, small payment | Unknown caller, known payee, small | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |
| Genuine wedding payment, no call | No contact, new payee, large | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |
| Delivery call, shop payment | Unknown caller, merchant already known, small | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |
| Play Store install, no payment | Known caller, install from Google Play | 0/90 (0%, 0% to 4%) | 0% / 0% / 0% | none |

**Overall: 0 of 450 genuine runs wrongly held (0%).**

## What this shows
- Weak spots (held in fewer than half of runs): Family emergency from an unknown caller; Payment split into three; Large payment, no screen-sharing app.
- "Fired by" says whether the payment score or a rule (such as an unsafe install during contact) raised the alarm.
- The older age band has a higher threshold, so it is the one to watch in the by-band column.
- A scam that leaves no screen-sharing app and no unsafe install rests on the unknown caller, a new payee and the amount alone.
  Whether that holds is shown in the rows above, and any miss is the detector's real limit.

## Limits
- These are our own scenarios. Real scammers will not follow them, and nothing here measures how often real people hit each workflow.
- The detector tested is the Python reference. The on-device version agrees on the 36 shared test vectors, not on every case here.
- Amounts are multiples of a typical user's usual payment, taken from the simulator's own distributions (listed above). A user with a very different baseline would see different results.
