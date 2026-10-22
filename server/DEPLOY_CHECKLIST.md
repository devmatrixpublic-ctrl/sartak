# Deploying the backend to Render (M3, with M4 and M1)

Nothing here has been run: the service has never been deployed. This checklist is derived from `render.yaml`, `server/Dockerfile`
and `server/app/core/settings.py`, in the order things depend on each other.

## 0. What must exist before the first deploy can succeed

| Needed | Who | Why it blocks |
|---|---|---|
| `server/certs/google_attestation_roots.pem` committed | **M4** (verify the fingerprints first, see `server/certs/CANDIDATE_ROOTS.md`) | In production the server **refuses to boot** without it, so `/health` never goes green. |
| Release signing certificate SHA-256 | **M4** creates the release keystore (`ops/release/README.md`); **M1**'s debug export prints a build's digest | `SATARK_AUTH_EXPECTED_SIGNING_SHA256` is required at boot. While testing with debug builds, list the debug digest too (comma-separated) and **remove it before real use**. |
| Razorpay **test-mode** key id, key secret, webhook secret | **M3** (Razorpay dashboard) | Without them the server uses a local stub order client: fine to boot, but not a real checkout. |
| Firebase service-account JSON | **M3** (Firebase project) | Without it alerts use a stub client: the push never reaches a phone. |

## 1. Environment (`render.yaml` is the source; this is what each value is)

| Variable | Set by | Notes |
|---|---|---|
| `SATARK_ENV=production` | blueprint | |
| `SATARK_DATABASE_URL`, `SATARK_MIGRATION_DATABASE_URL` | blueprint (from the database) | Later point the first at the `satark_app` role (step 5). |
| `SATARK_REDIS_URL` | blueprint (from the key-value service) | The limiter fails open if Redis is down, by design. |
| `SATARK_JWT_SECRET` | blueprint (`generateValue`) | At least 32 bytes; boot refuses a weak or default value. |
| `SATARK_AUTH_ATTESTATION_ROOTS=/srv/certs/google_attestation_roots.pem` | blueprint | The file must be in the image (step 0). |
| `SATARK_AUTH_EXPECTED_PACKAGE=com.satark.app` | blueprint | Fixed by the app's `applicationId`. |
| `SATARK_AUTH_EXPECTED_SIGNING_SHA256` | **you, in the dashboard** | See step 0. |
| `SATARK_TRUSTED_PROXY_HOPS` | **you, after checking** | Blueprint value 0 = ignore `X-Forwarded-For`. See step 4. |
| `SATARK_RAZORPAY_KEY_ID`, `_KEY_SECRET`, `_WEBHOOK_SECRET` | **you, in the dashboard** | Secrets; never commit. |
| `SATARK_FIREBASE_CREDENTIALS_JSON` | **you, in the dashboard** | The whole service-account JSON as the value. |
| `SATARK_AUTH_ENABLE_DEV_TOKEN` | never set | Boot refuses it outside dev. |

## 2. First deploy

1. Create the blueprint from the repo (`render.yaml`). Confirm the web service plan is not the sleeping free tier if the demo needs it awake.
2. The image runs `alembic upgrade head` before starting `uvicorn` (see `server/Dockerfile`). Check the deploy log shows the migrations applied.
3. `curl https://<service>/health` must return `{"status":"ok"}`.

## 3. Verify it is locked down (one command)

```bash
python ops/e2e/smoke_deployed.py https://<service>.onrender.com
```

All checks must pass: HTTPS, health, docs hidden, dev-token off, 401 without a token, bogus attestation rejected, forged webhook
refused, oversize body refused. (The script itself is proven against a production-configured local server in `ops/e2e/test_smoke.py`.)
It does not test real attestation, payments, push, pinning, the database role or the Redis limit.

## 4. Rate limits behind Render's proxy
With `SATARK_TRUSTED_PROXY_HOPS=0` every client shares one rate-limit bucket (the load balancer's address). Find how many hops Render
adds for this service, set the variable (usually 1), then confirm from **two different networks** that each gets its own bucket on
`/auth/challenge` (10 requests per minute each) and that adding a fake left-hand `X-Forwarded-For` entry does not change the bucket.
Too high a value lets callers pick their own bucket.

## 5. Database role (M4's SQL)
Run `ops/security/db_roles.sql` with the owner connection, then set `SATARK_DATABASE_URL` to the `satark_app` role. Keep
`SATARK_MIGRATION_DATABASE_URL` on the owner so migrations still work. Redeploy and re-run step 3.

## 6. Razorpay and Firebase
* Razorpay dashboard (test mode): webhook URL `https://<service>/webhooks/razorpay`, events `payment.captured`, `order.paid`,
  `payment.failed`, secret = `SATARK_RAZORPAY_WEBHOOK_SECRET`. Then a ₹1 test checkout from the app should reach `paid` only via the webhook.
* Firebase: with the credentials set, link a trusted contact from the app and confirm the push reaches the second phone.

## 7. Hand-offs after it is up
* Tell **M4** the domain: they generate `contracts/pins.txt` and run `ops/security/tls_pins.py`.
* Tell **M1** the base URL (`-PsatarkBaseUrl=https://<service>/`) and, once it exists, the pins (`-PsatarkPins=...`).
* Free tier: the service sleeps after ~15 minutes idle (first request can take a minute), the free database is time-limited and the
  free key-value store is not durable. Export the database before any live demo.
