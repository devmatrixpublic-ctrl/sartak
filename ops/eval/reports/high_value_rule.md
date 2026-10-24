# High-value new-payee rule

**Simulated data only (SatarkSim, validation split).** The rule holds a payment to a payee who was new within the last hour
(running total) when an unknown call or video is open, or ended within 30 minutes, and the amount reaches the threshold. It is the
same for every age band and only adds holds. Today: 538/578 scams held and
7/9887 genuine sessions held. The deck's target for false alarms is 0.100%.

| Threshold | Extra scams held | Scam recall after | Extra genuine sessions held | False-alarm rate after (95% interval) |
|---|---|---|---|---|
| Rs 10,000 | 25 | 97.405% | 39 | 0.465% (0.349% to 0.620%) |
| Rs 20,000 | 21 | 96.713% | 12 | 0.192% (0.123% to 0.300%) |
| Rs 25,000 (chosen) | 20 | 96.540% | 8 | 0.152% (0.092% to 0.250%) |
| Rs 30,000 | 14 | 95.502% | 6 | 0.131% (0.077% to 0.225%) |
| Rs 50,000 | 5 | 93.945% | 0 | 0.071% (0.034% to 0.146%) |

Read it as a trade: a lower threshold holds more scams and more genuine payments. A held genuine payment is not lost, because the
person can choose "Continue anyway", but it is friction and it counts against the alert budget.
