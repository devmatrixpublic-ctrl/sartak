# Split-payment evasion: before and after a split guard (Person B)

**Simulated data.** Validation split of SatarkSim (578 scam sessions), detector exactly as shipped, thresholds not re-tuned (except the one labelled re-calibrated row). Not the sealed held-out set and not real fraud.

**Attacks:** each payment in a scam is split into k equal pieces to the same payee, 30 s apart (k = 1 is the unmodified data); and an *adaptive* attack that cuts each payment into the fewest pieces that are each no larger than the victim's own median payment (the amount the detector compares against), at most 50 pieces. **Guard:** each attempt is scored as the running total to that payee in the last 30 minutes. The guard is app-side pre-processing, not part of the frozen detector; adopting it needs a new freeze.

*Amount protected* is the share of the scam's total still unsent when the alarm fired (an alarm holds the attempt it fires on). It is computed from the real piece amounts, never from the guard's running totals.

## 1. All scam sessions

| Pieces (k) | Guard | Caught | Interdicted before 1st payment | Amount protected | Caught unattacked but evaded now |
|---|---|---|---|---|---|
| 1 | off | 538/578 = 93.1% | 83.9% | 98.6% | 0/538 = 0.0% |
| 1 | on | 550/578 = 95.2% | 83.9% | 98.6% | 0/538 = 0.0% |
| 2 | off | 553/578 = 95.7% | 78.2% | 99.0% | 0/538 = 0.0% |
| 2 | on | 561/578 = 97.1% | 78.2% | 99.1% | 0/538 = 0.0% |
| 3 | off | 558/578 = 96.5% | 76.0% | 99.2% | 0/538 = 0.0% |
| 3 | on | 567/578 = 98.1% | 76.0% | 99.3% | 0/538 = 0.0% |
| 5 | off | 567/578 = 98.1% | 73.0% | 99.4% | 0/538 = 0.0% |
| 5 | on | 578/578 = 100.0% | 73.0% | 99.5% | 0/538 = 0.0% |
| 10 | off | 578/578 = 100.0% | 68.7% | 99.6% | 0/538 = 0.0% |
| 10 | on | 578/578 = 100.0% | 68.7% | 99.7% | 0/538 = 0.0% |
| adaptive (each piece no larger than the user's own median payment, at most 50) | off | 578/578 = 100.0% | 57.6% | 99.9% | 0/538 = 0.0% |
| adaptive (each piece no larger than the user's own median payment, at most 50) | on | 578/578 = 100.0% | 57.6% | 99.9% | 0/538 = 0.0% |

## 2. Only the scams that depend on the amount-sensitive payment score (281 sessions)

Many scams are caught by rules that ignore amounts (a sideloaded app during a call, a very long video call), so splitting cannot hide them. These are the ones caught by the payment score alone when unattacked: the only ones splitting can threaten.

| Pieces (k) | Guard | Still caught |
|---|---|---|
| 1 | off | 281/281 = 100.0% |
| 1 | on | 281/281 = 100.0% |
| 2 | off | 281/281 = 100.0% |
| 2 | on | 281/281 = 100.0% |
| 3 | off | 281/281 = 100.0% |
| 3 | on | 281/281 = 100.0% |
| 5 | off | 281/281 = 100.0% |
| 5 | on | 281/281 = 100.0% |
| 10 | off | 281/281 = 100.0% |
| 10 | on | 281/281 = 100.0% |
| adaptive (each piece no larger than the user's own median payment, at most 50) | off | 281/281 = 100.0% |
| adaptive (each piece no larger than the user's own median payment, at most 50) | on | 281/281 = 100.0% |

## 3. The guard's price: false alarms on legitimate sessions (never attacked)

| Configuration | False alarms | Rate (95% CI) |
|---|---|---|
| guard off (shipped) | 7/9887 | 0.071% (0.028% - 0.146%) |
| guard on, shipped thresholds | 7/9887 | 0.071% (0.028% - 0.146%) |
| guard on, thresholds re-calibrated | 7/9887 | 0.071% (0.028% - 0.146%) |

With thresholds re-calibrated on guarded calibration data, unattacked scam recall is 550/578 = 95.2%. A guard that also moves false alarms past the 0.1% target, or recall below 93%, would not be adopted as is.

## 4. Reading the results

- **Splitting did not evade the detector.** Unattacked it catches 538/578; across every attack in section 1 the worst case is 538/578 caught with the guard off. 0 scams caught unattacked were missed after any split.
- **Why:** each piece is another payment screen and another chance to alarm, and repeat payments to one payee add to the score, so more pieces give the detector more evidence, not less.
- **What splitting does cost the defender is timing.** Interdicted before the first payment falls from 83.9% unattacked to 57.6% under the adaptive attack: the first small pieces go out before the alarm. The money at risk stays small (99.9% of the amount is still protected).
- **The guard does not fix that, and was not needed here.** It leaves interdiction before the first payment unchanged (the first piece is scored as itself), and its only measurable effect is on scams whose own repeat payments add up. False alarms with the guard: 7/9887 against 7/9887 without.
- **So:** do not ship the guard on this evidence. The honest statement for the deck is that this attack shape was tested and does not beat the shipped detector, while naming the real exposure (the first payments before the alarm) and the attack not tested (pieces to several different payees).

## 5. Limits

- One attack shape (equal pieces, fixed gap, one payee). A scammer can vary amounts, gaps and payees; a guard keyed on one payee does nothing against pieces spread over several new payees (mule accounts).
- The guard counts a retried payment twice if the retry comes after the 3-second de-duplication window; the false-alarm row above is the measured cost of that on the simulator, which may not reproduce real retry behaviour.
- SatarkSim has no real splitting behaviour in it, so the unattacked numbers are the simulator's, not a measure of how often real scams split.

