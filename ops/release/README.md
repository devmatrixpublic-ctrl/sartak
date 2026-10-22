# Release signing: keystore, secrets and the server's signing digest (M4, with M1 and M3)

**Do this on a trusted machine, by a person.** A signing key is secret material: nothing in this repo or its tooling generates one, and
`.gitignore` already excludes `*.keystore` and `*.jks`. Never commit, paste into chat, or email the keystore or its passwords.

## 1. Create the release keystore (once)

```bash
keytool -genkeypair -v -keystore satark-release.keystore -alias satark-release \
        -keyalg RSA -keysize 4096 -validity 10000
```
It asks for a store password, a key password and a distinguished name. Keep the file and both passwords in a password manager and make
an offline backup: if the key is lost, installs signed with it cannot be updated in place.

## 2. Get the signing certificate digest the server needs

```bash
keytool -list -v -keystore satark-release.keystore -alias satark-release | grep "SHA256:"
```
Lowercase it and remove the colons to get 64 hex characters, e.g. `AB:CD:...` becomes `abcd...`. Set that as
`SATARK_AUTH_EXPECTED_SIGNING_SHA256` on Render (`server/DEPLOY_CHECKLIST.md`). It is a comma-separated list: during phone testing add the
**debug** build's digest too (M1's debug export prints it) and **remove it before real use**, otherwise a debug-signed app could register.

## 3. GitHub secrets (Settings -> Secrets and variables -> Actions)

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -w0 satark-release.keystore` (on macOS: `base64 -i satark-release.keystore`) |
| `ANDROID_KEYSTORE_PASSWORD` | the store password |
| `ANDROID_KEY_ALIAS` | `satark-release` |
| `ANDROID_KEY_PASSWORD` | the key password |
| `RENDER_DEPLOY_HOOK_URL` | Render service -> Settings -> Deploy Hook |
| (variable) `EVAL_GATE_ENFORCED` | optional, `true` to make the evaluation gate block PRs |

`release.yml` decodes the keystore into the runner's temp directory and passes the passwords through the environment; the app's
`signingConfigs.release` reads `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` (or the `SATARK_*` equivalents).

## 4. Check a built release APK really carries that certificate

```bash
apksigner verify --print-certs app-release.apk        # the "certificate SHA-256 digest" must equal the value in step 2
```

## What blocks a release today
`release.yml` runs a gate first and ships nothing while any `@SatarkStub` / `# SATARK_STUB` marker remains (the dev-token stubs, removed
once real Key Attestation works on a phone) or while the evaluation gate fails. The APK and deploy jobs only run after it passes.
