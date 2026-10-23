# "2 or more signal families" eligibility gate: probe result (not implemented)

**Simulated data (SatarkSim validation split, 578 scam and 9,887 legitimate sessions). Not real-world accuracy.**

Question: would a payment-score alarm only be allowed when at least two signal families are present, and what would that cost?
Reproduce with `python detector/experiments/signal_family_gate_probe.py` (offline; changes nothing).

How it was approximated: families were read from the 16 features on the payment itself: **contact** (unknown call, video or recent
contact), **install** (any install during an unknown contact, or a watch-listed app), **new payee**. A payment-score alarm was kept
only when at least `k` families were present. Rule alarms were unchanged. Thresholds were **not** recalibrated and nothing was tuned.
This approximates the 60-minute window with the features' own windows, so a precise event-level version could differ somewhat.

| Gate | Scam recall | False alarms |
|---|---|---|
| none (the shipped detector) | 93.1% (538/578) | 0.071% (7/9,887) |
| at least 1 family | 93.1% (538/578) | 0.071% (7/9,887) |
| **at least 2 families** | **88.9% (514/578)** | 0.061% (6/9,887) |

Recall by playbook with the 2-family gate (shipped in brackets): digital arrest 95.6% (98.9%), malicious APK 90.9% (97.9%),
remote access 95.9% (99.4%), screen share 98.1% (98.1%), family emergency 53.9% (56.6%).

Outcome: the gate removes 24 of the 538 caught scams (4.2 points of recall) to remove one of seven false alarms. That puts recall
below the plan's 93% target, so **the gate was not implemented**: no Kotlin change, no regenerated vectors, no re-freeze. Making it
pass would mean loosening thresholds or the target, which is tuning to a gate and was ruled out.

If a family gate is still wanted, the open design questions are which signals count as separate families, how long the window is, and
whether the loss in recall is acceptable in exchange for fewer interruptions; that is a product decision, not something this probe settles.
