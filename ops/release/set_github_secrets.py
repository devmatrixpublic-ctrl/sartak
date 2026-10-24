#!/usr/bin/env python3
"""Set the GitHub Actions secrets and variables the release workflow needs, without ever putting a value on a command line.

  python ops/release/set_github_secrets.py --repo OWNER/REPO --keystore PATH --google-services app/google-services.json \
         --server-url https://<service>.onrender.com/ --pins-file contracts/pins.txt --razorpay-key-id rzp_test_XXXX --dry-run

Nothing is sent until you drop --dry-run AND type the repository name when asked. Give only the options you have; each one sets its own
secrets/variables, so you can run this in stages (the keystore first, the server URL and pins after the deploy).

Secrets (encrypted; passwords are asked with a hidden prompt, or read from the environment variable named in --*-env):
  ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD   (from --keystore)
  GOOGLE_SERVICES_JSON_BASE64                                                                   (from --google-services)
  RENDER_DEPLOY_HOOK_URL                                                                        (from --deploy-hook-env or a prompt)
Variables (public values the workflow prints and checks):
  SATARK_EXPECTED_SIGNING_SHA256   derived from the keystore, so it cannot differ from what the APK is signed with
  SATARK_SERVER_URL                must be https
  SATARK_CERT_PINS                 from --pins-file, needs at least two pins
  SATARK_RAZORPAY_KEY_ID           must be a TEST-mode key id (rzp_test_...)

Values reach `gh` on standard input, never as arguments, and are never printed.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import signing_digest as sd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"^sha256/[A-Za-z0-9+/]{43}=$")


@dataclass
class Item:
    kind: str          # "secret" | "variable"
    name: str
    value: str | None  # None only in a dry run for a value that would be prompted for
    source: str        # human description of where it comes from, never the value itself


def read_pins(path: Path) -> list[str]:
    """The pin lines of contracts/pins.txt (ignores comments), validated. At least two are required."""
    pins = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            if not PIN.match(token):
                raise ValueError(f"not a pin (expected sha256/<44 base64 chars>): {token[:30]}")
            pins.append(token)
    if len(set(pins)) < 2:
        raise ValueError("need at least two distinct pins (a primary and a backup); one pin locks every app out at the next certificate change")
    return list(dict.fromkeys(pins))


def secret_from(env_name: str | None, prompt: str, dry_run: bool) -> str | None:
    if env_name and env_name in os.environ:
        return os.environ[env_name]
    return None if dry_run else getpass.getpass(prompt)


def build_plan(a: argparse.Namespace) -> list[Item]:
    plan: list[Item] = []
    if a.keystore:
        if not a.keystore.is_file():
            raise ValueError(f"keystore not found: {a.keystore}")
        if a.keystore.resolve().is_relative_to(REPO_ROOT.resolve()):
            print("WARNING: that keystore is inside the git repository. Move it out; *.keystore is git-ignored but do not rely on that.")
        store_pw = secret_from(a.keystore_password_env, "Keystore password (hidden): ", a.dry_run)
        key_pw = secret_from(a.key_password_env, "Key password (hidden): ", a.dry_run)
        digest = None
        if store_pw is not None:
            keytool = sd.find_keytool(a.keytool)
            if not keytool:
                raise ValueError("keytool not found, so the signing digest cannot be derived (pass --keytool PATH)")
            digest = sd.digest_of(sd.certificate_der(sd.export_from_keystore(a.keystore, a.alias, keytool, store_pw)))
        plan += [
            Item("secret", "ANDROID_KEYSTORE_BASE64", base64.b64encode(a.keystore.read_bytes()).decode(), f"file {a.keystore.name} ({a.keystore.stat().st_size} bytes)"),
            Item("secret", "ANDROID_KEYSTORE_PASSWORD", store_pw, "hidden prompt or --keystore-password-env"),
            Item("secret", "ANDROID_KEY_ALIAS", a.alias, "--alias"),
            Item("secret", "ANDROID_KEY_PASSWORD", key_pw, "hidden prompt or --key-password-env"),
            Item("variable", "SATARK_EXPECTED_SIGNING_SHA256", digest, "derived from the keystore's certificate"),
        ]
    if a.google_services:
        if not a.google_services.is_file():
            raise ValueError(f"google-services.json not found: {a.google_services}")
        plan.append(Item("secret", "GOOGLE_SERVICES_JSON_BASE64", base64.b64encode(a.google_services.read_bytes()).decode(), f"file {a.google_services.name}"))
    if a.deploy_hook:
        plan.append(Item("secret", "RENDER_DEPLOY_HOOK_URL", secret_from(a.deploy_hook_env, "Render deploy hook URL (hidden): ", a.dry_run), "hidden prompt or --deploy-hook-env"))
    if a.server_url:
        if not a.server_url.startswith("https://"):
            raise ValueError("--server-url must start with https:// (a release must never talk to the server in clear text)")
        plan.append(Item("variable", "SATARK_SERVER_URL", a.server_url if a.server_url.endswith("/") else a.server_url + "/", "--server-url"))
    if a.pins_file:
        plan.append(Item("variable", "SATARK_CERT_PINS", ",".join(read_pins(a.pins_file)), f"file {a.pins_file.name}"))
    if a.razorpay_key_id:
        if not a.razorpay_key_id.startswith("rzp_test_"):
            raise ValueError("--razorpay-key-id must be a TEST-mode key id (rzp_test_...): live mode needs account activation and is out of scope")
        plan.append(Item("variable", "SATARK_RAZORPAY_KEY_ID", a.razorpay_key_id, "--razorpay-key-id"))
    if not plan:
        raise ValueError("nothing to do: give at least one of --keystore, --google-services, --deploy-hook, --server-url, --pins-file, --razorpay-key-id")
    return plan


def apply_plan(plan: list[Item], repo: str, gh_cmd: list[str]) -> list[str]:
    """Run `gh <secret|variable> set NAME --repo REPO` with the value on STDIN. Returns the names set. Raises on the first failure."""
    done = []
    for item in plan:
        if item.value is None:
            raise RuntimeError(f"no value for {item.name}")
        out = subprocess.run([*gh_cmd, item.kind, "set", item.name, "--repo", repo], input=item.value.encode(), capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"gh failed for {item.name}: {out.stderr.decode(errors='replace').strip()[:200]}")
        done.append(item.name)
    return done


def confirmed(typed: str, repo: str) -> bool:
    """The person must type the exact repository name; anything else cancels."""
    return typed.strip() == repo


def describe(plan: list[Item]) -> str:
    lines = ["  kind      name                              source"]
    for it in plan:
        shown = "" if it.value is None else f"  [{len(it.value)} chars]"
        lines.append(f"  {it.kind:<9} {it.name:<33} {it.source}{shown}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="OWNER/REPO")
    ap.add_argument("--keystore", type=Path)
    ap.add_argument("--alias", default="satark-release")
    ap.add_argument("--keystore-password-env", metavar="VAR")
    ap.add_argument("--key-password-env", metavar="VAR")
    ap.add_argument("--keytool")
    ap.add_argument("--google-services", type=Path)
    ap.add_argument("--deploy-hook", action="store_true", help="also set RENDER_DEPLOY_HOOK_URL (prompted)")
    ap.add_argument("--deploy-hook-env", metavar="VAR")
    ap.add_argument("--server-url")
    ap.add_argument("--pins-file", type=Path)
    ap.add_argument("--razorpay-key-id")
    ap.add_argument("--dry-run", action="store_true", help="show what would be set (names and sizes only) and send nothing")
    ap.add_argument("--yes-i-typed-the-repo", metavar="REPO", help="non-interactive confirmation for CI rehearsals: must equal --repo")
    a = ap.parse_args(argv)

    if not re.match(r"^[\w.-]+/[\w.-]+$", a.repo):
        print("FAIL: --repo must look like OWNER/REPO")
        return 2
    try:
        plan = build_plan(a)
    except (ValueError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    print(f"Target repository: {a.repo}\n{describe(plan)}\n")
    if a.dry_run:
        print("DRY RUN: nothing was sent. Re-run without --dry-run to apply.")
        return 0

    gh = shutil.which("gh")
    if not gh:
        print("FAIL: the GitHub CLI (gh) is not installed or not on PATH.")
        return 2
    if subprocess.run([gh, "auth", "status"], capture_output=True).returncode != 0:
        print("FAIL: gh is not logged in. Run `gh auth login` yourself first (this script never handles your GitHub credentials).")
        return 2
    typed = a.yes_i_typed_the_repo or input(f"Type the repository name ({a.repo}) to set the {len(plan)} items above: ").strip()
    if not confirmed(typed, a.repo):
        print("Cancelled: that is not the repository name. Nothing was sent.")
        return 1
    try:
        done = apply_plan(plan, a.repo, [gh])
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"Set {len(done)} items on {a.repo}: " + ", ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
