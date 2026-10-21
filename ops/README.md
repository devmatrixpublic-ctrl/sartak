# ops/: Member 4 workspace

Source of truth: the module-wise implementation plan, "Member 4: Security, CI/CD, Evaluation, Explanations".

| Plan item | Where | Status |
|---|---|---|
| 4.1 Auth contract | `contracts/auth.md` | done |
| 4.1 Auth logic (challenge, attestation checks, JWT, refresh rotation, rate limit, `require_device`/`require_role`, IDOR helper) | `server/app/auth/` | done; `cd server && pytest` (129 tests, 12 security mutations verified caught) |
| 4.1 SQL store on M3's tables + migration | `server/app/auth/store.py`, `migrations/versions/a3c91d7e5b20_*` | done (adds `refresh_tokens`, `devices.revoked`: **M3 please review**) |
| 4.1 Real Google roots | `server/certs/google_attestation_roots.pem` | **not committed**: copy from Google's docs, verify fingerprints by hand |
| 4.1 Chains captured from both real phones | `server/tests/fixtures/` | **blocked on M1** producing attestation on a device |
| 4.2 CI/CD | `.github/workflows/` | stub-marker gate done (`ops/ci/check_stubs.py`); workflows not written |
| 4.3 Evaluation pipeline | `ops/eval/` | blocked: M2's detector is on `feat/m2-detector`, not merged |
| 4.4 Explanation strings | `ops/strings/` | blocked on M2's `contracts/reason_codes.json` |
| 4.5 Security checklist | `ops/security/checklist.md` | not started |
| 4.6 Held-out runner | `ops/heldout/run_heldout.py` | blocked on `detector-freeze` tag and the held-out data |
| `contracts/pins.txt` | | blocked on the Render domain |

Open items that touch other members:

* **M3**: production boot now needs `SATARK_AUTH_ATTESTATION_ROOTS`, `SATARK_AUTH_EXPECTED_PACKAGE`, `SATARK_AUTH_EXPECTED_SIGNING_SHA256`
  (wired in `render.yaml`); until set, the Render service will refuse to start. M3's `ensure_device_exists` stub is removed:
  `/trusted-contact` now 404s for an unregistered contact instead of fabricating a device.
* **M1**: read `contracts/auth.md` for encodings; use `/auth/dev-token` (dev only) until attestation works on a phone.
* Client IP for rate limiting is the proxy address on Render until trusted `X-Forwarded-For` is added.

```
python ops/ci/check_stubs.py .    # lists stub markers; exit 1 until the dev-token stub is removed
```
