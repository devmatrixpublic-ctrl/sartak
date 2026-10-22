# Running the Android app (against a local backend)

**What was verified:** GitHub CI builds the app and runs its unit tests (`./gradlew :app:assembleDebug :app:testDebugUnitTest`), and M1 ran it on an
Android 15 emulator (`app/e2e_log.md`). **Not tested by anyone yet:** a physical phone. The phone route below is inferred from the network config.

Needs: JDK 21, Android Studio (or the command-line SDK with platform 36), Python 3.12+, and an emulator or a phone with USB debugging.

## 1. Start the backend (dev mode)
```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
rm -f satark_dev.db && alembic upgrade head
SATARK_ENV=dev SATARK_AUTH_ENABLE_DEV_TOKEN=1 uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health        # {"status":"ok"}
```
Without Razorpay or Firebase keys the server uses local stub clients (fake order ids, no real push).

## 2. Build and install
```bash
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk       # or press Run on the `app` module in Android Studio
```
* **Emulator:** nothing else. The app defaults to `http://10.0.2.2:8000/` (the emulator's alias for your machine).
* **Physical phone:** the debug build allows plain HTTP only to `10.0.2.2` and `localhost` (`app/src/debug/res/xml/network_security_config.xml`). Connect by USB,
  run `adb reverse tcp:8000 tcp:8000`, and build with `-PsatarkBaseUrl=http://localhost:8000/`.
* **Deployed server:** `-PsatarkBaseUrl=https://<service>/` and, once M4 has them, `-PsatarkPins=sha256/...,sha256/...`.
* **Razorpay checkout:** `-PsatarkRazorpayKey=rzp_test_...` (without it the checkout path shows a clear failure).
* **Shortened 2-hour rule for a demo:** `-PsatarkLongSessionTestMin=2` (labelled test build).

## 3. Use it
Grant phone, contacts, call-log, notification and camera permissions, and the usage-access setting (Settings -> Special access). Anything denied
shows a banner and the app degrades instead of crashing. Use **Pay via Satark** with a test VPA. The UPI hand-off needs a UPI app on the device
(an emulator without one correctly shows "no UPI app"). Scam scenarios on an emulator (unknown call, sideloaded watch-listed app, long video) and
their helper commands are in `app/e2e_log.md`.

## 4. Tests
```bash
./gradlew :app:testDebugUnitTest            # JVM tests incl. M2's 36 vectors through the app pipeline
./gradlew :app:connectedDebugAndroidTest    # the 36 vectors on a connected device (uninstalls the app afterwards)
```
Without Android: `python ops/e2e/run_e2e.py` shows the real detector driving the real server.

## Limits to know
* **An emulator cannot register with a production-mode server.** Its attestation is software-only, so the server refuses it; debug builds fall back to
  `/auth/dev-token`, which exists only on a dev server. Against Render only a real phone with a hardware-backed key works, once M4's roots and the signing digest are set.
* **Push to the trusted contact is not wired into the app** (no Firebase dependency, no messaging service). The backend sends pushes; the app cannot yet receive them.
