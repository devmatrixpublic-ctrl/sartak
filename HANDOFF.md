# Context handoff — Satark backend (Member 3)

Written 2026-10-21, end of the session that built this. Read this first if
you're picking up this repo cold (new session, new agent, or a teammate).

## What was asked

Two uploaded plan docs drove this work:

1. **`Satark: Module-wise Implementation Plan`** — the whole-system spec:
   4 members (Android app, on-device detector, backend, security/CI),
   their modules, interfaces, and an integration checklist.
2. **`Satark: Member 3 Backend Build Plan`** — the one actually executed.
   8 phases, P0–P7, each with a branch, a "done when" bar, and a verify
   step. This is the plan whose checklist this handoff maps to.

The instruction was to build the backend per that phase plan, pushing each
phase to its own branch as specified, then (in a later turn) add a
production README and this handoff doc.

## What exists right now

Repo: `devmatrixpublic-ctrl/sartak` on GitHub. `main` still only has the
original placeholder `README.md` commit (`340177a`) — **nothing has been
merged to `main`**. All work lives on stacked feature branches, each
building on the previous:

```
main (340177a, placeholder only)
  └─ feat/m3-p0-contract   (bb7950d)  contracts/api.yaml + FastAPI scaffold + /health
       └─ feat/m3-p1-db         (86ee8fb)  Postgres models + Alembic
            └─ feat/m3-p2-payments  (e057f1f)  payment state machines
                 └─ feat/m3-p3-webhook  (8c479c5)  Razorpay webhook
                      └─ feat/m3-p4-alerts   (94faf01)  FCM alerts
                           └─ feat/m3-p5-signatures (586378f)  signature ingest
                                └─ feat/m3-p6-deploy   (9d5c380)  Docker + render.yaml
                                     └─ feat/m3-p7-hardening (9832147)  security/contract hardening
                                          └─ docs/m3-readme     (590b4a1)  production README
                                               └─ docs/context-handoff (this branch)  this file
```

Every branch is pushed to `origin`. **No PRs have been opened** — the user
hadn't asked for that yet as of this doc.

56 tests pass at the tip (`cd server && pytest`, run from a fresh venv —
see Quickstart below).

## What's actually implemented (`server/`)

FastAPI backend, Python ≥3.11, SQLAlchemy + Alembic, Postgres (SQLite for
local dev/tests). Full detail is in `README.md` at repo root — read that
for architecture, API surface, config, and security notes. The short
version of what each phase added:

- **P0**: `contracts/api.yaml` (the full OpenAPI contract for all 9
  endpoints), app skeleton, `{code,message}` error model.
- **P1**: 7 tables (`devices`, `auth_challenges`, `trusted_links`,
  `payments`, `webhook_events`, `alerts`, `signatures`), Alembic migrations.
- **P2**: the two payment state machines — this is the module's core.
  `checkout` can reach `paid`/`failed` only via a verified webhook;
  `upi_intent` never reaches `paid` (app-reported, not verified) and times
  out `handed_off` → `no_result`.
- **P3**: Razorpay webhook — HMAC-SHA256 over the raw body, dedupe on
  `X-Razorpay-Event-Id`, out-of-order events resolved by the event's own
  `created_at` rather than arrival order (added a `last_webhook_event_at`
  column for this — see migration `ef04b65f1726`).
- **P4**: `/trusted-contact` + `/alert` with FCM. Stale/invalid token is a
  routine logged outcome (2xx), never a 500.
- **P5**: `/signature`. Deliberately caught a real bug here: an early
  denylist for "no personal data in feature keys" blocked legitimate
  detector feature names (`unk_contact_recent`, `new_payee`, etc. from the
  module plan's own 16-feature list) because it matched topical substrings
  like "payee"/"contact" too broadly. Narrowed the denylist to raw-PII
  shapes only (phone, vpa, email, address, account, device_id, imei,
  amount, number, name). See `app/signatures/schemas.py`.
- **P6**: `server/Dockerfile`, `render.yaml`. Structured JSON logging with
  request-correlation IDs; request/response bodies are never logged by
  construction (not scrubbed after the fact).
- **P7**: self-audit pass — fixed a dead import, added `extra="forbid"`
  (`StrictInput` base, `app/core/schemas.py`) to every request body as a
  mass-assignment guard, confirmed no stale `# SATARK_STUB` markers except
  the intentional auth stub, added IDOR tests and a contract-vs-live-schema
  check against `api.yaml`.

## Deliberately out of scope here

- **`/auth/*`** (Key Attestation → JWT) is Member 4's module. Every
  protected route uses a dev-token stub (`app/auth/dependencies.py`,
  tagged `# SATARK_STUB`) where the bearer token value *is* trusted as the
  device id. This is correct per the plan's own stub table but **must not
  reach production** — the module plan's CI gate (owned by M4) is supposed
  to fail the release build while any `# SATARK_STUB` tag remains.
- **Android app (`app/`)** and **on-device detector (`detector/`)** —
  Members 1 and 2's scope, not started in this repo.
- **`ops/`** (CI pipeline, evaluation harness, security checklist,
  explanation-string generation) — Member 4's scope, not started.
- **Rate limiting** — Redis is provisioned (`render.yaml`, `SATARK_REDIS_URL`)
  but the actual rate-limit logic is M4's (`4.1 Authentication & access`).

## What was never verified (be honest about this with whoever reads it)

- **Docker build**: no Docker daemon was available in the sandbox this was
  built in (`docker version` connects to the client but not a daemon). The
  Dockerfile was reviewed for correctness (paths match `dockerContext`,
  install path mirrors the proven local venv install) but **never actually
  built or run as a container**.
- **Real Razorpay / Firebase / Render**: no credentials were available.
  `order_client.py` and `fcm_client.py` both fall back to local stub
  clients when keys aren't configured — those stub paths are what's
  tested, not the real HTTP calls to Razorpay/Firebase.
- **Actual Render deploy**: never performed. `render.yaml` is a blueprint,
  not a deployed service.
- **CI pipeline**: doesn't exist yet (M4's `.github/workflows/`), so
  nothing has run these tests except local `pytest` in this session.

## Decisions made that weren't fully spelled out in the plan

A few implementation choices filled gaps the plan left open — worth
knowing if you're reviewing or extending this:

1. **`upi_intent` + `ALLOW` → `handed_off` immediately.** The plan has no
   separate "I launched the intent" callback endpoint, and says "On HOLD:
   no order and no hand-off" (implying ALLOW *does* hand off). So
   `create_payment` transitions `created → allowed → handed_off` in one
   step for `upi_intent`, starting the timeout clock right there. See
   `app/payments/service.py::create_payment`.
2. **Webhook out-of-order resolution uses the event's own timestamp**, not
   arrival order — added `payments.last_webhook_event_at` for this. A
   stale replay (older event, arrives late) is a no-op; a genuinely later
   terminal-state attempt after the payment is already terminal is also a
   no-op (terminal states don't un-terminal). This seemed like the only
   way to satisfy "out-of-order events reach the correct final state"
   without just trusting delivery order.
3. **`/alert` always returns 2xx**, even with zero trusted contacts linked
   (not just for a stale token) — the alert row is still stored with a
   `failure_reason`. This generalizes the plan's explicit stale-token
   requirement to the whole "never fail loudly on a notification path"
   principle.
4. **IDOR returns 404, not 403**, for a payment owned by another device —
   doesn't leak whether the payment id exists.

## How to resume

```bash
cd /home/user/sartak
git checkout feat/m3-p7-hardening   # or whichever branch you're extending

cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
rm -f satark_dev.db && alembic upgrade head
pytest -q   # should show 56 passed (49 on p6, fewer on earlier branches)
```

To continue the stack (e.g. add a new phase), branch off the tip:
`git checkout -b feat/m3-pX-whatever feat/m3-p7-hardening`.

Known immediate next steps, roughly in likely order of value:
1. Open PRs for the 9 branches (not done — wasn't asked for yet).
2. Decide whether to merge the stack into `main`.
3. Get real Razorpay/Firebase/Render credentials and actually exercise
   those integration paths, or at least a Docker build.
4. Start Member 4's scope (`/auth/*`, CI, the stub-marker release gate) —
   this backend's biggest structural gap is that it currently trusts any
   bearer token as a device identity.
5. Only after that: Members 1 and 2 (`app/`, `detector/`), which this
   backend's contract (`contracts/api.yaml`) was written to serve.
