# Demo: the split-payment guard on a phone

**What it shows:** a scammer on an unknown call asks for one big transfer. Satark holds it. The scammer then asks for the same
total in three pieces. No single piece looks big, but Satark adds up what went to the same new payee in the last hour and holds it.

**Setup (important):** use a fresh install, or one with only small payments, because Satark learns the person's usual payment
and the thresholds depend on it. On a fresh install the usual payment is about Rs 160. Do NOT install a remote-access app: that
trips a rule that ignores the amount and hides what this demo is about. Pick an age band of 18-35 or 36-59 in onboarding
(60+ is deliberately less sensitive in the demo: it needs a higher total).

| Step | Do this | Expect |
|---|---|---|
| 1 | Call the phone from a number that is not in contacts and answer (emulator: `adb emu gsm call 9876500022`, then `adb emu gsm accept 9876500022`) | "Protection is on" stays on |
| 2 | In Satark, pay `newperson@okaxis` Rs 75,000 once | Full-screen hold: "Stop. This looks like a scam." Do not continue |
| 3 | End the call, wait, or use a different new payee, then repeat the call | A clean start |
| 4 | Pay `splitgrp@okaxis` Rs 25,000, three times, a couple of minutes apart | Pieces 1 and 2 may go through or nudge; at the point the total reaches the threshold the hold appears. The alarm lists the same reasons as step 2 |
| 5 | Open Alert history | "Payments held" has gone up |

**Why it is held:** `SplitGuard` runs a second copy of the detector on the running total to a payee who was new within the last
hour. It only ever adds an alarm.

**How to check it flags only suspicious activity:**
- `SplitGuardDemoTest` pins the numbers above (single Rs 75,000 held; three Rs 25,000 held only by the guard; three Rs 3,000 not held).
- `SplitGuardVectorsTest` runs M2's 36 vectors and fails if the guard changes any frozen decision except one named session or adds a false alarm.
- `ops/eval/split_guard_app.py` and person-b's `ops/eval/split_guard.py`: with the guard, false alarms on genuine sessions stay at 7/9887 (0.071%), and 12 more scams are held.
- Known limit: the guard only helps scams the payment score catches. Scams caught by the sideload or call rules are held regardless of splitting.
