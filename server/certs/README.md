# Pinned Google attestation roots

Put the current Google hardware-attestation root certificates (PEM bundle) in
`google_attestation_roots.pem` in this directory. The Dockerfile copies this folder into the image and
`SATARK_AUTH_ATTESTATION_ROOTS` points at it.

**Copy them from Google's official Android Key Attestation documentation and verify the SHA-256
fingerprints by hand**, including any newly rotated root. They are deliberately not committed yet:
they must not be typed from memory or fetched by a script nobody reviewed.

Until the file exists the server refuses to boot with `SATARK_ENV=production` (fail closed), and
`/auth/device` answers 503 `attestation_unavailable` in dev.

## Helper for the manual check
`python ops/security/attestation_roots.py --write` fetches the roots from Google's attestation API and documentation page, cross-checks them, and
writes `CANDIDATE_google_attestation_roots.pem` (never read by the server) plus a fingerprint table. See `CANDIDATE_ROOTS.md`. The decision to pin
is still a person's: compare the fingerprints with Google's page in a browser, then rename the file.
