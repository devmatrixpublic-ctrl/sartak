#!/usr/bin/env python3
"""Create the release keystore (once), safely, and print the signing digest the server needs.

  python ops/release/make_keystore.py                       # interactive: keytool asks for passwords and your details

Safety rules this script enforces (each is a way keystores get lost or leaked):
  * it will NOT create the file inside this git repository (a keystore next to the code is one `git add -A` from being published);
  * it will NOT overwrite an existing keystore (losing the old key means installs signed with it can never be updated);
  * it never sees, prints or stores your passwords: keytool prompts for them on your terminal;
  * afterwards it reads back only the PUBLIC certificate digest.

Default location: ~/satark-signing/satark-release.keystore. After it succeeds: back the file up offline, store both passwords in a
password manager, then run ops/release/set_github_secrets.py.

Non-interactive mode exists for tests and CI rehearsals only (--storepass-env/--keypass-env/--dname).
"""
from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import signing_digest as sd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO.resolve())
        return True
    except ValueError:
        return False


def build_command(keytool: str, keystore: Path, alias: str, keysize: int, validity: int, dname: str | None,
                  storepass_env: str | None, keypass_env: str | None) -> list[str]:
    cmd = [keytool, "-genkeypair", "-v", "-keystore", str(keystore), "-alias", alias, "-keyalg", "RSA",
           "-keysize", str(keysize), "-validity", str(validity)]
    if dname:
        cmd += ["-dname", dname]
    if storepass_env:
        cmd += ["-storepass:env", storepass_env]
    if keypass_env:
        cmd += ["-keypass:env", keypass_env]
    return cmd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path.home() / "satark-signing" / "satark-release.keystore")
    ap.add_argument("--alias", default="satark-release")
    ap.add_argument("--keysize", type=int, default=4096)
    ap.add_argument("--validity", type=int, default=10000, help="days")
    ap.add_argument("--keytool")
    ap.add_argument("--dname", help="non-interactive only, e.g. 'CN=Satark, O=Satark'")
    ap.add_argument("--storepass-env")
    ap.add_argument("--keypass-env")
    ap.add_argument("--allow-in-repo", action="store_true", help="tests only: permit a path inside the git repository")
    a = ap.parse_args(argv)

    keytool = sd.find_keytool(a.keytool)
    if not keytool:
        print("FAIL: keytool not found. Install a JDK (for example Temurin 21) or pass --keytool PATH.")
        return 2
    if inside_repo(a.out) and not a.allow_in_repo:
        print(f"REFUSED: {a.out} is inside the git repository. Choose a folder outside it (the default is ~/satark-signing).")
        return 2
    if a.out.exists():
        print(f"REFUSED: {a.out} already exists. Never overwrite a release keystore: if you lose the old key, installs signed with it "
              "cannot be updated. Pick another --out if you really want a second one.")
        return 2
    if a.keysize < 2048:
        print("REFUSED: key size must be at least 2048 (default 4096).")
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)

    interactive = not (a.storepass_env and a.keypass_env and a.dname)
    if interactive:
        print("keytool will now ask for a store password, a key password and your details. Use long, unique passwords from a password manager.\n")
    cmd = build_command(keytool, a.out, a.alias, a.keysize, a.validity, a.dname, a.storepass_env, a.keypass_env)
    if subprocess.run(cmd).returncode != 0 or not a.out.is_file():
        print("FAIL: keytool did not create the keystore.")
        return 1

    password = os.environ[a.storepass_env] if a.storepass_env else getpass.getpass("\nStore password again (hidden), to read the public digest back: ")
    try:
        digest = sd.digest_of(sd.certificate_der(sd.export_from_keystore(a.out, a.alias, keytool, password)))
    except (RuntimeError, ValueError) as exc:
        print(f"Keystore created, but reading it back failed: {exc}")
        return 1

    print(f"\nCreated {a.out}")
    print(f"Signing certificate SHA-256 (public, safe to share): {digest}")
    print(f"\n  Render:   {sd.ENV_NAME}={digest}")
    print("  Next:     1) back the keystore up OFFLINE and store both passwords in a password manager")
    print("            2) python ops/release/set_github_secrets.py --keystore <path> ...   (use --dry-run first)")
    print("            3) while testing on a phone, ALSO list the debug build's digest on Render, and remove it before real use")
    return 0


if __name__ == "__main__":
    sys.exit(main())
