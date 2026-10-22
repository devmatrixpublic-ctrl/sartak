# ops/: Member 4 workspace

Source of truth: the module-wise implementation plan, "Member 4: Security, CI/CD, Evaluation, Explanations".
Test status today: **161 server tests, 67 ops tests, all passing** (`cd server && pytest`; `pytest ops`).
"Built" means implemented and tested here; the right-hand column says what is still owed.

| Plan item | Where | Built | Still owed |
|---|---|---|---|
| 4.1 Auth | `server/app/auth/`, `contracts/auth.md` | challenge, 7 attestation checks, JWT, single-use refresh with reuse revocation, per-IP/device rate limits, `require_device`/`require_role`, SQL store + migration, startup validation | real Google roots in `server/certs/` (copy from Google's docs, verify fingerprints by hand); chains captured from both real phones (needs M1); run against real Postgres and Redis |
| 4.1 least-privilege DB | `ops/security/db_roles.sql`, `SATARK_MIGRATION_DATABASE_URL` | SQL written, migration-URL split tested | run the SQL on Render Postgres and switch `SATARK_DATABASE_URL` to `satark_app` |
| 4.2 CI/CD | `.github/workflows/`, `ops/ci/` | PR workflow, gated release workflow, stub rule (net additions) | nothing has run on GitHub; Kotlin detector, gitleaks, Docker and Android jobs unverified; secrets/variables to set (`ops/ci/README.md`) |
| 4.3 Evaluation | `ops/eval/` | pipeline reproduces M2's numbers exactly and applies the plan's gate; input hashes; local-hash tool | BAF/IEEE raw-file hashes (`input_hashes.json` holds nulls). The gate now PASSES on SatarkSim (recall 93.1%, false alarms 0.071%) after M2 calibrated thresholds with a margin (`detector/experiments/calibration_margin_cv.md`) |
| 4.4 Strings | `ops/strings/`, `app/src/main/res/values/strings.xml` | 18 hand-written strings, generator, validator (fails on missing/leaking/stale) | Hindi `values-hi/` (optional, plan cut item 3); LLM generation (Sarvam access unavailable, `source` recorded as hand-written) |
| 4.5 Security | `ops/security/checklist.md`, `server/tests/test_m4_security.py`, `tls_pins.py` | OWASP API checklist with every row linked to a test (a test enforces the links); found and fixed 4 real defects; `pip-audit` clean | run `tls_pins.py` on the real domain; set `SATARK_TRUSTED_PROXY_HOPS` on Render after checking the hop count |
| 4.6 Held-out runner | `ops/heldout/run_heldout.py` | guards (freeze tag, sealed hash, run-once) tested; scoring adapter tested on real SatarkSim sessions | the real run: needs the `detector-freeze` tag and the sealed file; full sealed hash into `expected_sha256.txt`; M2 to confirm how per-case user baselines are supplied |
| `contracts/pins.txt` | | generator built | needs the Render domain; deliberately not committed (an empty file silently disables pinning) |

## Defects found in other people's code while testing (all fixed on this branch, M3 please review)

* 422 responses echoed the client's input **and server file paths and source lines**.
* `amount` was unbounded; NaN reached the database as NULL and returned a 500.
* No string length limits (ids are `String(36)`, so Postgres would have returned 500s).
* `/docs`, `/redoc`, `/openapi.json` were served in production.
* M3's auth stub fabricated devices on first sight, including a "trusted contact" that never registered.

## Cross-member items

* **M3:** production boot now needs `SATARK_AUTH_ATTESTATION_ROOTS`, `SATARK_AUTH_EXPECTED_PACKAGE`, `SATARK_AUTH_EXPECTED_SIGNING_SHA256`
  (wired in `render.yaml`); until set the service refuses to start. New migration `a3c91d7e5b20` adds `refresh_tokens` and `devices.revoked`.
* **M1:** `contracts/auth.md` has the encodings. Use `/auth/dev-token` (dev only) until attestation works on a phone. `signingConfigs.release`
  must read `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD`. Request bounds are in `contracts/api.yaml`.
* **M2:** the false-alarm gate is resolved (calibration margin, see above). The held-out adapter scores each case as a brand-new user (cold-start prior, unknown age band, pooled threshold) unless you supply `--users`.
* Client IP for rate limiting: `SATARK_TRUSTED_PROXY_HOPS` (default 0 = ignore `X-Forwarded-For`, so on Render all clients share the proxy's bucket). Code and tests are in `server/app/core/clientip.py`; M4 sets the value (usually 1) after checking how many hops Render adds.

```
python ops/eval/run_eval.py          # evaluation + gate (about 80 s)
python ops/strings/validate_strings.py
python ops/heldout/run_heldout.py --check   # run every held-out guard; changes nothing
python ops/ci/check_stubs.py .       # lists stub markers (expect the 2 dev-token ones)
```
