# Round 1 plan vs delivered

What the Round 1 deck (14 pages, team DEV MATRIX) promised, and what this repository does now. Written so a judge can check any row
against the code. **All detection numbers are from simulators (SatarkSim), not real users.**

Status words: **Built** (works as promised), **Changed** (built differently, reason given), **Cut** (decided against, with the evidence),
**Not yet** (needs a phone, an account or a partner that does not exist yet).

## Signals and decision

| Round 1 promise (page) | Status | What exists now | Why |
|---|---|---|---|
| Five signals read on the phone, metadata only: unknown live call, remote-access app, new payee, amount above 3x own median, payee risk (6) | **Changed** | The detector reads call, video, installs, watch-listed apps, new payee, amount against the user's own baseline, repeat payee and event order (16 features). No audio, no message content. | Features were refined while building the simulator; the payee-risk signal is not available (next row). |
| DoT Fraud Risk Indicator rating of the payee (+2 points) (6) | **Not yet** | Not built (`docs/ROADMAP.md`). | The feed goes to payment service providers and banks, not to an app. Needs a partner. |
| Points scoring with a ladder: LOG 0-3, NUDGE 4-5, PAUSE 6-8, ESCALATE 9+ (6, 7) | **Changed** | A logistic weight-of-evidence score with a per-age-band conformal threshold. Levels: NONE, LOG, NUDGE, HARD, TRUSTED_CONTACT (`contracts/api.yaml`). Points exist for display only (`detector/tools/points.py`). | The deck's weights were marked "to be calibrated". Learned weights plus a calibrated threshold let us set the false-alarm rate directly. |
| At least two signal families within 60 minutes before any pause (6, 7, 9) | **Cut** | Probed, not implemented (`detector/experiments/signal_family_gate.md`). | On simulated data it loses 24 of 538 caught scams (recall 93.1% to 88.9%, under the 93% target) to remove 1 of 7 false alarms. Tuning around the target was ruled out. |
| Novelty detector sending rare sequences to an analyst queue (6) | **Cut** | Not in the app, server or detector. It exists only in the Round 1 simulator folder. | Out of scope for the build window; not claimed. |
| Scammers adapt: red-team variants that drop one signal (8, A3) | **Changed** | Built two tests: a split-payment evasion test with a split guard (`ops/eval/split_guard.py`) and a signal-family probe. **Result:** splitting payments does not evade the shipped detector (even cutting every payment below the victim's own median, all 578 validation scams are still caught); what it costs is timing, with interdiction before the first payment falling from 83.9% to 57.6%. The guard does not change that. `ops/eval/gen_variants.py` writes scam-pretext outlines but has **not been run** (needs an API key). | The detector reads behaviour signals, not wording, so text variants only help the red-team report. |

## Intervention, people and privacy

| Round 1 promise (page) | Status | What exists now | Why |
|---|---|---|---|
| A pause with a plain-language reason and three choices: call trusted contact, hold 30 minutes, continue (5) | **Built** | `AlertScreens.kt`: reasons, call contact, hold 30 minutes, continue anyway; read-aloud button. | |
| Never auto-block; the user keeps the final choice (5, 7) | **Changed** | The server HOLDs a flagged payment started inside Satark; the user can still choose "Continue anyway". A payment started in GPay or PhonePe can only be warned about. | A hold is the only intervention the app can enforce, and only on its own payment path. |
| One alert per incident; repeats within 60 minutes merged (7) | **Built** | `AlertMerger` folds a repeat alert of the same kind within 60 minutes into the first (no second screen, pause or push); the time survives a restart. Counters are local. | |
| Nudge budget of at most 1 per user per month (7) | **Not yet** | No per-user cap and no tool that measures the budget. The deck called it a design target. | Not built; a measurement tool would be the first step. |
| Trusted contact accepts first, sees one line, cannot approve, can be removed (9) | **Built** | pending / accepted / revoked states, accept and decline endpoints, one short line, remove button. | |
| Real push to the trusted contact (A1) | **Not yet** | Server side is fixed and tested (a credential bug would have crashed the first real alert) and `ops/e2e/check_push.py` tests delivery. **No Firebase project or credentials exist yet.** | Needs an account owner to create the project. |
| Analyst reviews the worst cases; role-based access and an audit log (9) | **Built, small** | Admin-only console: list alerts, Approve or Clear, every action written to `audit_log`. | The deck's "score 9+ always goes to an analyst" is now "alerts go to the console". |
| One-tap report to 1930 or NCRP, only with consent (9) | **Changed** | A summary prepared on the phone plus a dial-1930 button, labelled "Prepared summary; not submitted to NCRP". | Submitting to NCRP needs an integration we do not have. |
| Evidence stays on the phone for 7 days (5, 9) | **Built** | `EventPurgeWorker` removes events older than 7 days. | |
| Only flags and bands leave the phone; no audio, messages, contacts, location, PIN or OTP (9) | **Built** | On-device scoring; payee ids are salted hashes; `/signature` rejects personal-data keys; a privacy check exists in the app. | |
| "This was legitimate" is one tap and tunes that user's weights (7, 9) | **Not yet** | The server records "Continue anyway". Nothing learns from it and there is no separate legitimate tap. | Learning from overrides is Phase 2. |
| Hindi and English with read-aloud (9) | **Changed** | Hindi reason sentences were drafted by Claude and **need review by a native speaker**; only the reason sentences are translated. | No translator was available. |
| False-pause rate by age band, language and device tier; a gap above 1.5x blocks release (9) | **Changed** | Gate by age band, activity tier and call-state availability (standing in for device tier). Language is skipped: the simulator has no language field. The false-alarm ratio is "n/a" in every dimension (some cohort has under 5 false alarms), so only the recall ratio is enforced. | Honest limits of the simulator. |

## Platform and proof

| Round 1 promise (page) | Status | What exists now | Why |
|---|---|---|---|
| Device attestation with Play Integrity (A3) | **Changed** | Android Key Attestation, verified by 7 server checks against pinned Google roots. | Key Attestation proves the key is in secure hardware and which app and signing certificate asked; it does not prove Play licensed the install. |
| On-device scoring, 100 ms target; risk API timeout 300 ms, then the on-device tier stands (A2) | **Built / not measured** | The 300 ms timeout and fallback exist (`RiskTimeout`). The 100 ms scoring target has not been measured. | |
| Degraded mode when device signals are unavailable (A1) | **Built** | Banners for each unavailable protection; defaults in `contracts/schema.json`. | |
| Shadow mode first (10) | **Not yet** | A shadow switch exists (decisions reported as LOG), but it has never run on real payments. | Needs a payment-provider partner. |
| Risk API `POST /v1/assess` (A3) | **Changed** | `POST /risk-check` takes the on-device decision and creates a held or allowed payment, plus a verified Razorpay test-mode checkout, a signed webhook and a payee fan-in rule that holds a mule-like payee. | Extra scope beyond Round 1. |
| Android signals on a physical phone (10) | **Not yet** | 36/36 test vectors pass on an emulator and the JVM. The run on two physical phones, which the detector freeze requires, is outstanding. | Needs the phones. |
| Simulation: 1,000 scam and 10,000 legitimate sessions (A3) | **Built, larger** | SatarkSim v2: 53,000 sessions with look-alike legitimate cases, device noise and a week-6 drift. | |
| A signed APK on a download link, a server on Render (10) | **Not yet** | The release workflow and tools are prepared (`ops/release/`), never run. | Needs the keystore, secrets and a Render deploy. |

## The numbers, side by side

These are **not comparable**: different simulator, different detector, different definitions. They are listed so nobody mistakes one for the other.

| | Round 1 deck (page 8) | Now |
|---|---|---|
| Data | 11,000 synthetic sessions (satark-sim, seed 20261012) | SatarkSim v2, 53,000 sessions; validation split 10,465 |
| Scams caught | 65% flagged, 37% reached Pause | 93.1% recall on validation (538/578); **90.8%** on three fresh draws (8,168/9,000) |
| Legitimate sessions | 0.25% paused, 1.75% flagged | 0.071% false alarms on validation (7/9,887); 0.063% on fresh draws (94/150,000) |
| Cloned-voice / family-emergency scam | 63% flagged, 20% Pause | 56.6% on validation, **43.9%** on fresh draws |

The family-emergency scam is the weakest result in both the deck and now. Real family emergencies in the simulator trigger 3.9% false alarms
on the fresh draws, so the detector cannot yet tell a genuine emergency from a scripted one. See `ops/eval/reports/fresh_seed_report.md`.

## Still open, and why it is not faked

- **Sealed held-out run.** `ops/heldout/run_heldout.py` refuses unless the `detector-freeze` tag exists, and the held-out file is not on this machine. The set can be run once. It waits for 36/36 on two physical phones.
- **Real-phone attestation, Firebase push, Render deploy, signed APK:** each needs a person with the phone, the account or the signing key.
- **Real-world accuracy:** unknown. Every figure above is simulated.
