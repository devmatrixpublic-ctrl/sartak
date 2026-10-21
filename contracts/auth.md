# Auth contract (owner: M4; consumers: M1 app, M3 server)

Only M4 edits this file. A change here ships together with the matching pytest in
`server/tests/test_m4_*.py` and the consumers' approval. Wire shapes follow `contracts/api.yaml`
(M3-owned); where this document adds detail (error codes, encodings) the api.yaml schema is unchanged.

## Flow

```
App (M1)                                   Server (M4 logic, mounted in server/app/main.py)
 |-- POST /auth/challenge ------------------->  random 32 bytes, one-time, 120 s expiry
 |<-- {challenge, expires_at} -----------------
 | generate Keystore EC key with setAttestationChallenge(decode(challenge))
 |-- POST /auth/device {challenge, public_key, attestation_chain} -->
 |        attestation checks (below) -> devices row -> JWT + refresh token
 |<-- {access_token, refresh_token, token_type:"bearer", expires_in, device_id} --
 |-- any route with  Authorization: Bearer <access_token>  --> require_device
 |-- POST /auth/refresh {refresh_token} --------> rotated pair (the old refresh token is now dead)
```

## Encodings (M1 must match exactly)

| Field | Encoding |
|---|---|
| `challenge` | base64url, no padding, 32 random bytes. The app base64url-decodes it and passes the raw bytes to `setAttestationChallenge`. |
| `expires_at` | RFC 3339 date-time (UTC). |
| `public_key` | standard base64 of the X.509 `SubjectPublicKeyInfo` DER (`keyPair.public.encoded`). |
| `attestation_chain` | JSON array of standard-base64 DER certificates, **leaf first** (the order `KeyStore.getCertificateChain` returns). 2 to 6 certs. |
| `role` | optional, only the literal `"device"`. Admin can never be requested; it is set server-side only. |
| `device_id` | UUID derived from the SHA-256 of the SPKI, so re-registering the same key returns the same id. |

Request bodies reject unknown fields (422 `validation_error`, M3's app-wide handler).
The trusted contact's FCM token is **not** sent here; it goes through `POST /trusted-contact`.

## Attestation checks (`POST /auth/device`)

Run in this order; the first failure rejects with **HTTP 400** (api.yaml: "Attestation invalid") and the code shown.
The challenge is consumed before any other check, so a failed attempt burns it (the app fetches a new one).

| # | Check | Error code |
|---|---|---|
| 0 | Challenge exists, unused, not expired | `challenge_invalid` |
| 1 | Chain signatures verify; every cert inside validity; issuers are CAs; top cert is (or is directly issued by) a pinned Google root | `chain_invalid` / `chain_untrusted` |
| 2 | No certificate serial is on Google's revocation status list (fail closed: 503 `attestation_unavailable` if the list cannot be obtained) | `cert_revoked` |
| 3 | Leaf `attestationChallenge` equals the issued challenge | `challenge_invalid` |
| 4 | `attestationSecurityLevel` and `keymasterSecurityLevel` are TEE or StrongBox (software-only rejected; always enforced outside dev) | `software_only` |
| 5 | `verifiedBootState` stored in `devices.verified_boot_state` (`verified`, `self_signed`, `unverified`, `failed`, `unknown`); anything but `verified` is flagged on the record, not rejected | (recorded) |
| 6 | `attestationApplicationId`: exactly one package, equal to the release package; all signing digests are in the expected set and at least one matches | `app_mismatch` |
| 7 | Leaf certificate public key equals the registered `public_key` | `key_mismatch` |

Other 400 codes: `malformed_attestation` (unparseable cert or ASN.1), `invalid_request` (bad base64, oversized field).
503 `attestation_unavailable`: roots not configured, or revocation list unobtainable.

`devices.attestation_level` is `software`, `TEE` or `StrongBox`. Re-attesting an existing device updates
those columns, never its role, and clears `revoked`.

## Tokens

Access token: JWT HS256, `SATARK_JWT_ACCESS_TTL_SECONDS` (default 900).

| Claim | Meaning |
|---|---|
| `sub` | `device_id` |
| `role` | `device` or `admin` |
| `exp`, `iat` | epoch seconds |
| `jti` | random id |
| `typ` | always `access` |

Every request also checks the device row exists and is not `revoked`, so revocation is immediate.

Refresh token: opaque 32-byte random string, 30 days, stored only as a SHA-256 hash in `refresh_tokens`,
**single use**. Presenting an already-used refresh token sets `devices.revoked`, killing every token for that
device until it re-attests: HTTP 401 `refresh_reuse`.

## Route protection

Every route except `GET /health`, `POST /webhooks/razorpay` (HMAC) and the `/auth/*` routes declares one of:

* `device_id: str = Depends(require_device)`: role must be `device`.
* `who: DeviceIdentity = Depends(require_role("admin"))`: exact role match.

Ownership: any lookup by id compares the owner. A device asking for another device's object gets **404, not 403**,
so existence is not leaked (`ensure_owner` for admin-aware code; M3's routers already do this inline).

## Errors

Always `{"code": "...", "message": "..."}`. Never a stack trace, never an echo of input.

| Status | Code | When |
|---|---|---|
| 400 | attestation codes above, `invalid_request` | `/auth/device` |
| 401 | `missing_token` / `invalid_token` / `token_expired` | no/bad/expired access token (`WWW-Authenticate: Bearer`) |
| 401 | `invalid_refresh` / `refresh_reuse` | bad, expired or replayed refresh token |
| 403 | `forbidden_role` | role mismatch |
| 404 | `not_found`, `trusted_device_not_found` | missing **or** owned by another device; unregistered trusted contact |
| 422 | `validation_error` | schema validation failed (M3 handler) |
| 429 | `rate_limited` (+ `Retry-After`) | rate limit hit |
| 503 | `attestation_unavailable` | see above |

## Rate limits (Redis in production, in-memory in dev/tests; fails open if Redis is down)

| Key | Limit | Window |
|---|---|---|
| `rl:challenge:<client_ip>` | 10 | 60 s |
| `rl:register:<client_ip>` | 10 | 60 s (shared by `/auth/device` and `/auth/refresh`) |
| `rl:device:<device_id>` | `SATARK_RATE_LIMIT_PER_MINUTE` (default 60) | 60 s |

Behind Render's proxy `client_ip` is the proxy address unless trusted `X-Forwarded-For` handling is added (open item).

## Configuration (environment, all prefixed `SATARK_`)

| Variable | Notes |
|---|---|
| `JWT_SECRET` | outside `dev`: at least 32 bytes and not the dev default, else the server refuses to boot |
| `AUTH_ATTESTATION_ROOTS` | path to the pinned Google roots PEM (`server/certs/google_attestation_roots.pem`); required outside dev |
| `AUTH_EXPECTED_PACKAGE` | release app package name; required outside dev |
| `AUTH_EXPECTED_SIGNING_SHA256` | comma-separated lowercase hex SHA-256 of the release signing certificate(s); required outside dev |
| `AUTH_REQUIRE_HARDWARE` | default true; forced on outside dev |
| `AUTH_ENABLE_DEV_TOKEN` | dev only (below); refused at boot outside dev |

## Dev token stub (temporary, tagged `# SATARK_STUB`)

`POST /auth/dev-token {device_id, role?}` answers 404 unless `SATARK_ENV=dev` **and** `SATARK_AUTH_ENABLE_DEV_TOKEN=1`.
It lets M1 build before attestation works on a phone (an emulator's chain does not root at Google). It is hidden from
the OpenAPI schema. The stub-marker CI gate (`ops/ci/check_stubs.py`) fails the release build while the marker exists,
so removing the stub is a release blocker by construction.
