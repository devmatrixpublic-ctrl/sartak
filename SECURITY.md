# Security Policy

Satark handles payment decisions for people who may be under pressure from a scammer. Security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue, pull request or discussion for a security problem.**

Report it privately instead:

1. Open the repository's **Security** tab and choose **Report a vulnerability** (GitHub private vulnerability reporting), **or**
2. If that option is not available, contact a maintainer through their GitHub profile and ask for a private channel. Do not put details in the first message.

Include what you found, where (file, endpoint or screen), the steps to reproduce it, and what an attacker could do with it. A proof of concept helps. Please do not include real
personal data, real payment details or other people's accounts.

### What to expect

This is a small project, so these are goals and not guarantees:

- an acknowledgement within a few days;
- an assessment and a plan, or a request for more detail, within two weeks;
- a fix, or a clear explanation if we decide not to fix it, and credit if you want it.

Please give us a reasonable chance to fix a problem before you publish it.

## Scope

**In scope**
- The backend in `server/` and its API (`contracts/api.yaml`): authentication and attestation, authorization (reading or changing another device's data), trusted-contact linking and
  invite codes, payment state, webhook verification, rate limiting, injection and input handling.
- The Android app in `app/`: ways to bypass the fingerprint or PIN lock, the protection-off wait, the device-admin guard or the hold screen; leaks of personal data; insecure storage or
  transport.
- Anything that lets someone read, change or redirect another person's alerts.

**Out of scope**
- The public **test server**. It is a demo that runs in development mode with fake dev tokens enabled, by design. Findings that depend on that mode (open API docs, dev tokens, claiming a
  phone number) are known and listed below.
- Social engineering of maintainers, denial of service by volume, and findings that need a rooted or already-compromised phone.
- Missing hardening that is already on the roadmap (below).

## Known limitations

These are documented, not secret:

- The test deployment runs in **development mode**: the API docs are open and `/auth/dev-token` issues tokens. Sign-in on it accepts a fixed test code.
- Production boot is blocked until the Google attestation roots are pinned by a person; certificate pinning, a restricted database role and a release signing key are not done.
- A legacy `POST /trusted-contact` route lets the device owner supply the contact's push address. The app no longer uses it, and it should be removed or guarded.
- All detection accuracy figures are from a simulator.

## What is already in place

Strict request models, owner-scoped lookups, HMAC-verified webhooks, request-body caps, rate limits, single-use refresh tokens with reuse revocation, Key Attestation checks, keyed hashing
of phone numbers and invite codes, no personal data in logs, a secret scan and a dependency scan in CI. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the trust boundaries.

## Supported versions

Satark is a prototype. Only the latest `main` is supported.

## Handling secrets

If you find a credential in the repository or its history, report it privately as above. Do not use it. We will rotate it.
