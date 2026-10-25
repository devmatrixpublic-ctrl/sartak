## What and why

<!-- What does this change, and why? Link the issue if there is one. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Change to a shared contract (`contracts/`)
- [ ] Documentation or tooling only

## How it was tested

<!-- The suites you ran and what you checked by hand (on a phone, if it touches the app). -->

- [ ] `cd server && pytest`
- [ ] `./gradlew :app:testDebugUnitTest`
- [ ] `cd detector && gradle test`
- [ ] `pytest ops`
- [ ] Tried on a phone

## Checklist

- [ ] No secrets, keystores, `.env`, `google-services.json` or database files are included.
- [ ] Nothing new is logged or stored that identifies a person, a payee, an amount, a phone number or message content.
- [ ] Satark does not become quieter, or if it does, the evidence and `docs/WHEN_SATARK_WARNS.md` are updated.
- [ ] Any API change updates `contracts/api.yaml`, the server route, the app types and the contract test together.
- [ ] A new table has a migration (one Alembic head) and is cleared by *Delete my data* if it references a device.
- [ ] Docs and `CHANGELOG.md` are updated.
- [ ] Accuracy claims say they come from the simulator.
