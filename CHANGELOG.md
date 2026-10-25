# Changelog

All notable changes to Satark are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/) once it has a release. Until then, everything is a prototype and only the latest `main` is supported.

## [Unreleased]

### Added
- **Device check at payment time.** Tapping *Check and pay* looks at the installed apps and warns if the phone is vulnerable: remote-access apps, root or hooking tools, known modified
  messaging clones and well-known payment apps from outside a store (serious), and any other app installed from outside an official store (weak). It sends a notification (at most one a day
  for the same set), shows a card with a *Remove* button, and asks before the payment. A warning only: it never holds a payment or reaches the detector. Trusted stores include Google Play and
  the phone makers' own stores. 32 new tests.
- **Short invite code for linking a trusted contact.** The contact taps *Get an invite code* and reads out eight characters such as `K7M4-Q2XH`; the person being protected types it.
  The code is valid for 10 minutes, works once, is stored only as a keyed hash, and is limited to 10 tries an hour per phone. New routes `POST /trusted-contact/invite` and
  `POST /trusted-contact/join`; new table `trusted_invites`.
- `GET /trusted-contact`: the people who accepted, by name. A pending request is never shown.
- A *Close this and start over* button on the "Payment on hold" card.
- Project documentation: a rebuilt README, `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull request templates, `.editorconfig`,
  and `server/.env.example`.

### Changed
- The long pairing code and the by-phone link call are removed. The contact's own phone now supplies its push address when it asks for a code, so the person being protected
  can no longer supply (or replace) it.

### Fixed
- The "protection turned off" and "removal guard off" alerts were skipped for a contact who was linked without the old pairing code, because the phone never recorded that it
  had a contact. They are now always sent, and the server decides who receives them.
- The hold card on the Pay screen stayed until the next payment.

### Known issues
- A legacy `POST /trusted-contact` route still lets a device owner supply a contact's push address. The app no longer calls it.

## [0.1.0] - 2026-10-25

First working prototype: Android app, on-device detector, backend, and security, CI and evaluation tooling.

### Added
- **Detector.** Sixteen features, a logistic score with a split-conformal threshold per age band, two rules (a sideload install during an unknown call; a two-hour unknown video call),
  reason codes in English and Hindi, and a rolling baseline of the person's own payments.
- **Payments.** Pay via Satark (scan a UPI QR or type a UPI ID), a hand-off to the person's UPI app, and a Razorpay test checkout verified by webhook. Server-side payment state
  machines; a payee fan-in check that holds a payee paid by several devices in an hour.
- **Warnings.** A quiet, nudge or hold result. The nudge is a step before the payment is sent. A held payment always shows the Stop screen.
- **App policies beside the detector** (they only add warnings): a split guard for payments added up to one new payee; a hold for ₹25,000 or more to a new payee during or soon after an
  unknown call; ₹10,000 for people under 22; a nudge at twice the usual amount; a warning for a burst of texts from strangers.
- **Trusted contact.** A push naming the person; approve or block a held payment; the contact must accept; an unanswered hold stays held.
- **Anti-coercion.** A fingerprint (or screen-lock PIN) is needed for *Continue anyway*, turning protection off, changing the contact or age, and deleting data. Turning protection off waits
  30 minutes and tells the contact at once. A device-admin guard blocks uninstalling and tells the contact if it is switched off.
- **Accounts.** Optional phone-number sign-in (Firebase one-time code); the number is kept only as a keyed hash; the contact sees a name. Phones register their own push address.
- **Backend.** FastAPI, Alembic migrations, Key Attestation device identity with JWT and single-use refresh rotation, rate limits, Razorpay webhook handling, Firebase push,
  *Delete my data*, a Dockerfile and a Render blueprint.
- **Tooling.** An evaluation pipeline with a recall and false-alarm gate, a held-out runner, a secret scan and a dependency scan in CI, a gated release workflow, and a deployed-server smoke test.

### Security
- Strict request models, owner-scoped lookups, HMAC-verified webhooks, request-body caps, structured logs with no request bodies, and Key Attestation checks on the app package and signing certificate.

### Known limitations
- All accuracy figures are from a simulator; the sealed held-out run has not been done.
- The public test server runs in development mode. Production needs pinned attestation roots, a release signing key, certificate pinning and a restricted database role.
- Payments started inside another UPI app can be warned about but not held.

[Unreleased]: https://github.com/Amogh-Thorve/Satark-Raksham/compare/main...HEAD
