# Release: keystore, secrets, signed APK and GitHub Release (M4, with M1 and M3)

Goal: one **signed APK on a download link**, built by CI from a version tag, talking to the production server with certificate pinning.

**The secret-sensitive steps are done by a person, on a trusted machine.** Nothing here generates a key unattended or sets a GitHub secret
without a typed confirmation, and no value ever appears on a command line or in output. `.gitignore` already excludes `*.keystore` and `*.jks`.

| Step | Who | Tool | Result |
|---|---|---|---|
| 1. Pinned Google roots | M4 | `server/certs/ROOTS_VERIFICATION.md` | `server/certs/google_attestation_roots.pem` (committed, 4 roots) |
| 2. Keystore | M4, once | `make_keystore.py` | `satark-release.keystore` outside the repo, plus its public digest |
| 3. Firebase file | M3 | (Firebase console) | `app/google-services.json` (git-ignored) |
| 4. Server on Render | M3 + M4 | `server/DEPLOY_CHECKLIST.md` | `https://<service>.onrender.com/` with `SATARK_AUTH_EXPECTED_SIGNING_SHA256` set |
| 5. Pins | M4, after step 4 | `ops/security/tls_pins.py` | `contracts/pins.txt` |
| 6. Secrets and variables | M4 | `set_github_secrets.py` | what `release.yml` reads |
| 7. Real-phone check | M1 + M4 | `ops/e2e/verify_captured_chain.py` | proof the server accepts a real phone's chain |
| 8. Remove the stubs | M1 + M4 | `patches/remove-dev-token.patch` | release gate passes |
| 9. Tag | M4 | `git tag v1.0.0 && git push origin v1.0.0` | signed APK on a GitHub Release |

Run all tests of these tools with `pytest ops/release ops/e2e/test_verify_captured_chain.py ops/ci/test_workflows.py`.

## 1. Pinned Google roots

`server/certs/google_attestation_roots.pem` holds four Google attestation roots. A person must still compare their SHA-256 fingerprints
with Google's published page and tick the boxes in `server/certs/ROOTS_VERIFICATION.md`; it also says how to drop the two roots that only the
docs page lists.

## 2. Create the release keystore (once)

```bash
python ops/release/make_keystore.py
```
`keytool` asks for the passwords and your details on your own terminal; the script never sees them. It refuses to write inside this
repository, refuses to overwrite an existing keystore, and refuses a key under 2048 bits. Default location:
`~/satark-signing/satark-release.keystore`. It prints the **public** certificate digest at the end.

Back the file up offline and keep both passwords in a password manager: if the key is lost, installs signed with it can never be updated.

To read the digest again, or validate a value before pasting it into Render:
```bash
python ops/release/signing_digest.py --keystore ~/satark-signing/satark-release.keystore --alias satark-release
python ops/release/signing_digest.py --check "<digest>,<digest>"
```
Set the printed 64-hex value as `SATARK_AUTH_EXPECTED_SIGNING_SHA256` on Render. It is a comma-separated list: while testing on phones you may
add the **debug** build's digest too, and you must **remove it before real use**, otherwise a debug-signed app could register.

## 3. Firebase file

M3 downloads `google-services.json` for package `com.satark.app` and saves it as `app/google-services.json` (git-ignored). CI checks the copy it
decodes is for this package: `python ops/release/check_google_services.py app/google-services.json` (it never prints the contents).

## 5. Certificate pins (after the Render domain exists)

```bash
python ops/security/tls_pins.py --host <service>.onrender.com --write contracts/pins.txt
python ops/release/pins_value.py            # the single value the build takes (also shown with --gradle)
```
Read the per-pin notes it prints: Render renews its certificate about every 90 days and may change the leaf key, so the second pin must be an
**intermediate or root**, not the leaf. `pins.txt` holds public values and is committed (M1 reads it). With fewer than two pins the tool refuses.

## 6. GitHub secrets and variables

Dry run first. It shows each name and where its value comes from, never the value:
```bash
python ops/release/set_github_secrets.py --repo devmatrixpublic-ctrl/sartak \
    --keystore ~/satark-signing/satark-release.keystore --google-services app/google-services.json \
    --server-url https://<service>.onrender.com/ --pins-file contracts/pins.txt \
    --razorpay-key-id rzp_test_XXXX --deploy-hook --dry-run
```
Then run it again without `--dry-run`; it asks you to type the repository name before sending anything. Every option sets its own names, so
it can be run in stages (keystore first, server URL and pins after the deploy). Passwords are asked with a hidden prompt, or read from the
environment variable named by `--keystore-password-env` / `--key-password-env`.

| Name | Kind | Set from |
|---|---|---|
| `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | secrets | `--keystore` |
| `GOOGLE_SERVICES_JSON_BASE64` | secret | `--google-services` |
| `RENDER_DEPLOY_HOOK_URL` | secret | `--deploy-hook` (Render service -> Settings -> Deploy Hook) |
| `SATARK_EXPECTED_SIGNING_SHA256` | variable | derived from the keystore, so it cannot differ from what the APK is signed with |
| `SATARK_SERVER_URL` | variable | `--server-url` (must be https; a trailing slash is added) |
| `SATARK_CERT_PINS` | variable | `--pins-file` (at least two pins) |
| `SATARK_RAZORPAY_KEY_ID` | variable | `--razorpay-key-id` (must be a TEST key, `rzp_test_...`) |
| `EVAL_GATE_ENFORCED` | variable | optional, `true` to make the evaluation gate block PRs |

## 7. Does the server accept a real phone?

M1 captures a chain on each phone (`python app/tools/phone_check.py --build` saves `app/build/phone_check/attestation_*.json`). Then:
```bash
python ops/e2e/verify_captured_chain.py app/build/phone_check/attestation_*.json
python ops/e2e/verify_captured_chain.py phoneA.json phoneB.json --expected-digests "<release digest>"   # test the release certificate
```
It runs the server's own verifier but reports **every** check instead of stopping at the first (chain to a pinned root, revocation, challenge,
hardware level, verified boot, package, signing digest, key match) and explains each failure: the top certificate's fingerprint when the root is
unknown, the digest to add when the signing certificate differs, what an emulator chain looks like. Exit code 0 only if every file is accepted.
`--allow-software` inspects an emulator chain; `--skip-revocation` works offline; `--json` for scripts.

## 8. Remove the stubs, only after step 7 passes

`patches/remove-dev-token.patch` removes the server's `/auth/dev-token` route, service method, `SATARK_AUTH_ENABLE_DEV_TOKEN` setting and its
boot rule, the stub register entries, and the docs that mention them. It also makes `ops/e2e/run_e2e.py` register devices through the real
`/auth/device` with a synthetic chain (throwaway root, no network). It was built and tested in a scratch worktree: server 226 passed, ops tests
and `ops/e2e/test_smoke.py` pass, `run_e2e.py` 71/71. Apply with:
```bash
git apply --check ops/release/patches/remove-dev-token.patch && git apply ops/release/patches/remove-dev-token.patch
```
The Android side (`net/Network.kt`, the debug fallback and `DevTokenRequest` in `Api.kt`) is M1's. After removal an emulator cannot register
with any server, by design. The release gate stays red until the last `@SatarkStub` marker is gone.

## 9. Tag and publish

```bash
git tag v1.0.0 && git push origin v1.0.0
```
A tag matching `v*` runs `release.yml`: the gate, then `android-release`:

1. `check_release_config.py` - https server URL (not local), at least two valid pins, a test-mode Razorpay key, a valid digest list, a `vX.Y.Z` tag. All problems are reported together.
2. decode the keystore and `google-services.json` (checked to be for `com.satark.app`);
3. `./gradlew :app:assembleRelease -PsatarkBaseUrl -PsatarkPins -PsatarkRazorpayKey` (the names `app/build.gradle.kts` reads);
4. `apksigner verify --print-certs` and `check_apk_signature.py`: **every** signer must be in the expected digest list, so an APK signed with the
   wrong key (which would be rejected by every phone's registration) never ships;
5. upload the APK and its `.sha256` as a workflow artifact;
6. on a tag only, `gh release create` publishes a **pre-release** with the checksum in the notes and `--verify-tag`.

The workflow can also be started by hand (Actions -> Release -> Run workflow): it builds and uploads the APK but publishes nothing. A push to
`main` deploys the server and does not build an APK; a tag does not redeploy the server. Only the APK job has `contents: write`. No expression is
interpolated into a script: values reach scripts through `env`, so a tag or branch name can never become shell code.

## Check a built APK by hand

```bash
apksigner verify --print-certs app-release.apk
python ops/release/check_apk_signature.py --certs <that output saved to a file> --expected "<release digest>"
```

## What blocks a release today
`release.yml` runs a gate first and ships nothing while any `@SatarkStub` / `# SATARK_STUB` marker remains (the dev-token stubs, removed
once real Key Attestation works on a phone) or while the evaluation gate fails. The APK and deploy jobs only run after it passes.
