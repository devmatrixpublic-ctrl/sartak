# Satark

Satark is an on-device scam/fraud protection system for Android. It watches
locally for signals correlated with remote-access and social-engineering
scams — unknown calls, screen-share app installs, unusual payees and
amounts, abnormally long sessions — scores them on-device with a
conformal-calibrated detector, and can hold a payment, nudge the user, or
alert a trusted contact before money moves.

This repository holds the whole system, built against the module-wise implementation plan and the shared contracts in
`contracts/`: the Android app, the on-device detector, the backend and the security/CI/evaluation tooling.

## Status

| Module | Owner | What exists | Not done yet |
| --- | --- | --- | --- |
| Android app (`app/`) | Member 1 | all 8 plan sections implemented; 36/36 vectors on an emulator; privacy check; emulator end-to-end log (`app/e2e_log.md`) | runs on **physical phones**, real Key Attestation, Firebase push, Razorpay `paid` path, signed release build |
| On-device detector (`detector/`) | Member 2 | Kotlin detector, `model.json`, schema and reason-code contracts, reports | 36/36 on physical phones, then the `detector-freeze` tag. Simulated results: recall 93.1% on validation (cross-validated about 91.8%), false alarms 0.071% (`detector/detector_report.md`) |
| **Backend (`server/`)** | **Member 3** | implemented (P0–P7) plus M4's auth; 161 tests | never deployed to Render; real Razorpay/Firebase credentials |
| Security / CI / evaluation (`ops/`, `server/app/auth/`) | Member 4 | auth, CI, evaluation gate, strings, held-out runner, security checklist | Google attestation roots, chains from real phones, certificate pins (need the deployed domain), the one held-out run |

Release is gated on purpose: it fails while any `@SatarkStub` / `# SATARK_STUB` marker remains (the dev-token stub) and while
the evaluation gate fails.

## Limitations

- **Holds cover only payments started in Satark** (scan or manual entry in the app). A payment started directly in GPay,
  PhonePe or another UPI app can only be warned about, not held.
- **UPI hand-off outcomes are app-reported, not verified.** Many UPI apps return nothing or unreliable data. Only a
  Razorpay checkout in test mode is verified, by its webhook.
- **Play Integrity is not implemented.** Android Key Attestation is used instead; it does not prove Play licensing or that
  Google Play recognises the app.
- **All detection results are on simulated data (SatarkSim).** They show the logic separates the simulated scam playbooks from
  hard negatives; they do not measure real-world accuracy. At a realistic fraud rate (about 1 in 1.47 lakh) even a 0.1%
  false-alarm rate gives a precision well under 1%.
- **Unknown-contact signals depend on permissions and phone makers.** Without them the detector falls back to amount, payee and
  install signals (see `contracts/schema.json`, `missing_signal_defaults`).
- **Phase 2, not built** (details in [`docs/ROADMAP.md`](docs/ROADMAP.md)): the DoT FRI payee rating (a PSP-only feed); embedding in a real
  PSP or bank app with a shadow-mode pilot (needs a partner); Play Integrity (Key Attestation is used instead); learning from overrides
  (the server records "Continue anyway", nothing learns from it and nothing is tuned); real-world accuracy and a live A/B test (every
  result here is on simulated data); and local differential-privacy noise and CUSUM outbreak detection on signatures.
- **Hindi warnings are machine-drafted** and need review by a native speaker (`ops/strings/PROVENANCE.md`); only the reason sentences are translated.

Backend build log, phase by phase (built as stacked branches, all merged to `main`):

| Phase | What it shipped | Verified by |
| --- | --- | --- |
| P0 | `contracts/api.yaml` (OpenAPI 3.0), FastAPI scaffold, `/health` | `openapi-spec-validator`, pytest |
| P1 | Postgres schema (7 tables) + Alembic migrations | migration applies to an empty DB, restart persistence, `webhook_events.event_id` uniqueness |
| P2 | Payment state machines (`checkout`, `upi_intent`) | every valid/invalid transition, timeout sweep to `no_result` |
| P3 | Razorpay webhook handler | HMAC verification, dedupe, out-of-order resolution by event timestamp |
| P4 | Trusted-contact alerts via FCM | stale-token path returns 2xx and is logged, never 500 |
| P5 | Signature ingest | schema rejects raw personal data, accepts real detector feature names |
| P6 | Docker image + Render blueprint | structured JSON logs with request correlation, no payload bodies logged |
| P7 | Security/contract hardening | mass-assignment guards, IDOR tests, contract-vs-implementation check |

The server suite (`cd server && pytest`, 182 tests) and the ops suite (`pytest ops`) run in CI on every pull request. The server suite is M3's original 56 plus M4's auth, security and rate-limit suites and the integration tests.

## Architecture

```
                       ┌─────────────────────┐
                       │   Android App (M1)   │
                       │  signals → events →  │
                       │  Detector.onEvent()   │
                       └──────────┬───────────┘
                                  │ Decision{level, score, reasons}
                                  ▼
                       ┌─────────────────────┐
                       │  On-device Detector  │
                       │       (M2)           │
                       └──────────┬───────────┘
                                  │ HTTP (JWT-bearer, contracts/api.yaml)
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend — server/ (M3, this repo)           │
│                                                                    │
│   /auth/*  (M4, mounted here)      /risk-check → payment created  │
│   /trusted-contact                 /payments/{id}, /result        │
│   /alert → FCM push                /webhooks/razorpay             │
│   /signature → pattern store                                      │
│                                                                    │
│   Postgres (payments, devices, trusted_links, alerts, signatures) │
│   Redis (rate-limit counters only)                                │
└─────────────────────────────────────────────────────────────────┘
                                  │
                      ┌───────────┴───────────┐
                      ▼                       ▼
                 Razorpay                  Firebase
             (test-mode checkout)         Cloud Messaging
```

**Payment state machines** (`server/app/payments/state_machine.py`):

```
checkout:    created → held
             created → allowed → paid    (only from a verified webhook)
             created → allowed → failed  (only from a verified webhook)

upi_intent:  created → held
             created → allowed → handed_off → reported_success
                                            → reported_failure
                                            → no_result (timeout)
```

`upi_intent` never reaches `paid` — the UPI app's returned result is
app-reported, not verified. Only Razorpay's webhook can move a `checkout`
payment to its terminal state.

## Repository layout

```
contracts/
  api.yaml              OpenAPI 3.0 contract — owned by M3, consumed by M1/M4
server/
  app/
    auth/                M4: Key Attestation, JWT, refresh rotation, rate limits,
                          require_device / require_role (see contracts/auth.md)
    core/                settings, error model, structured logging, strict-input schema
    db/                  SQLAlchemy models, session, Alembic env
    payments/            state machines, Razorpay order client, webhook handling,
                          timeout sweep job
    alerts/               FCM client + alert service
    signatures/           privacy-filtered signature ingest
    routers/              FastAPI route modules, one per resource
  migrations/            Alembic migrations
  tests/                 pytest suite, one file per build phase
  Dockerfile
  pyproject.toml
  certs/                 pinned Google attestation roots (not yet committed, see its README)
render.yaml              Render blueprint: web service, Postgres, Key Value (Redis)
contracts/auth.md        M4's auth contract (encodings, checks, error codes, rate limits)
ops/                     M4: eval pipeline, strings, security checklist/tools, held-out runner, CI gates (ops/README.md)
.github/workflows/       M4: ci.yml (PR checks) and release.yml (gated deploy), see ops/ci/README.md
```

## API surface

Full contract: [`contracts/api.yaml`](contracts/api.yaml). Summary:

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /health` | none | liveness check |
| `POST /auth/challenge`, `/auth/device`, `/auth/refresh` | none | **M4-owned**, mounted; Key Attestation → JWT, see `contracts/auth.md` |
| `POST /trusted-contact` | bearer | link a trusted contact's device + FCM token |
| `POST /risk-check` | bearer | evaluate a `Decision` from the on-device detector, create a payment as `held` or `allowed`; with `override` + `payment_id` ("Continue anyway") releases the caller's own detector hold (`allowed_by_user`) |
| `GET /payments/{id}` | bearer | read a payment's current state (owner-scoped) |
| `POST /payments/{id}/result` | bearer | report a UPI app's returned result (never for a `held` payment) |
| `POST /webhooks/razorpay` | HMAC-SHA256 signature | the only source of truth for `checkout` → `paid`/`failed` |
| `POST /alert` | bearer | push an alarm/long-session notification to the trusted contact (optional `payment_id` rides in the push) |
| `DELETE /device` | bearer | "Delete my data": erases the calling device's payments, alerts, trusted links, tokens and device record |
| `POST /payments/{id}/decision` | bearer | the owner's linked trusted contact approves or blocks a **held** payment (dual custody) |
| `POST /signature` | bearer | store a pattern signature (no personal data) |

Every error body is `{code, message}` — never a stack trace
(`app/core/errors.py`).

## Receiver-side mule check and dual custody (roadmap pillars 1 and 4, server side)

- **Payee fan-in.** `/risk-check` holds an otherwise-allowed payment when `SATARK_MULE_FANIN_THRESHOLD` (default 3) *other*
  devices paid the same hashed payee within `SATARK_MULE_FANIN_WINDOW_MINUTES` (default 60). `0` turns it off. It only ever
  escalates ALLOW to HOLD; the response carries `hold_reason` (`detector` or `payee_fan_in`). Exact counts over `payments`,
  no sketch needed at this scale.
- **Trusted-contact approve/block.** A held payment moves to `approved` or `blocked` only through
  `POST /payments/{id}/decision` from a device the owner linked. Approve on `upi_intent` starts the hand-off; on `checkout`
  the owner's app then fetches the order (`POST /risk-check` with `override`), because the amount is not stored. The owner, a stranger and an unknown id all get the same 404.
- **App side:** built (`ContactDecisionScreen`, the hold screen waits for the answer); unit-tested, not yet run on two phones.
- **By design:** an unanswered hold stays held (no auto-release after a timeout); payments store an `amount_band`, not the rupee amount.
- **Not built:** the detector, sensor, Hawkes/GBDT, adaptive-conformal and federated-update roadmap pillars (they would change the frozen model and its 36 vectors).

## Local development

Requires Python ≥ 3.11.

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# apply migrations (defaults to a local sqlite file; see Configuration)
alembic upgrade head

# run the API
uvicorn app.main:app --reload

# run the test suite
pytest
```

`GET http://localhost:8000/health` should return `{"status": "ok"}`.

## Configuration

All settings are environment variables prefixed `SATARK_` (see
`app/core/settings.py`). None have real-looking defaults — every default is
either obviously local-only (`sqlite:///./satark_dev.db`) or empty, so a
misconfigured deploy fails closed rather than silently using a fake secret.

| Variable | Required in production | Notes |
| --- | --- | --- |
| `SATARK_ENV` | yes | `production` enables the background timeout sweeper |
| `SATARK_DATABASE_URL` | yes | Postgres connection string |
| `SATARK_REDIS_URL` | yes | rate-limit counters only — never payment/session state |
| `SATARK_JWT_SECRET` | yes | signs device JWTs; ≥ 32 bytes and not the dev default, else the server refuses to boot outside dev |
| `SATARK_AUTH_ATTESTATION_ROOTS` | yes | PEM bundle of pinned Google roots (`server/certs/`); server refuses to boot without it outside dev |
| `SATARK_AUTH_EXPECTED_PACKAGE` / `_SIGNING_SHA256` | yes | identity of the release app, checked on every attestation |
| `SATARK_MIGRATION_DATABASE_URL` | optional | owner connection used only by `alembic upgrade head`, so `SATARK_DATABASE_URL` can be the DML-only role in `ops/security/db_roles.sql` |
| `SATARK_TRUSTED_PROXY_HOPS` | optional | proxies that append to `X-Forwarded-For` (default 0 = ignore the header; usually 1 on Render once checked) |
| `SATARK_MAX_BODY_BYTES`, `SATARK_WEBHOOK_MAX_BODY_BYTES` | optional | request-body caps (defaults 64 KB and 256 KB) |
| `SATARK_RAZORPAY_KEY_ID` / `_KEY_SECRET` | yes | without these, `/risk-check` falls back to a local stub order id — fine for dev, **not safe for production** |
| `SATARK_RAZORPAY_WEBHOOK_SECRET` | yes | without this, `/webhooks/razorpay` rejects every request with `webhook_not_configured` (fails closed) |
| `SATARK_FIREBASE_CREDENTIALS_JSON` | yes | without this, `/alert` uses a local stub FCM client — no real push is sent |

## Deployment

```bash
render.yaml   # web service (Docker) + managed Postgres + Key Value (Redis)
server/Dockerfile
```

The Dockerfile runs `alembic upgrade head` before starting `uvicorn`, so a
deploy always migrates first. `HEALTHCHECK` hits `GET /health`.

**Render free-tier limitations** (documented here per the plan's own
requirement, not hidden in a footnote):

- The web service sleeps after ~15 minutes idle; the first request after
  sleep can take up to a minute. Client-side retry/timeout handling and the
  offline queue (Member 1's scope) must cover this.
- The periodic in-process timeout sweeper (`app/payments/jobs.py`) does not
  run while the service is asleep. `GET /payments/{id}` re-evaluates the
  timeout on read (`sweep_if_stale`), so state is still correct once the
  service wakes.
- Free Postgres has a time-limited free period, and free Key Value (Redis)
  is not durable. Export the database before any live demo.

## Security notes

- **Mass assignment**: every request body model inherits from
  `StrictInput` (`extra="forbid"`) — an unexpected field is a 422, not a
  silent no-op.
- **IDOR**: `GET /payments/{id}` and `POST /payments/{id}/result` are
  owner-scoped; a payment that exists but belongs to another device returns
  404, not 403, so existence isn't leaked.
- **Webhook signatures**: verified with `hmac.compare_digest` over the raw
  request body before any JSON parsing; a missing webhook secret fails
  closed (400), never silently accepts unsigned requests.
- **Privacy-by-schema**: `signatures` rows have no `device_id` column at
  all (not just a nullable one) — personal-data linkage is impossible by
  construction, not convention. Feature keys are validated against a
  denylist of raw-PII-shaped substrings (`phone`, `vpa`, `email`, …),
  deliberately narrower than the detector's own vocabulary so legitimate
  feature names like `unk_contact_recent` or `new_payee` aren't
  false-positive-rejected.
- **Logging**: structured JSON with a request-correlation ID; request/response
  bodies are never logged, so payment amounts and payee hashes cannot leak
  into the log stream by construction.

## Known limitations

- **Release is gated and currently blocked, on purpose.** `release.yml` refuses to deploy while a stub marker remains (the dev-token
  stub) or while the evaluation gate fails. The gate passes today on simulated data (recall 93.1%, false alarms 0.071%); the stub is
  what blocks. See `ops/ci/README.md`.
- Request bodies are capped at 64 KB (256 KB for `/webhooks/`) before parsing or authentication (`server/app/core/limits.py`).
- `/docs`, `/redoc` and `/openapi.json` are served only when `SATARK_ENV=dev`.
- Request amounts must be positive, finite and at most 10,000,000; string fields have length limits (see `contracts/api.yaml`).
- Not yet verified on real infrastructure: Postgres (tests use SQLite), Redis (the limiter is tested against a fake), the Docker
  image, the GitHub workflows, and attestation chains from real phones.

- Holds cover only payments started through this API (`/risk-check`); a
  payment started directly in another UPI app can't be intercepted here —
  that's an app-side (Member 1) concern.
- `upi_intent` outcomes are app-reported, not verified — see the state
  machine section above.
- Device auth is implemented and tested against **synthetic** attestation
  chains only. It has not yet been run against chains from the two physical
  phones, and the real Google roots are not committed, so production boot
  is blocked until they are (fail closed, by design).
- A `/auth/dev-token` stub (tagged `# SATARK_STUB`) exists for dev only; it
  404s unless `SATARK_ENV=dev` and the flag is set, and boot refuses the flag
  elsewhere. `ops/ci/check_stubs.py` fails the release build while the tag
  remains.
- The per-device/IP rate limiter uses Redis in production and fails open if
  Redis is down (rate limiting is abuse control, not authentication).
- Razorpay/Firebase/Render integrations fall back to local stubs without
  real credentials; they have not been exercised against the live services
  in this environment.
- Results reported in the module plan's evaluation pipeline (recall,
  false-alarm rate) belong to the detector module (M2) and are not part of
  this backend.

## Contributing / interfaces

`contracts/api.yaml` is owned by this module (M3); any change needs
approval from the Android app (M1) and security/CI (M4) as consumers, per
the shared-interfaces rules in the module-wise implementation plan.
