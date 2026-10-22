# Satark app: privacy data-flow check (M1)

The plan's privacy rule: **no call content and no raw phone numbers leave the phone, VPAs are always hashed, and only
signatures (no personal data) are shared for pattern detection.** This document checks the app against that rule: by
reading the code for every way data can leave or be stored, then by a live run with canary values.

Checked on 2026-10-22, `role_1`, debug build on an Android 15 emulator against the local M3 server. Automated guard:
`app/src/test/kotlin/com/satark/app/PrivacyTest.kt` (runs with the unit tests).

## What never enters the app's pipeline

| Data | How it is kept out |
|---|---|
| Call audio, call content | Never accessed. No `RECORD_AUDIO` permission. |
| Phone numbers | The caller's number is used once, on the phone, for a contacts lookup (`CallSignalSource.isInContacts`), and dropped. `RawSignal.CallStarted` has only a time and `callerKnown` (true/false/unknown). `PrivacyTest` fails if any signal type gains an unreviewed field. |
| Contact names | Never read: the lookup returns only a count. |
| Raw VPA | Hashed on the pay screen before anything else sees it: `payee_hash = SHA-256(per-install salt ‖ lowercase(trim(vpa)))` (`contracts/upi.md`). The salt is random per install, so the same payee has a different hash on every phone and the server cannot link users. |

## What leaves the phone, and to whom

| Destination | What | Why |
|---|---|---|
| Satark server `/auth/*` | Public key, attestation certificate chain, challenge | Device registration (`contracts/auth.md`) |
| `/risk-check` | Decision level, score, up to 3 reason codes, method, **amount**, **payee_hash**, is_p2p | The server records the payment and decides HOLD/ALLOW (`api.yaml`). The amount is linked to the device here by design: it is a payment record. |
| `/payments/{id}/result` | `success`/`failure`, the UPI app's transaction ref (max 128 chars) | App-reported outcome |
| `/alert` | Device id, `alarm`/`long_session`, reason codes | Trusted-contact push |
| `/signature` | Pattern id + the detector's 16 numeric feature values | Stored by the server **without** a device id (`signatures` table has no device column) |
| `/trusted-contact` | The trusted contact's device id and push token | Linking |
| The UPI app the user picks | `upi://pay` with VPA, name, amount, note | Needed to pay; it is the user's own payment app, started by the user |
| Razorpay checkout | Order id, amount, currency, "Satark" | Test-mode checkout. No VPA. |
| Google (Firebase Cloud Messaging) | A Firebase installation id and this phone's push token. **Only after the user taps "Show my pairing code"** (auto-init is off in the manifest); analytics are off | To receive trusted-contact alerts. Phones that never show a code never contact Firebase (checked: with a Firebase config present, no registration call at startup) |
| Through Google, to the contact's phone | The alert the server sends: today a title, a body made of the raw reason codes, and the data `type` and `owner_device_id` | The contact's alert. The app's own text for the contact names no payment details, but Android shows the server's body when the app is in the background (see open points) |

Release builds talk HTTPS only (`res/xml/network_security_config.xml`); certificate pins are added once
`contracts/pins.txt` exists.

## What stays on the phone

| Store | Contents | Retention |
|---|---|---|
| Room `event_queue` | Event type, time, app package names, install source, payee **hash**, amount | **24 h** (pruned at start and hourly; before this check it was never pruned and grew into a full app-usage history) |
| Room `decision_log` | Time, level, score, reason codes | 30 days |
| Room `known_payee` | Payee hashes | Until uninstall |
| Room `completed_payment` | Amounts of completed payments (for the user's baseline) | Until uninstall |
| Room `queued_call` | Pending `/alert` and `/signature` bodies | Until sent |
| `EncryptedSharedPreferences` | Tokens, device id, payee salt, age band, onboarding flag | Until uninstall; encrypted with an Android Keystore key |

Backup: `allowBackup="false"`, `fullBackupContent="false"`, and `data_extraction_rules.xml` excludes everything from
both cloud backup and **device-to-device transfer** (Android 12+; `allowBackup` alone does not cover transfer).
Added in this check.

Logs: no log line contains a number, VPA or token. Debug builds log HTTP bodies (hashes, amounts, reason codes) with
`Authorization` redacted; release builds log no HTTP traffic.

## Live check with canary values

Unknown call from **9123456780**, AnyDesk sideloaded during the call (alarm, `/alert`), then a ₹7 payment to
**privacy.canary@upi** handed to the test UPI app, which reported success.

| Where searched | Number | VPA |
|---|---|---|
| Every request body the app sent (`/alert`, `/risk-check`, `/payments/{id}/result`) | 0 | 0 (only the 64-hex hash) |
| The app's own log lines | 0 | 0 |
| Every file in the app's data directory (134 files: database, preferences, caches) | 0 | 0 |
| Server database and server log | 0 | 0 (the server holds only the hash) |

## Result

Pass, after two fixes made during this check (event retention, device-transfer exclusion).

## Open points

- **Physical phones**: repeat the canary run on both test phones (vendor dialers and backup tools differ).
- **Push content (M3)**: the server's push puts the protected person's reason codes (e.g. `F_NEW_PAYEE`) in the
  notification body, which passes through Google and shows on the contact's lock screen when Satark is in the
  background. A data-only message (`type` only, high priority) would keep those details off Google's notification
  payload and let the app show its own wording, which has no payment details.
- **Firebase on a real project**: repeat the startup check (no Firebase traffic before "Show my pairing code") with the
  team's Firebase project; the check above used a dummy project.
- **For M3/M4, not privacy**: noticed during the run. A sideload-during-call alarm had fired, yet a ₹7 payment to a new
  payee in the same call was allowed (the payment's own score was low). The server holds only on the payment's own
  decision. Whether a session that already raised a HARD alarm should hold every payment is a product decision for
  M2/M3.
