# app (M1): Android application

Kotlin + Compose. Consumes `detector` (M2) through an included build and talks to `server` (M3) per `contracts/api.yaml`.

| Package | Plan item |
|---|---|
| `signals/` | 1.1 Call, Usage, Install, Watchlist sources + `SignalStatus`; `SignalService` keeps them alive |
| `events/` | 1.2 `EventMapper`, `Deduplicator`, `EventSequencer`, Room storage, `EventDispatcher` |
| `ui/onboarding/` | 1.3 permission steps, degraded-mode banners, trusted-contact link |
| `ui/alerts/` | 1.4 Nudge / Hard / Trusted-contact / Long-session screens, `AlertController` |
| `payments/`, `ui/pay/` | 1.5 QR scan, `UpiUriParser`, hand-off, checkout, result reporting |
| `net/` | 1.6 Retrofit client, retry/backoff, token refresh, offline queue |
| `security/` | 1.7 Key Attestation, encrypted token store, certificate pins |

Contracts owned here: `contracts/watchlist.json`, `contracts/upi.md`.

## Stubs (`@SatarkStub`, release build must fail while any remain)
- Dev token when `/auth/*` answers 404 (`net/Network.kt`).
- (removed) Raw reason codes: M4's `strings.xml` is merged and validated for all 18 codes.

## Tests
`app/src/test` holds the JVM tests (UPI parser, event mapper, dedup, sequencer, session policy, M2's 36 vectors through the app pipeline, privacy and API contract checks). The instrumented 36-vector test has run on an emulator (see `e2e_log.md`); runs on physical phones are still to do.

```bash
gradle wrapper && ./gradlew :app:testDebugUnitTest -PsatarkBaseUrl=https://<server>/ -PsatarkPins=sha256/...,sha256/...
```
