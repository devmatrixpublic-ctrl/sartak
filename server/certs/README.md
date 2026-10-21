# Pinned Google attestation roots

Put the current Google hardware-attestation root certificates (PEM bundle) in
`google_attestation_roots.pem` in this directory. The Dockerfile copies this folder into the image and
`SATARK_AUTH_ATTESTATION_ROOTS` points at it.

**Copy them from Google's official Android Key Attestation documentation and verify the SHA-256
fingerprints by hand**, including any newly rotated root. They are deliberately not committed yet:
they must not be typed from memory or fetched by a script nobody reviewed.

Until the file exists the server refuses to boot with `SATARK_ENV=production` (fail closed), and
`/auth/device` answers 503 `attestation_unavailable` in dev.
