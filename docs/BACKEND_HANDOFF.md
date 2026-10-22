# Backend handoff (Member 3's scope), corrected after integration

Updated 2026-10-22. Replaces `HANDOFF.md` on the `docs/context-handoff` branch, which was written before anything was merged and
says "nothing has been merged to `main`", "no PRs", "56 tests" and "auth, CI, app and detector not started". All of that is out of date.
The design decisions and the list of what was never verified are kept below because they are still true.

## Where things are now

Everything is on `main`. The backend was built in stacked branches (since deleted) and merged
(PRs 1 to 6), then the app (M1), detector (M2) and ops/auth (M4) were integrated in PR #10 with cross-member fixes.

| Area | Where | Owner | State |
|---|---|---|---|
| REST API and contract | `contracts/api.yaml`, `server/app/routers/` | M3 | done; every endpoint covered by contract tests |
| Persistence | `server/app/db/`, `server/migrations/` | M3 (+ M4's `refresh_tokens`, `devices.revoked`) | applies from an empty database (checked on SQLite) |
| Payment state machines, Razorpay webhook | `server/app/payments/` | M3 | done; tested with fixtures and a local stub order client |
| Alerts (FCM) | `server/app/alerts/` | M3 | done; tested with a stub client |
| Signature ingest | `server/app/signatures/` | M3 | done; accepts the detector's own 16 feature names |
| Auth: challenge, 7 attestation checks, JWT, refresh, roles, rate limits | `server/app/auth/` | **M4** (replaced M3's stub) | done; a dev-token stub remains until real attestation works |
| Body-size cap, client-IP handling | `server/app/core/limits.py`, `clientip.py` | M4 item, built in integration | done; `SATARK_TRUSTED_PROXY_HOPS` is set to 0 until checked on Render |
| CI, evaluation, strings, held-out runner | `.github/workflows/`, `ops/` | M4 | running on GitHub; see `ops/README.md` |
| Android app, detector | `app/`, `detector/` | M1, M2 | on `main`; see their READMEs |

Server tests: 182 at the time of writing (`cd server && pytest`). A cross-module run drives the real server with the real
detector's decisions (`python ops/e2e/run_e2e.py`, 57 checks).

## What is verified, and what is still not

Verified on GitHub CI: the server image builds, server and ops tests pass, contract tests pass, dependency scan and secrets scan
are clean, the Android debug build and unit tests pass.

**Still never verified** (needs accounts, hardware or a deployed domain):
* **Render deployment.** Never deployed. `render.yaml` is a blueprint. See `server/DEPLOY_CHECKLIST.md`.
* **Real Razorpay and Firebase.** `order_client.py` and `fcm_client.py` fall back to local stubs without keys; those stub paths are what is tested, not the real HTTP calls.
* **Real Postgres and Redis.** Tests and the end-to-end run use SQLite and an in-memory limiter; the Redis limiter is tested against a fake. The first deploy is the first real run of both.
* **Key Attestation with a real phone.** Fixtures are synthetic; real chains from both phones are still needed (M1 exports, M4 tests).
* **Certificate pins**, which need the deployed domain.

**Deployment dependency that was not written down before:** in production the server refuses to boot without
`server/certs/google_attestation_roots.pem`, so the deploy waits for M4's roots decision (`server/certs/CANDIDATE_ROOTS.md`).

## Decisions made that the plan left open (unchanged, still in force)

1. **`upi_intent` + `ALLOW` goes to `handed_off` immediately.** The plan has no separate "I launched the intent" call and says HOLD means no hand-off, so ALLOW hands off; this starts the timeout clock (`app/payments/service.py::create_payment`).
2. **Webhook out-of-order resolution uses the event's own timestamp**, not arrival order (`payments.last_webhook_event_at`, migration `ef04b65f1726`). A stale replay is a no-op; terminal states do not un-terminal.
3. **`/alert` always returns 2xx**, even with no trusted contact linked or a stale token; the alert row is stored with a `failure_reason`.
4. **IDOR returns 404, not 403**, for another device's payment, so it does not reveal whether an id exists.

Added during integration:
5. **Optional response fields are omitted when unset**, not returned as `null` (`order_id`, `razorpay_order_id`, `reported_*`), as `api.yaml` describes.
6. **Validation errors are 422** on every endpoint (the app-wide handler); `api.yaml` now says so for `/signature`.
7. **The client cannot self-report ALLOW.** The server holds on `HARD` or `TRUSTED_CONTACT` decisions; the app reports the detector's decision and the server decides.

## How to run it locally

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
rm -f satark_dev.db && alembic upgrade head
pytest -q
uvicorn app.main:app --reload        # dev mode: docs at /docs, dev-token enabled only with SATARK_AUTH_ENABLE_DEV_TOKEN=1
```

## Next steps for the backend, in order

1. Wait for (or help with) M4's pinned roots file, then follow `server/DEPLOY_CHECKLIST.md` to deploy.
2. Run `python ops/e2e/smoke_deployed.py https://<service>` against the live URL.
3. Add real Razorpay test keys and Firebase credentials; exercise a real checkout and a real push on the second phone.
4. Set `SATARK_TRUSTED_PROXY_HOPS` after checking Render's hop count; run `ops/security/db_roles.sql` and switch to the `satark_app` role.
5. Remove the dev-token stub with M4 once real attestation works. Optional: signature trend detection (CUSUM), not built.
