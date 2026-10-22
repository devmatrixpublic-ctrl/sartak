# CI/CD (plan 4.2)

Workflows: [`ci.yml`](../../.github/workflows/ci.yml) on every pull request, [`release.yml`](../../.github/workflows/release.yml) on push to `main`.

## What was and was not verified

**Ran on GitHub** (PR #9, head `01e039d`, 10 checks, all success): server tests + ops tests + strings, contract tests, detector
JUnit (36 vectors, parity, fuzz), evaluation (reports, does not block), gitleaks over full history, dependency scan, server
image build, stub check, TLS/pin tool tests. The `android` job was **skipped** there because `app/` did not exist yet.

**Not yet verified on a runner:** the `android` and `android-release` jobs (first real run happens once `app/` is merged; they
need JDK 21, see below), the Render deploy hook, and anything that needs secrets.

**Fixed after review:** both Android jobs asked `setup-java` for JDK 17 while `app/` (`JavaVersion.VERSION_21`) and `detector/`
(`jvmToolchain(21)`) need 21, so the first Android job would have failed on toolchain resolution. They now use 21, and
`test_every_java_setup_matches_the_toolchain_the_projects_require` reads the requirement from the Gradle files so it cannot
drift again. Actions are pinned to major-version tags, not commit SHAs.

Also checked locally: both files validate against GitHub's workflow schema, and `ops/ci/test_workflows.py` pins least-privilege
permissions, no `pull_request_target`, no secrets in PR runs, version-pinned actions, release gating, and that every script a
step calls exists.

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

## The evaluation gate

`ops/eval/run_eval.py` applies the plan's gate (recall >= 93%, false alarms <= 0.1%, point estimates) to a fresh run of the reference
detector and checks its counts equal the ones in `detector/detector_report.md`. It currently **passes** (recall 93.1%, false alarms 0.071%);
it was red (0.111%) until thresholds were calibrated with a margin (`detector/experiments/calibration_margin_cv.md`). The intervals still
straddle both targets, and cross-validation puts recall nearer 91.8%, so a future model change can turn it red again. In `ci.yml` the
job reports (step summary + artifact) and does not block PRs; set the repository **variable** `EVAL_GATE_ENFORCED=true` to make it block.
`release.yml` always enforces it.

## Release (`main`)

`gate` runs first and nothing ships unless it passes: no stub markers anywhere, evaluation gate, strings valid. Today it fails on the
dev-token stub only. That is the intended release behaviour; it means **no automated deploy until the dev-token stub is removed.** (Render can still deploy from the repo on its own, independent of Actions.)

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
