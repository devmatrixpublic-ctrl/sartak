# Notes for M1: driving the detector from the app

Written by M2 after reviewing `feat/m1-app` (commit `8b6b1df`). The pure-logic part of `app/` (parser, mapper, dedup,
sequencer, watch-list/contract checks) was compiled against this detector on the JVM and its 20 tests pass. The Android
module itself was not built (no Android SDK where this was reviewed), so nothing here has run on a phone.

## Already fixed in the detector (pull `feat/m2-detector`)
1. **Long-session alarm repeated on every tick.** `onTick` now raises it once per unknown video session. Before, the
   30 s tick in `EventDispatcher` would have re-emitted the alarm, and `AlertController` would have sent `/alert`
   (a push to the trusted contact) every 30 s.
2. **A retried payment inside the 3 s dedup window returned `NONE`.** The detector now returns the original decision for a
   repeated `PAYMENT_ATTEMPT`. Test: `IntegrationHazardsTest`.

## Still needs a change in `app/`
3. **App-level dedup has the same hole.** `Deduplicator` drops an identical back-to-back `PAYMENT_ATTEMPT` (a known payee
   tapped twice within 3 s) before it reaches the detector, then `submitAndDecide` returns `NONE`, `/risk-check` gets
   level `NONE`, and the server answers `ALLOW`. Fix: do not dedupe `PAYMENT_ATTEMPT` in the app (the detector handles it
   and now repeats the original decision), or have `submitAndDecide` return the last payment decision.
   (A first-time payee is not affected: `PayeeAdded` between the attempts breaks the "previous raw event" match.)
4. **`/signature` with an empty feature map.** For sideload and long-session alarms `a.trace` is null, so
   `SignatureRequest.features` is empty; the server rejects an empty map with 400 and the offline queue then drops it.
   Skip the signature call when there are no features.
5. **The app-side nudge has no reasons** (`Nudge(emptyList())`). The plan has nudge screens show reasons. If a nudge tier
   is wanted it should be calibrated inside the detector, not decided by `unknownCallActive && payeeIsNew`; tell M2.

## Design gap to decide as a team (not a bug)
6. **Unknown-origin video can never be detected on a real phone.** `UsageSignalSource` emits `VideoStarted(callerKnown = null)`,
   and the detector treats `null` as "not unknown" (documented in `contracts/schema.json`), so `unk_video_active` and the
   long-session rule never fire. In SatarkSim that rule is the main catch for the digital-arrest playbook (98.9% recall).
   Likewise `CallStarted.callerKnown` depends on READ_CALL_LOG + READ_CONTACTS and on the phone-state broadcast arriving
   before the telephony callback (a race), so it is often `null`. Expect real-phone behaviour closer to the "call state
   unavailable" mode than to the simulated results. Options: treat a video-app session as unknown when it starts within
   N minutes of an unknown call; or accept the gap and say so. Either way, the e2e "long session" demo needs a
   test build that fakes the signal.

## Contract alignment
- `contracts/upi.md` is the owner's contract; `detector/tools/upi_mapping.py` now follows it (SHA-256(salt || vpa), `am` > 0
  with at most 2 decimals, blank `mc` is P2P).
- `contracts/watchlist.json` equals `model.json` `watchlist` (3 packages). When M1 adds packages, M2 re-exports the model
  (`python detector/tools/export_model.py` reads the list from `params.json` today; tell M2 and it will read `watchlist.json`).
