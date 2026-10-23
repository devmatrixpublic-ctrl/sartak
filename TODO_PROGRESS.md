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

## Medium-size features: final status (branch feat/medium-features, not pushed)
1-6 DONE (see earlier sections). 
7 DONE with the owner's rule: false-alarm ratio only counts when every cohort has >=5 false alarms (otherwise n/a, not a failure);
  recall ratio gate stays strict (1.07 / 1.02 / 1.10, limit 1.5). In SatarkSim every dimension has a cohort with <5 false alarms, so the
  false-alarm ratio is n/a everywhere: the simulation cannot show whether false alarms differ between cohorts.
8 DONE gbt_baseline.py + report: boosted model 96.0% recall / 3 false alarms vs logistic 92.7% / 7 (payment score only); intervals overlap.
9 DONE gen_variants.py + data/llm_variants/PROVENANCE.md. NOT RUN: no ANTHROPIC_API_KEY. data/llm_variants/ has no variants yet.
10 DONE ops/dashboard/build.py -> dashboard.html (static, every figure labelled simulated). Alert counts need --db; none given, so that section says so.
11 NOT IMPLEMENTED on purpose. heldout_result.md does not exist and no gate existed, but a probe (detector/experiments/signal_family_gate.md)
  shows a 2-family gate cuts recall 93.1% -> 88.9% (below the 93% target) for 1 fewer false alarm. Not tuned around.
12 SKIPPED (only applies if 11 was done). Note: there is no detector-freeze tag in this checkout and no heldout/ directory.
13 DONE docs/ROADMAP.md and README limitations. (The app logs "Continue anyway" server-side; there is no separate "this was legit" tap, so the wording says so.)

## Still needs a device, account or decision
Room v1->v2 and everything else on a real phone; Sarvam/real Hindi review; an API key for item 9; a product decision on the family gate.
