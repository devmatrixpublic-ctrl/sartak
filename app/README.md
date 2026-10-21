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
- Raw reason codes on screen until M4's `strings.xml` (`ui/alerts/AlertController.kt`).

## Tests
`app/src/test` holds JVM tests (parser, mapper, dedup, sequencer, contract checks). Instrumented tests, the build of the Android module and the on-phone runs are still to do.

```bash
gradle wrapper && ./gradlew :app:testDebugUnitTest -PsatarkBaseUrl=https://<server>/ -PsatarkPins=sha256/...,sha256/...
```
