# Alert budget

**Simulated data only (SatarkSim). This is a projection from a measured per-payment rate, not a measurement of real people.**
Calibration alpha 0.0008. Validation split: 9,887 legitimate sessions, 3,000 simulated users.

## What is measured

| | Count | Rate per legitimate payment | 95% interval |
|---|---|---|---|
| Pause (alarm) on a legitimate session | 7 | 0.071% | 0.034% to 0.146% |
| Nudge only (new payee during an unknown call, no alarm), today's rule | 229 | 2.316% | 2.038% to 2.632% |
| Nudge only, tighter rule (also needs the amount to be at least 2x the user's usual payment) | 139 | 1.406% | 1.192% to 1.658% |

6.625% of the legitimate simulated sessions contain an unknown call. The simulator includes many such calls on purpose
(bank support, delivery, the genuine family emergency) as hard negatives, so the nudge rate here is likely higher than real life. Treat it as a stress test.

## Projected burden on a legitimate user, against the deck's budget

| Alert | Budget (deck) | Mean per user | Upper-bound (95%) | Worst activity tier | Share of users hit at least once | Verdict |
|---|---|---|---|---|---|---|
| Pause, per quarter | at most 1 | 0.078 | 0.161 | 0.170 | 7.277% | within budget for every activity tier |
| Nudge, per month, today's rule | at most 1 | 0.848 | 0.964 | 1.853 | 46.311% | within on average, OVER for the busiest users |
| Nudge, per month, tighter rule | at most 1 | 0.515 | 0.607 | 1.125 | 34.591% | within on average, OVER for the busiest users |

**Finding.** Pauses are well inside the budget. The nudge is the fatigue risk: it is a policy in the app (not in the frozen detector),
so it can be tightened without touching the model. The tighter rule above is a proposal; it is measured here but not yet in the app.

## Assumptions (read these)

1. Every payment a person makes in Satark is one scored session. Payments per month per user come from the simulator
   (min 5, median 25, max 80).
2. The alert rate per payment is constant and independent between payments. Real people are bunched (a week of unusual
   spending), so real burden would be lumpier than this average.
3. The simulator holds only a few sessions per user, so alerts were not counted per user directly. They were projected.
4. A Nudge is approximated as "a payment to a new payee while an unknown call is active, with no alarm". The app's
   own rule is the same shape, but real call patterns differ from simulated ones.
5. Repeat alerts within 60 minutes are merged by the app, so one incident is one alert. The simulator also counts the
   first alarm per session only.
6. This says nothing about missed scams. See the main evaluation report for recall.
