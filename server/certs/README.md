# Pinned Google attestation roots

Put the current Google hardware-attestation root certificates (PEM bundle) in
`google_attestation_roots.pem` in this directory. The Dockerfile copies this folder into the image and
`SATARK_AUTH_ATTESTATION_ROOTS` points at it.

**Current state:** the file is present and holds four verified roots; see `ROOTS_VERIFICATION.md` for exactly what was checked, what was not,
and the sign-off box a person must complete before committing it. Roots must never be typed from memory: refresh them with the helper below and
compare them with Google's page.

Without the file the server refuses to boot with `SATARK_ENV=production` (fail closed), and `/auth/device` answers 503
`attestation_unavailable` in dev.

## Helper for the manual check
`python ops/security/attestation_roots.py --write` fetches the roots from Google's attestation API and documentation page, cross-checks them, and
writes `CANDIDATE_google_attestation_roots.pem` (never read by the server) plus a fingerprint table. See `CANDIDATE_ROOTS.md`. The decision to pin
is still a person's: compare the fingerprints with Google's page in a browser, then rename the file.
