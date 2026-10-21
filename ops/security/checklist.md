# Security checklist (plan 4.5)

Every line names the test or evidence that backs it. **Done** means the linked test exists and passes today;
**Partial** and **Open** say exactly what is missing. Re-run: `cd server && pytest` and `pytest ops`.
Tests in `server/tests/test_m4_security.py` run against the real app with real authentication.

Last full run: 153 server tests + 46 ops tests passing (plus 1 slow opt-in test); `pip-audit` clean (no known vulnerabilities); a pattern scan of the
tree for private keys / cloud, Razorpay, Google, GitHub and Slack tokens found nothing. gitleaks over full history runs in CI (4.2).

## OWASP API Security Top 10 (2023)

| # | Risk | Status | Evidence |
|---|---|---|---|
| API1 | Broken object-level authorization (IDOR) | **Done** | `test_m4_auth.py::test_idor_other_device_cannot_read_my_payment_on_real_routes`; M3 `test_p7_contract_and_hardening.py::test_device_a_cannot_read_device_b_payment`; `ensure_owner` unit test. Another device's object answers 404, identical to a missing one. |
| API2 | Broken authentication | **Done** (synthetic chains) | 31 attestation checks (`test_m4_attestation.py`), token/refresh/expiry/forgery tests (`test_m4_auth.py`), every non-public route 401s without a token (`test_every_non_public_route_rejects_a_request_with_no_token`). **Open:** chains captured from the two real phones (needs M1). |
| API3 | Broken object-property-level authorization | **Done** | Every request body forbids unknown fields (`test_every_request_body_model_forbids_unknown_fields`, reads the OpenAPI schema so a new endpoint is covered automatically); `/auth/device` cannot be asked for `role: admin` (`test_role_field_may_only_be_device_and_extras_are_rejected`). Responses use explicit output models. |
| API4 | Unrestricted resource consumption | **Partial** | Rate limits: per IP on `/auth/*`, per device elsewhere (`test_burst_gets_429_with_retry_after_then_recovers`, `test_challenge_endpoint_is_rate_limited`). Field sizes and amount bounds enforced (`test_oversized_strings_are_rejected`, `test_payment_amount_must_be_positive_and_finite`, `test_reasons_list_is_capped_at_three`). **Open:** no overall request-body size cap at the server or proxy; the limiter fails open if Redis is down (deliberate, see `ratelimit.py`) so abuse protection degrades while it is down. |
| API5 | Broken function-level authorization | **Done** | Role checks exact, 403 on mismatch (`test_wrong_role_is_403`, `test_admin_device_cannot_use_device_routes_and_vice_versa`). Admin is never self-assignable. |
| API6 | Unrestricted access to sensitive business flows | **Partial** | A held payment cannot have a result reported (M3 `test_p2_payments.py`); webhook is the only path to `paid`. **Open:** no per-device cap on `/risk-check` volume beyond the general limit. |
| API7 | Server-side request forgery | **Done** (by construction) | The server's only outbound calls go to fixed hosts: Google's attestation status URL (`revocation.py: STATUS_URL`), Razorpay, FCM. No client-supplied URL is ever fetched. |
| API8 | Security misconfiguration | **Done** | Unsafe auth config refuses to boot (`test_m4_settings.py`, 15 tests incl. the documented env-var names); `/docs`, `/redoc`, `/openapi.json` are off outside dev (`test_docs_and_schema_are_not_served_outside_dev`); no CORS headers (`test_no_cors_headers_are_emitted`); dev-token stub is dev-only and refused at boot elsewhere. **Open:** no security response headers (`X-Content-Type-Options`, HSTS from the app); Render terminates TLS and HSTS is checked by `tls_pins.py` instead. |
| API9 | Improper inventory management | **Done** | M3 contract test asserts every path in `contracts/api.yaml` is mounted and implemented (now including `/auth/*`); `test_every_non_public_route...` enumerates the live schema, so an undocumented route would have to be added to a public allow-list on purpose. |
| API10 | Unsafe consumption of APIs | **Done** | Razorpay webhook: HMAC over the raw body, dedupe, forged -> 400 (M3 `test_p3_webhook.py`); Google revocation list fails closed when never fetched (`test_revocation_list_fails_closed_when_never_fetched`). |

## Input validation and error handling

| Item | Status | Evidence |
|---|---|---|
| Validation errors never echo client input or server paths | **Done** (was broken, fixed in this change) | `test_validation_errors_do_not_echo_what_the_client_sent`. Before the fix the 422 body contained the submitted values **and server file paths and source lines**. |
| Unhandled exceptions return a generic 500 | **Done** | `test_unhandled_exception_returns_a_generic_500_with_no_stack_trace` |
| Amount positive, finite, <= 10,000,000 | **Done** (was broken, fixed) | `test_payment_amount_must_be_positive_and_finite` (6 cases). Before the fix NaN was stored as NULL and crashed with a 500; negatives and 1e300 were accepted. The bound is a sanity limit, not a product limit. |
| String lengths bounded (ids <= 36 to match the columns) | **Done** (fixed) | `test_oversized_strings_are_rejected` |
| SQL metacharacters in path ids | **Done** | `test_path_ids_with_sql_metacharacters_are_just_not_found` (parameterised queries throughout) |

## Transport

| Item | Status | Evidence |
|---|---|---|
| TLS version, chain, hostname, expiry, HSTS check | **Tool done, real domain not checked** | `ops/security/tls_pins.py`, 7 tests against a real local TLS server (untrusted chain, wrong hostname, near-expiry, missing HSTS). **Open:** run it against the Render domain once it exists: `python ops/security/tls_pins.py --host <domain>`. |
| Certificate pin set for M1 | **Open** | `contracts/pins.txt` is deliberately not committed: it needs the real domain, and an empty file would silently disable pinning in the app. Generate with `--write contracts/pins.txt` (refuses unless there is a primary and a backup pin). |

## Privacy data-flow

| Item | Status | Evidence |
|---|---|---|
| No raw personal-data column anywhere in the schema | **Done** | `test_no_table_has_a_raw_personal_data_column` |
| Signatures cannot be linked to a device | **Done** | `test_signatures_cannot_be_linked_to_a_device`; M3 `test_p5_signatures.py` (denylist of PII-shaped feature keys) |
| Logs carry no bodies, amounts, payee hashes or tokens | **Done** | `test_request_logs_contain_no_bodies_amounts_or_payee_hashes` |
| Refresh tokens stored hashed | **Done** | `test_refresh_tokens_are_stored_hashed` |
| No call audio/content, raw numbers or screen content leave the phone | **Open (needs M1)** | This is a property of the app. Server side, the API has no field that could carry them; the phone-side check (inspect traffic from both devices) cannot be done here. |
| Local differential-privacy noise on signature uploads | **Not done** | Optional; first in the plan's cut order. |

## Secrets and dependencies

| Item | Status | Evidence |
|---|---|---|
| No secrets in the tree | **Done** (tree), **CI for history** | pattern scan clean; `gitleaks` job in 4.2 covers history. |
| JWT secret fails closed | **Done** | `test_unsafe_production_settings_refuse_to_boot`; default dev secret refused outside dev. |
| Dependency vulnerabilities | **Done** | `pip-audit`: no known vulnerabilities (re-run in CI, 4.2). |
| Least-privilege database user (no DDL at runtime) | **Written, not executed** | `ops/security/db_roles.sql` + `SATARK_MIGRATION_DATABASE_URL` (tested: `test_alembic_env_reads_the_migration_url`). **Open:** run the SQL on the Render Postgres and switch `SATARK_DATABASE_URL` to the `satark_app` role; verify the four statements at the bottom of the SQL fail. |
| Production boot needs the pinned Google roots | **Blocking, by design** | `server/certs/README.md`. |
