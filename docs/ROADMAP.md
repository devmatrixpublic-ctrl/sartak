# Roadmap: Phase 2 (not built)

Nothing on this page exists in the product today. It lists what was deliberately left out of the first version, so no one mistakes
it for a finished feature. All detection results in this repository are on simulated data.

| Item | Status | Why it is not built |
|---|---|---|
| **DoT Financial Fraud Risk Indicator (FRI) rating of the payee** | Not built | The feed is available to payment service providers and banks, not to an app. It needs a PSP partner. |
| **Embedding in a real PSP or bank app, with a shadow-mode pilot** | Not built | Needs a partner willing to run Satark beside live traffic. Shadow mode (score and log, show nothing) exists in the app as a switch, but has never run on real payments. |
| **Play Integrity** | Not built | Android Key Attestation is used instead. It proves the key lives in secure hardware and which app and signing certificate asked for it, but it does not prove that Google Play licensed the install. |
| **Learning from overrides** | Not built | The server records that a person chose "Continue anyway" on a held payment, and the app keeps local alert counters. Nothing learns from them and no threshold, weight or cohort is tuned from overrides. |
| **Real-world accuracy and a live A/B test** | Not done | Every result (recall, false alarms, fairness, the boosted-model comparison) is on SatarkSim, a simulator. Real accuracy is unknown, and at a realistic fraud rate even a 0.1% false-alarm rate gives a precision well under 1%. |
| **Local differential privacy noise on signatures, and CUSUM outbreak detection** | Not built | Signatures are stored without any device identifier, but they are not noised and nothing watches them for a sudden rise in one scam pattern. |

Also open from earlier rounds: the sealed held-out run, and the detector re-freeze (see `detector/FREEZE_CHECKLIST.md`).
