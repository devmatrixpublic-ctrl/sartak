# app (M1): Android application

Kotlin + Compose. Consumes `detector` (M2) through an included build and talks to `server` (M3) per `contracts/api.yaml`
and `contracts/auth.md` (M4).

| Package | Plan item |
|---|---|
| `signals/` | 1.1 Call, Usage, Install, Watchlist sources + `SignalStatus`; `SignalService` keeps them alive |
| `events/` | 1.2 `EventMapper`, `Deduplicator`, `EventSequencer`, `SessionPolicy`, Room storage, `EventDispatcher` |
| `ui/onboarding/` | 1.3 permission steps, degraded-mode banners, trusted contact; the same screen is "Protection and trusted contact" later |
| `ui/alerts/` | 1.4 Nudge / Hard / Trusted-contact / Long-session screens, `AlertController`, alarm notification; `Friction` (scam playbook, purpose question, payment pause) |
| `ui/theme/` | Satark colours (light and dark), the shield mark, `SatarkHeader`; the launcher icon is in `res/` |
| `push/` | 1.4 trusted-contact push: pairing code, Firebase Cloud Messaging, the alert shown on the contact's phone |
| `payments/`, `ui/pay/` | 1.5 QR scan, `UpiUriParser`, hand-off, checkout, result reporting |
| `net/` | 1.6 Retrofit client, retry/backoff, token refresh, offline queue |
| `security/` | 1.7 Key Attestation, encrypted token store, certificate pins |
| `ui/debug/` | Debug builds only: attestation chain export for M4 |

Contracts owned here: `contracts/watchlist.json`, `contracts/upi.md`. Runs and defects: `e2e_log.md`. Privacy data flows:
`privacy_check.md`.

## Build

Needs JDK 21 and the Android SDK (platform 36). The Gradle wrapper is in the repo root (Gradle 9.7.1, AGP 8.9.1).

```bash
./gradlew :app:assembleDebug                      # talks to http://10.0.2.2:8000/ (a server on the emulator's host)
./gradlew :app:assembleDebug -PsatarkBaseUrl=https://<server>/ -PsatarkPins=sha256/...,sha256/...
```

| Property | Meaning |
|---|---|
| `satarkBaseUrl` | Server URL. Release builds allow HTTPS only; debug also allows `http://10.0.2.2` and `http://localhost`. |
| `satarkPins` | Certificate pins from `contracts/pins.txt` (M4), comma-separated. Empty means no pinning. |
| `satarkRazorpayKey` | Razorpay **test** key id for checkout. Without it checkout fails with a clear message. |
| `satarkLongSessionTestMin` | Debug only: shortens the 2 h long-session rule for a labelled demo build. |

Release signing reads `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` (or the `SATARK_*` names).

## Trusted-contact push

The person who wants protecting pastes their trusted contact's **pairing code** (`<device id>:<push token>`) into
"Protection and trusted contact"; the app sends it to `POST /trusted-contact`. The contact gets the code on their own
phone with **Show my pairing code**. When the protected phone raises an alarm it calls `POST /alert`, and the server
pushes to the contact through Firebase Cloud Messaging.

* **Firebase config.** Put the project's `google-services.json` at `app/google-services.json` (git-ignored: it is per
  environment, and its API key would trip the secrets scan). The Google services plugin is applied only when the file
  exists, so builds without it still work and the screen says push is not set up. CI release builds need the file
  from a secret (M4).
* **Privacy.** Firebase auto-init is off: a phone registers with Firebase only when its user taps
  **Show my pairing code**. Analytics are off. The contact's alert says who to call, not what was paid.
* **App in the background.** The server sends a `notification` payload, which Android shows by itself with the
  server's title and body (today the raw reason codes). The app's own wording appears only while it is open. A
  data-only message from the server (M3) would let the app show its own text every time.
* **Token changes.** The token reaches the server only via the protected person's app, so a new token means they
  must link again. The contact's phone shows a notification when that happens (after a code was first shown).
* **Without Firebase** (debug builds): `adb shell am broadcast -n com.satark.app/.push.DebugFakePushReceiver --es type alarm`
  (or `long_session`) shows the alert exactly as a push would.

## Friction ladder (app-side rungs of the improvements roadmap, section 3.4)

Only rungs that work inside the app alone. They add caution on top of the detector; nothing here releases a held payment,
lowers a score or sends data anywhere.

1. **Playbook** (`Friction.playbook`): the scam the reasons point to ("digital arrest", screen sharing, sideloaded app,
   unknown caller, new payee), shown on the Hard, long-session, contact and "payment on hold" screens.
2. **Purpose question**: "What is this payment for?" with six answers; each explains the matching scam. The answer is not
   stored or sent.
3. **Payment pause** (`PaymentPause`): after a Hard alarm or a held payment, **Check and pay** is locked for 15 minutes, then
   the person types one sentence. State is in the encrypted `TokenStore`, so it survives a restart; a clock set back cannot
   stretch it. Debug builds have an "End pause" button. Rung 4 (trusted contact approves or blocks): after a hold the app sends the contact a push carrying the payment id
   (a second push, beside the generic alarm one). Tapping it opens `ContactDecisionScreen` (no payee or amount shown) with
   Approve / Block, which calls `POST /payments/{id}/decision`. The held person's screen polls the payment for up to 10
   minutes: approve starts the UPI hand-off or the checkout, block ends it, no answer leaves it held. Unit-tested; not yet
   run on two real phones.

## Stubs (`@SatarkStub`, release build must fail while any remain)
- Debug builds fall back to M4's `/auth/dev-token` when Key Attestation is refused (`net/Network.kt`). Remove it,
  together with M4's two server-side markers and the entry in `ops/ci/planned_stubs.txt`, once a real phone registers
  through `/auth/device`.

## Tests

```bash
./gradlew :app:testDebugUnitTest            # JVM: parser, mapper, dedup, sequencer, session policy, M2's 36 vectors through
                                            # the app pipeline, API contract, privacy, push pairing code
python app/tools/phone_check.py --build     # one connected phone: 36 vectors on the device, attestation chain for M4,
                                            # fresh-install onboarding, permissions revoked (prints rows for e2e_log.md)
./gradlew :app:connectedDebugAndroidTest    # the instrumented tests only (uninstalls the app afterwards)
```
