# Contributing to Satark

Thanks for helping. Satark protects people from fraud, so changes are held to a few rules that matter more than speed. Read this once; it is short.

## Ground rules

1. **Privacy is a feature.** Never log or store a rupee amount, a payee identity, a phone number, message content or call content. The server keeps amount *bands* and *hashed*
   payees; the phone number is kept only as a keyed hash. A change that widens what is collected needs a written reason in the pull request.
2. **Warnings can be added, never silently removed.** App policies sit beside the frozen detector and may only add warnings. Anything that makes Satark quieter needs evidence
   (a test or an evaluation run) and a note in `docs/WHEN_SATARK_WARNS.md`.
3. **Say what is simulated.** Every accuracy figure in this repository comes from the SatarkSim simulator. Do not present a simulated result as real-world accuracy.
4. **No secrets in git.** Never commit `google-services.json`, a Firebase service-account key, Razorpay secrets, keystores, `.env` files or database files. CI runs a secret scan over
   the full history.
5. **Fail closed.** A missing credential or an unverifiable request must refuse, not fall back to something permissive.

## Getting set up

| Tool | Version |
|---|---|
| JDK | 21 (newer JDKs fail the Android build) |
| Python | 3.11 or newer |
| Android SDK | platform 36 |

```bash
# backend
cd server && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" -r ../ops/requirements-eval.txt
alembic upgrade head
pytest

# app
./gradlew :app:testDebugUnitTest

# detector
cd detector && gradle test
```

The README's [Getting started](README.md#getting-started) has the debug build flags and the demo steps.

## Workflow

1. **Branch from `main`.** Use a short, descriptive name: `feat/invite-code`, `fix/hold-card-close`, `docs/readme`.
2. **Keep a change focused.** One concern per pull request. Do not mix a refactor with a behaviour change.
3. **Write the test first or with the change.** A bug fix includes a test that fails without it.
4. **Run the suites that your change touches** (below) before you open the pull request.
5. **Open a pull request** and fill in the template. Link the issue if there is one.

### Commit messages

Use the form `area: what changed`, in the present tense and in plain words:

```
server: reject an invite code after its first use
app: close the hold card without waiting for the contact
docs: describe the data inventory
```

`feat:` and `fix:` prefixes are fine too. The body should say *why*, not repeat the diff.

## What to run

| You changed | Run |
|---|---|
| `server/` | `cd server && pytest` |
| `contracts/api.yaml` | `cd server && pytest` (a test checks every contract path and method is implemented) and `./gradlew :app:testDebugUnitTest` (the app checks its requests and responses against the yaml) |
| `app/` | `./gradlew :app:testDebugUnitTest` |
| `detector/` or `contracts/schema.json` | `cd detector && gradle test` and `pytest detector/tools/test_schema.py` |
| `ops/` | `pytest ops` |
| Explanation strings | `python ops/strings/validate_strings.py` |

Do not skip a failing test or loosen an assertion to get green. If a test is wrong, fix it and say why.

## Changing a shared contract

`contracts/` is shared by the app, the detector and the backend. A change there affects more than one module, so:

- **`contracts/api.yaml`** (the API): change the yaml, the server route, the app's request and response types and their contract test in the **same** pull request. Optional fields are
  *absent*, not `null`.
- **`contracts/schema.json` and `reason_codes.json`** (the detector's inputs and reasons): owned by the detector. A change can invalidate the frozen model and its 36 test vectors,
  so open an issue first.
- **Reviewers:** a contract change needs approval from the owner of each consuming module.

## Database changes

Every schema change needs an Alembic migration in `server/migrations/versions/` with a unique, linear revision chain (`alembic heads` must show one head). The migration must apply
to an empty database, and the model and the migration must match. Remember "Delete my data" (`DELETE /device`): a new table that references a device must be cleared there.

## Code style

- **Kotlin:** idiomatic Kotlin, small composables, state hoisted where it is shared. Match the surrounding file. Keep comments for the *why*.
- **Python:** type-annotated, `StrictInput` request models (`extra="forbid"`), errors through `ApiError`, no raw SQL built from user input.
- Follow [`.editorconfig`](.editorconfig): UTF-8, LF line endings, no trailing whitespace.
- Prefer a plain sentence to a clever one in user-facing text. The people reading it may be frightened.

## Reporting bugs and asking for features

Use the issue templates. For a **security** problem, do **not** open a public issue: follow [SECURITY.md](SECURITY.md).

## Release gate

The release workflow refuses to deploy while a `@SatarkStub` (Kotlin) or `# SATARK_STUB` (Python) marker remains, or while the evaluation gate fails. A temporary shortcut must carry
the marker so it cannot ship by accident.

## Code of conduct

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
