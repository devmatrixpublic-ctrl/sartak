# CI/CD (plan 4.2)

Workflows: [`ci.yml`](../../.github/workflows/ci.yml) on every pull request, [`release.yml`](../../.github/workflows/release.yml) on push to `main`.

## What was and was not verified

None of this has run on GitHub yet. What was checked from this machine:

* Both files validate against GitHub's own workflow schema (`check-jsonschema --builtin-schema vendor.github-workflows`).
* `ops/ci/test_workflows.py` pins least-privilege permissions, no `pull_request_target`, no secrets in PR runs, version-pinned actions,
  release gating, and that every script a step calls exists.
* The commands of the `server`, `contracts`, `strings`, `evaluation`, `dependency-scan` and `stubs` jobs were run locally and pass
  (evaluation reports its known failure, below).

**Not verified anywhere yet:** the `detector` job (needs JDK 21 + Gradle; this machine has Java 8), `secrets-scan` (gitleaks via Docker
image `zricethezav/gitleaks:v8.21.2`; Docker is not running here, and the tag is from memory, so a wrong tag shows up as a red job),
`docker`, and `android` / `android-release` (there is no `app/` project in the repo yet, so they skip with a notice).
Actions are pinned to major-version tags, not commit SHAs.

## Pull-request jobs

| Job | Blocks the PR? | Notes |
|---|---|---|
| `server` | yes | server pytest (includes api.yaml contract check + security suite), `pytest ops`, string validation |
| `contracts` | yes | `detector/tools/test_schema.py` (schema.json + UPI mapping) |
| `detector` | yes | Kotlin JUnit incl. the 36 vectors; retries with one worker if Maven Central rate-limits |
| `evaluation` | **no, by default** | see below |
| `secrets-scan` | yes | gitleaks over full history |
| `dependency-scan` | yes | `pip-audit` on the server's installed dependencies. Gradle/Kotlin dependencies are not scanned yet. |
| `docker` | yes | the server image must build |
| `stubs` | yes | a PR may not add more `@SatarkStub` / `# SATARK_STUB` markers than it removes (replacing a stub with a stub is fine) |
| `android` | yes once `app/` exists | `assembleDebug` + unit tests |

The plan's three red-PR examples: *breaks a vector* -> `detector`; *adds a fake key* -> `secrets-scan`; *leaves a stub marker* -> `stubs`.

## The evaluation gate is currently red, on purpose

`ops/eval/run_eval.py` applies the plan's gate (recall >= 93%, false alarms <= 0.1%, point estimates). It reproduces M2's published
numbers exactly: recall 93.4% (met), false alarms 0.111% (**not met**; M2's report says the interval contains both sides). Making every PR
red for that would train people to ignore CI, so in `ci.yml` the job reports (step summary + artifact) and does not block. Set the
repository **variable** `EVAL_GATE_ENFORCED=true` to make it block PRs. `release.yml` always enforces it.
Decision needed from the team: improve the detector, widen the target to the interval, or accept the gap in writing.

## Release (`main`)

`gate` runs first and nothing ships unless it passes: no stub markers anywhere, evaluation gate, strings valid. Today it fails on both
the dev-token stub and the 0.111%. That is the intended release behaviour; it means **no automated deploy until the dev-token stub is
removed and the gate is resolved.** (Render can still deploy from the repo on its own, independent of Actions.)

Then `server-image` builds the image and POSTs the Render deploy hook, and `android-release` builds the signed APK (when `app/` exists).

### Secrets and variables to configure (Settings -> Secrets and variables -> Actions)

| Name | Kind | Used by |
|---|---|---|
| `RENDER_DEPLOY_HOOK_URL` | secret | `server-image` (Render service -> Settings -> Deploy Hook) |
| `ANDROID_KEYSTORE_BASE64` | secret | `android-release`: `base64 -w0 release.keystore` |
| `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | secrets | `android-release` |
| `EVAL_GATE_ENFORCED` | variable | `ci.yml` evaluation job (optional) |

**For M1:** the release job exports `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` as environment variables; the
app module's `signingConfigs.release` must read exactly those, and `minSdk` must cover the older test phone (plan 1.8).
The keystore is decoded into the runner's temp directory and never touches the repo.
