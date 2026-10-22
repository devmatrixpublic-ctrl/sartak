# Research behind the detector's data and method (2026-10-21)

Produced by a research pass run from a sandbox that **could not reach** NPCI, RBI, Sansad, Kaggle, Hugging Face, arXiv, Google Play or
most primary sources. So most figures are second-hand (press and search summaries) and many Android package names are from memory.
Every file labels what is real, second-hand or assumed; read those labels before quoting any number.

| File | What it is |
|---|---|
| `detector-data-and-modelling-report.md` | The synthesis: what real data exists (almost none), what must be simulated, base-rate precision, the build plan |
| `notes-real_datasets_access.md` | Which datasets are reachable, licences, what maps onto the 16 features |
| `notes-scam_playbooks_timing.md` | Indian coached-scam playbooks and the (thin) timing evidence |
| `notes-upi_behaviour_distributions.md` | Published UPI amount/volume/fraud statistics and the assumptions made |
| `notes-android_signals_watchlist.md` | Android API behaviour and watch-list package names (mostly unverified) |
| `notes-modelling_methods.md` | Conformal thresholds, imbalance, evaluation pitfalls, Kotlin parity |

The key conclusion: **no public dataset links call, install and payment events for Indian coached UPI scams**, so detection can only be
validated on simulation (SatarkSim) plus published aggregates. See `detector/detector_report.md` for the measured, simulated results.
