# Small-features progress (branch feat/small-features, stacked on feat/app-contact-approval)

Setup for builds: JDK 21 (`~/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2`) and `ANDROID_HOME=~/AppData/Local/Android/Sdk`.

## Done (one commit each)
1. Hard screen buttons: Call trusted contact / Hold payment 30 minutes / Continue anyway.
2. Server override: `override` + `payment_id` on POST /risk-check, `held -> allowed_by_user`, `user_override_at` (migration c1a8f3d20e57); app "Continue anyway" calls it. Only detector holds can be overridden (not payee_fan_in).
3. `payments.amount_band` replaces `amount` (migration d4e9b6a3c812, backfills, reversible). Because the amount is no longer stored, a contact's approval of a checkout payment no longer creates the order; the owner's app fetches it via the override call (amount must be in the same band).
4. Call trusted contact: ACTION_DIAL; only the contact's content URI is stored (TokenStore.dialContactUri), the number is read at dial time. "Choose the person to call" button in Protection settings.
5. `Level.LOG` (silent, never shows a screen; server treats as ALLOW) and shadow mode (`TokenStore.shadowMode`, no UI toggle yet): score and log only.
6. validate_strings.py fails on URLs and on PIN/OTP.
7. WorkManager `EventPurgeWorker` (daily, deletes event_queue rows older than 7 days).
8. 300 ms timeout on the risk call: alarm -> Held; clean upi_intent -> proceeds with a `local:` id; clean checkout -> fails (needs the server's order).

## In progress
(none)

## Remaining
9. DONE: consent screen (first run, revocable switch in Protection settings, gates SignalService) + "Delete my data" (clears Room and the encrypted store; the server keeps its device record, no server delete yet).
10. TextToSpeech read-aloud button on alert screens.
11. Merge repeat alerts within 60 minutes; local per-user alert counters in Room.
Items 12-14 need a vector re-freeze; not started, on hold until asked.

## Not verified
Nothing here ran on a phone or emulator. Item 8's 300 ms budget will often be missed on a cold Render instance.
