# Satark app: end-to-end log (M1)

Runs of the Android app against the backend. Each row is one scripted run; failures that were fixed are listed with
the commit that fixed them.

**Setup for every run below**

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

## Defects found and fixed (all on `role_1`)

| | Defect | Fix | Commit |
|---|---|---|---|
| A | Debug build blocked plain HTTP, so it could never reach the local server | Debug-only network config for `10.0.2.2`/`localhost`; release stays HTTPS-only | `5b3b323` |
| B | Call start sent before the number arrived → `caller_known` always missing → unknown-call rules never fired | Wait up to 2 s for the number; phone-state broadcast drives calls below Android 12 | `5b3b323` |
| C | Two registrations at once mixed device id and token → `/alert` 403 | Registration serialized, session written in one commit, self-repair | `5b3b323` |
| D | Alarm waited for the next 30 s tick | Events released right after the 1.5 s reorder hold | `5b3b323` |
| E | App killed mid-scam lost the detector session → ₹25,000 payment ALLOWed | Session rebuilt from the last 3 h of stored events; blank call start ignored during an open call | `5b3b323` |
| F | Offline queue only flushed at app start | Flush on network available; one flush at a time | `7c3eb5c` |
| G | Razorpay error left the user waiting 60 s | Short check, then a plain "did not complete" message | `7c3eb5c` |
| H | Video session closed after ~2 min without new usage events | `VideoSessionTracker` keeps it open while the app is in front | `1b82773` |
| I | Video always sent with an unknown-or-missing caller, so the long-session rule could never fire | `VideoOrigin`: video during/≤15 min after an unknown call is unknown | `1b82773` |
| J | Alarm only visible inside Satark, which the user is usually not looking at | High-priority notification on every alarm | `1b82773` |

## Not covered here (needs others or a physical phone)

- Key Attestation, refresh after expiry, re-register: needs M4's `/auth/*` merged; StrongBox/TEE needs a real phone.
- Trusted-contact link and push received on a second device: needs a Firebase project (`google-services.json`).
- Razorpay test-mode `paid` path and webhooks: needs a Razorpay test key on the server and the app.
- Readable reasons on screen: needs M4's `strings.xml`.
- QR scan with a real camera, ₹1 to a real VPA through GPay/PhonePe, the older test phone (minSdk 26), and the
  final two passes on both phones, the last on the release build.
