# Progress (branch feat/medium-features, from feat/small-features)

Builds: JDK 21 (`~/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2`) and `ANDROID_HOME=~/AppData/Local/Android/Sdk`.
Earlier rounds (11 small features + closing work) are merged or pushed; see git log.

## Medium-size features: status
1. DONE trusted contact must accept (pending/accepted/revoked, migration e6b1c7a49d03, accept/decline/requests/remove endpoints, push only to accepted, one short line; app panel on the contact's phone + remove button). ops/e2e updated; e2e 58/58.
2. DONE Report fraud (on-device summary, Share + Call 1930, "Prepared summary; not submitted to NCRP"); amount shown as a band only.
3. DONE Hindi: reason_strings_hi.json (machine-drafted by Claude, NOT Sarvam; needs native review), values-hi, validator, PROVENANCE.md, language setting (English/Hindi/phone). Only the reason sentences are translated.
4. DONE screen-recording source (API 35+, own window only), UNSUPPORTED below 35, in SignalStatus.screenRecording and the log only; never a detector input; does not affect allAvailable.
5. TODO analyst console
6. TODO points display fields (Explainer.kt)
7-10. TODO ops items (fairness, GBT, LLM variants, dashboard)
11-12. TODO check heldout_result.md first; STOP if it exists
13. TODO docs/ROADMAP.md

## Notes
- run_e2e.py sometimes dies with a connection reset on the first run after code changes (seen twice, passes on rerun); cause not found.
- Not run on a phone/emulator; no emulator image installed.
