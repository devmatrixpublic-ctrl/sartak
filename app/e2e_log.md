# Satark app: end-to-end log (M1)

Runs of the Android app against the backend. Each row is one scripted run; failures that were fixed are listed with
the commit that fixed them.

**Setup for runs 1 to 20** (later runs list their own setup)

| Item | Value |
|---|---|
| Device | Android emulator, Pixel 6 profile, Android 15 (API 35, `google_apis` x86_64). **Not a physical phone.** |
| App | `role_1` debug build (`./gradlew :app:assembleDebug`), long-session runs use `-PsatarkLongSessionTestMin=2` |
| Server | `server/` from this branch (main's M3 backend), local SQLite, `uvicorn --host 0.0.0.0 --port 8000`; app uses `http://10.0.2.2:8000/` |
| Auth | Dev-token stub (`/auth/challenge` answers 404 on this server, app falls back). Key Attestation not exercised. |
| Detector | M2 detector as linked by `includeBuild("detector")` (JVM build, `model.json` from `feat/m2-detector` at `8b6b1df`) |
| Reason text | Raw reason codes (`@SatarkStub`): M4's `strings.xml` not on this branch |

**Test helpers (emulator only, not part of the app)**

| Helper | How |
|---|---|
| Unknown call | `adb emu gsm call 98765000NN` then `adb emu gsm accept …` / `cancel …` (number not in contacts) |
| Sideloaded remote-access app | Throw-away APK with package `com.anydesk.anydeskandroid` (on the watch-list), installed with `adb install` |
| UPI app | Throw-away APK that handles `upi://pay` and returns `Status=SUCCESS&txnRef=REF123` |
| Video app | Throw-away APK with package `com.whatsapp` showing one screen |
| Permissions | `adb shell pm grant/revoke`, `adb shell appops set com.satark.app GET_USAGE_STATS allow/deny` |
| Offline | `adb shell svc wifi disable; adb shell svc data disable` (calls still work) |

## Runs (2026-10-22)

| # | Path | Steps | Expected | Result |
|---|---|---|---|---|
| 1 | First launch | Fresh install, open app | Onboarding with plain-language reasons; "Reduced protection" banner for missing permissions | Pass |
| 2 | Offline, no alarm | Server stopped, pay ₹1 to `test@upi` | "Can't reach Satark… no payment was made"; no intent | Pass |
| 3 | Clean, no UPI app | Server up, pay ₹1 | `/risk-check` → ALLOW; "No UPI app is installed on this phone"; no crash | Pass, after fix A |
| 4 | Clean hand-off | Fake UPI app installed, pay ₹1 | Chooser → UPI app → "The UPI app reported success (not verified by Satark)"; `POST /payments/{id}/result` 200 | Pass |
| 5 | Scam: sideload during unknown call | Unknown call → accept → sideload "AnyDesk" | `RULE_SIDELOAD_DURING_CALL` HARD screen within seconds; `/alert` 200 | Pass, after fixes B, C, D |
| 6 | Scam: payment during the scam, app killed in between | Run 5 → `am force-stop` → reopen → pay ₹25,000 to new payee | Detector still remembers the call and sideload; HARD (`F_INSTALL_SIDELOAD_DURING_UNK`, `F_UNK_X_NEWPAYEE`, `F_WATCHLIST_APP`); `/risk-check` → HOLD; no UPI app opened | Pass, after fix E |
| 7 | Alarm while offline | Wi-Fi + data off → run 5 | `/alert` fails and is queued; on reconnect it is sent (200) and the queue is empty | Pass, after fix F |
| 8 | Offline + alarm payment | Wi-Fi + data off, scam session, pay ₹30,000 | "Payment on hold. Satark did not send this payment. Nothing was paid."; no intent | Pass |
| 9 | Permissions revoked | Revoke phone, contacts, usage access → reopen → place a call | No crash; banners "Call signal is off" and "Usage signal is off" | Pass |
| 10 | Checkout without a Razorpay key | Pay ₹1 via "Satark checkout (test)" | Razorpay errors → "Checkout did not complete. No payment was made." within seconds | Pass, after fix G |
| 11 | Long session (test build, 2 min) | Unknown call → hang up → fake video app for 2.5 min | Session marked unknown; `RULE_LONG_SESSION`; `/alert type=long_session` 200; notification shown over the video app | Pass, after fixes H, I, J |

### Against M4's server (PR #9, `origin/m4` at `01e039d`, run from a separate checkout, not merged)

Server: `SATARK_ENV=dev SATARK_AUTH_ENABLE_DEV_TOKEN=1`, port 8001; app built with `-PsatarkBaseUrl=http://10.0.2.2:8001/`.

| # | Path | Expected | Result |
|---|---|---|---|
| 12 | Upgrade from the old dev token | Old bearer rejected (401) → challenge → emulator attestation refused (503: no roots configured in dev) → `/auth/dev-token` → JWT + refresh token; `/risk-check`, `/alert`, `/signature` 200 | Pass, after fix K |
| 13 | Restart after a video session ended while the app was dead | No stale "video still active" alarm | Pass, after fix L |
| 14 | Run 6 again (app killed mid-scam, ₹25,000) | HARD → HOLD, no UPI app opened | Pass |
| 15 | Clean ₹1 hand-off | ALLOW → fake UPI app → reported success | Pass |

### Detector in the app: M2's 36 test vectors

Run with `./gradlew :app:assembleDebug :app:assembleDebugAndroidTest`, install both APKs, then
`adb shell am instrument -w com.satark.app.test/androidx.test.runner.AndroidJUnitRunner`
(or `./gradlew :app:connectedDebugAndroidTest`, which uninstalls the app afterwards). JVM version: `VectorsJvmTest`.

| # | Where | Path | Result |
|---|---|---|---|
| 16 | JVM | Detector only | 36/36 |
| 17 | JVM | App pipeline (stored as schema JSON and read back, app dedup, `SessionPolicy`) | 36/36, after fix M (was 33/36) |
| 18 | Emulator, API 35 | Detector only, `model.json` from the APK | 36/36 |
| 19 | Emulator, API 35 | App pipeline | 36/36 |

Still needed: the same run on both physical phones (plan 2.7). `python app/tools/phone_check.py --build` runs it and
prints the row in the form `detector/tools/freeze_preflight.py` counts (`Physical: ...` and `36/36`). Then M2 runs the
pre-flight and tags `detector-freeze`.

### Attestation chain export (for M4)

Debug builds show **"Export attestation chain for M4"** at the bottom of the pay screen. It fetches a challenge from
`/auth/challenge` (or makes a local one if the server has no auth routes), creates a key under its own Keystore alias
(the app's registration key is never touched), and opens the share sheet with a JSON file. It also saves the file to
`/sdcard/Android/data/com.satark.app/files/` (`adb pull` works). Format `satark-attestation-export/1`: device, package,
build type, **signing-certificate SHA-256** (what `SATARK_AUTH_EXPECTED_SIGNING_SHA256` needs), key security level,
challenge, public key, chain (leaf first).

| # | Where | Result |
|---|---|---|
| 20 | Emulator, API 35 | Pass: key level `software`; 3-certificate chain; challenge embedded in the attestation extension and leaf key = exported public key (checked with Python `cryptography`); root "Google Test LLC" as expected for an emulator. Share sheet opens. |

**For each physical phone:** install the debug build, tap the button, send the JSON to M4 (or run
`python app/tools/phone_check.py --build`, which does the same without tapping and saves the JSON under
`app/build/phone_check/`). Expect `TEE` or `StrongBox` and a chain ending at Google's hardware attestation root.

### On merged `main` (after PR #10): trusted-contact push, registration, phone check

Server: `main`'s backend (M3 + M4 auth) in dev mode, `SATARK_ENV=dev SATARK_AUTH_ENABLE_DEV_TOKEN=1`, port 8000, no
Firebase or Razorpay credentials (the server uses its stub push and order clients). App: `role_1` on top of `main`, no
`google-services.json` unless stated. Reason text: M4's generated `strings.xml`.

| # | Path | Expected | Result |
|---|---|---|---|
| 21 | Fresh install | Onboarding shows the new trusted-contact card; "Show my pairing code" without a Firebase config says push is not set up in this build | Pass |
| 22 | Protection screen | Pay screen → "Protection and trusted contact" (permission status, trusted contact); system back returns to the pay screen | Pass |
| 23 | Link a trusted contact (a second device registered on the server with the dev token) | Garbage → "does not look right"; unknown device → "not registered yet" (404); own code → "your own code"; the contact → "Linked."; the server stores the link and exactly the pasted token | Pass, after fix N |
| 24 | Alarm → push to the contact | Unknown call + sideload → `/alert` → the server sends to the contact's token (`alerts.delivered = 1`, stub push client) | Pass |
| 25 | The contact's phone receives a push (simulated with `DebugFakePushReceiver`) | High-priority "Someone you protect may be being scammed" and "Long video call with an unknown person" notifications | Pass |
| 26 | Firebase config present (dummy project, not committed) | Firebase initialises but makes no registration call at startup; "Show my pairing code" → Firebase refuses the dummy key → clear message, no crash | Pass |
| 27 | Registration on a fresh install | Exactly one registration (challenge → `/auth/device` refused in dev → `/auth/dev-token`) | Pass, after fix O |
| 28 | `python app/tools/phone_check.py --build --allow-emulator` | 36/36 both paths; attestation exported (challenge from the server); fresh install opens onboarding; permissions revoked → banners, no crash. The rows say "Emulator", so they do not count for the freeze | Pass |

### Redesign: theme, icon and the friction ladder

Same setup as above (`main`'s server in dev mode, Android 15 emulator, debug build). A fake UPI app is installed on this
emulator, so an allowed payment ends with "The UPI app reported success".

| # | Path | Expected | Result |
|---|---|---|---|
| 29 | Fresh install | Teal shield launch screen; "Set up Satark" below the status bar; "Satark never asks for your PIN or OTP" card; permission pills Off / On | Pass |
| 30 | Allow all permissions, Start protection | Pay screen with "Protection is on" | Pass |
| 31 | UPI ID `hello`, amount empty | "Enter a valid UPI ID and an amount." | Pass |
| 32 | Clean payment `shop@okaxis` 50 | Allowed, handed to the UPI app | Pass |
| 33 | Server stopped, payment `test2@upi` 10 | "Can't reach Satark. Check your connection; no payment was made." No crash | Pass |
| 34 | Unknown call, new payee `friend@okicici` 200 | "Take a moment" banner; payment allowed | Pass |
| 35 | Unknown call + sideloaded "AnyDesk" | Full-screen Stop with the reason, "Apps sent as a link or file are a trap", purpose question | Pass |
| 36 | Purpose answer, Cancel | Reply for that scam; amber "Payments are paused" with a 15:00 countdown; Check and pay greyed out | Pass |
| 37 | Held payment `refund@ybl` 25000 during the scam | Stop screen; "Payment on hold, nothing was paid" with 3 reasons and the playbook; pause restarts | Pass, after fix P |
| 38 | Close and reopen during a pause | Pause continues (13:59 left) | Pass |
| 39 | Clock moved 16 minutes on | "Type this sentence"; a wrong sentence is refused, the right one unlocks payments | Pass |
| 40 | Contact's simulated alert; dark mode; rotation; crash log | Notification shown; readable dark theme; typed values kept; `logcat -b crash` empty | Pass |
| 41 | `python app/tools/phone_check.py --allow-emulator` | 36/36 both paths; attestation exported; fresh install; permissions revoked. One run failed the fresh-install step because the launcher was still showing after the emulator booted; the same step passed when repeated | Pass |

### Razorpay test mode: the paid path

Server: `main`'s backend on a laptop in dev mode with a Razorpay **test** key, reached by Razorpay through a temporary
Cloudflare tunnel (the webhook URL in the dashboard pointed at the tunnel). App: debug build with `-PsatarkRazorpayKey`.
Android 15 emulator. The Razorpay test keys and webhook secret were shared in a chat, so they must be regenerated.

| # | Path | Expected | Result |
|---|---|---|---|
| 42 | Pay ₹1 with "Satark checkout (test)" | Satark checks first; the server creates a real test order at Razorpay (`POST /v1/orders` 200); checkout opens showing ₹1 | Pass |
| 43 | Webhook with a forged signature, through the tunnel | 400, logged as forged | Pass |
| 44 | A signed `payment.captured` sent by a script (simulation, not Razorpay) | 200 `processed`; payment `paid`; after closing checkout the app shows "Payment confirmed (test mode)." | Pass |
| 45 | Real checkout: phone number pasted, Netbanking, "Success" on Razorpay's demo bank page, webhook URL pointing at the Render address that had no server | Razorpay: payment `captured`, order `paid`. Our server never got the webhook, so the app ended on "Still waiting for confirmation. Check again in a moment." (correct: it never says paid without the webhook) | Pass (expected behaviour) |
| 46 | Same, with the webhook URL changed to the tunnel | Razorpay itself sent two webhooks (`Tr2SMoKTBIHoVk`, `Tr2SNCeLVX5NPY`), both 200; payment `allowed` → `paid`; the app shows "Payment confirmed (test mode)." | Pass |

Notes: Razorpay's form did not accept text typed through adb, and the emulator's keyboard was unusable here; the number was
pasted from the clipboard. Back in the checkout opens an "Are you sure you want to exit?" sheet (tap "Yes, exit"). Razorpay
rejected `9876543210` as an invalid number; `8123067459` was accepted. Not yet run against a deployed server.

### Full pass on `main` with the others' features (consent screen, Hold 30 minutes, Continue anyway, Report fraud)

Server: `main`'s backend in dev mode with a Razorpay test key; Android 15 emulator; debug build. 102 app tests and 229 server
tests pass; debug, release and androidTest builds succeed; no new stubs.

| # | Path | Expected | Result |
|---|---|---|---|
| 47 | Fresh install | "Before we start" consent, "I agree", setup, pay screen with "Protection is on" | Pass |
| 48 | Clean payment `shop@okaxis` 50 | Handed to the UPI app, no alarm | Pass |
| 49 | Unknown call, new payee | "Take a moment" banner, payment allowed | Pass |
| 50 | Unknown call + sideloaded app | Stop screen with the reason, playbook, purpose question, Report fraud, Read aloud; buttons Call trusted contact / Hold payment 30 minutes / Continue anyway | Pass |
| 51 | Purpose answer; Hold payment 30 minutes | Reply for the scam; pay screen with "Payments are paused" 29:5x; End pause (debug) clears it | Pass |
| 52 | Held payment `refund@ybl` 25000 | "Payment on hold, nothing was paid"; no UPI app opened | Pass |
| 53 | Contact's simulated alert; dark mode; crash log | Notification shown; app alive; `logcat -b crash` empty; no server errors | Pass |
| 54 | Real Razorpay checkout (₹1, Netbanking, Success) with the webhook on the same account as the keys | Razorpay sent two webhooks (`Razorpay-Webhook/v1`), both 200; payment `paid`; app shows "Payment confirmed (test mode)." | Pass |
| 55 | `phone_check.py --allow-emulator` | 36/36 both paths; attestation; fresh install; permissions revoked (the script now taps "I agree" on the new consent screen) | Pass |

Note for the Razorpay run: webhooks only arrive if the dashboard account is the account the API keys belong to (checked with
`GET https://api.razorpay.com/v1/webhooks`, which lists the webhooks of the key's account).

## Defects found and fixed (all on `role_1`)

| | Defect | Fix | Commit |
|---|---|---|---|
| A | Debug build blocked plain HTTP, so it could never reach the local server | Debug-only network config for `10.0.2.2`/`localhost`; release stays HTTPS-only | `d915f16` |
| B | Call start sent before the number arrived → `caller_known` always missing → unknown-call rules never fired | Wait up to 2 s for the number; phone-state broadcast drives calls below Android 12 | `d915f16` |
| C | Two registrations at once mixed device id and token → `/alert` 403 | Registration serialized, session written in one commit, self-repair | `d915f16` |
| D | Alarm waited for the next 30 s tick | Events released right after the 1.5 s reorder hold | `d915f16` |
| E | App killed mid-scam lost the detector session → ₹25,000 payment ALLOWed | Session rebuilt from the last 3 h of stored events; blank call start ignored during an open call | `d915f16` |
| F | Offline queue only flushed at app start | Flush on network available; one flush at a time | `e676ac7` |
| G | Razorpay error left the user waiting 60 s | Short check, then a plain "did not complete" message | `e676ac7` |
| H | Video session closed after ~2 min without new usage events | `VideoSessionTracker` keeps it open while the app is in front | `64fa08a` |
| I | Video always sent with an unknown-or-missing caller, so the long-session rule could never fire | `VideoOrigin`: video during/≤15 min after an unknown call is unknown | `64fa08a` |
| K | App could not authenticate against M4's server (it only knew "bearer = device id"); Android 8 crashed in key generation (`setIsStrongBoxBacked` is API 28+) | Debug builds fall back to M4's `/auth/dev-token`; StrongBox call guarded | `a627b52` |
| L | Session restore kept a call/video open whose end was missed while the app was dead → false `F_UNK_VIDEO_ACTIVE` | Sources report current state at start; restored video end is dated at the last event seen | `a627b52` |
| M | The app reset the detector after any 2 h gap, even during an open unknown video call: lost the long-session alarm (vectors S050008, S050139) and changed a decision M2 measured (S052021) | Reset only after 96 h of silence (longest SatarkSim session) and never while a call or video is open | `4782b89` |
| J | Alarm only visible inside Satark, which the user is usually not looking at | High-priority notification on every alarm | `64fa08a` |
| N | The pairing-code parser took any text glued after the code as part of the push token; the server accepts any string, so every alert to that contact would have failed silently | The token must have the FCM shape; over-long input is refused, not cut | `64de9b9` |
| O | Startup registered 2 to 3 times (MainActivity and AppGraph at once); with real attestation each registration is a new key, so the phone's device id would have changed | Re-check inside the registration lock | `997fb08` |
| P | A payment result ("The UPI app reported success") stayed on screen under a later "Payment on hold, nothing was paid" | A new payment attempt clears the old message | this branch |
| Q | The 300 ms risk-call limit also covered signing in (first payment after install: about 450 ms) and a Razorpay checkout (the server waits about 0.7 s for the order), so those payments ended with "Satark was slow to answer. No payment was made." | The app signs in before the timed call (up to 5 s); a checkout gets 10 s; the normal UPI path keeps 300 ms and its fallbacks | this branch |

## Not covered here (needs others or a physical phone)

- Key Attestation with a hardware key (TEE/StrongBox), refresh after expiry and re-register against a production-mode
  server: needs a real phone, M4's pinned Google roots and the signing digest on the server.
- A real push reaching a second device: needs a Firebase project (`app/google-services.json` for the app, credentials
  for the server). Linking and the server-side send are verified above with the stub push client.
- Razorpay `paid` path against a deployed server: verified above through a tunnel to a laptop server; repeat on the
  deployed server once it exists (webhook URL and secret must match it).
- QR scan with a real camera, ₹1 to a real VPA through GPay/PhonePe, the older test phone (minSdk 26), and the
  final two passes on both phones, the last on the release build.
