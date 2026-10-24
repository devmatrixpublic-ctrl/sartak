#!/usr/bin/env python3
"""Will the server's Firebase push really reach a phone? Three escalating checks, none of which prints a secret.

  1. offline      python ops/e2e/check_push.py --credentials service-account.json [--google-services app/google-services.json]
                  The key parses with the server's own loader, and (if given) belongs to the SAME Firebase project as the app's
                  google-services.json. A token minted by one project cannot be pushed by another project's key: that mismatch is the usual
                  reason "the push does nothing", and it is visible here without any network.
  2. dry run      ... --token-env FCM_TOKEN --dry-run
                  Firebase validates the message and the token and delivers nothing.
  3. real push    ... --token-env FCM_TOKEN --send
                  A notification titled "Satark push test" arrives on that phone. This is the step that proves the second phone receives alerts.

The credentials come from --credentials (a file) or the SATARK_FIREBASE_CREDENTIALS_JSON environment variable (the same value Render holds).
The phone's token comes from the environment variable NAMED by --token-env, never from the command line. To get it: pair the second phone
in the app ("Show my pairing code"), then read it from the debug log or from the server's trusted_contacts row. The token and the key are
never printed (the token is shown as its last 6 characters).

Exit code 0 only if every requested check passed. Not run against Firebase yet: no project or credentials exist in this repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from app.alerts import fcm_client  # noqa: E402

ENV_CREDENTIALS = "SATARK_FIREBASE_CREDENTIALS_JSON"
EXPECTED_PACKAGE = "com.satark.app"


def load_credentials(path: Path | None, environ=os.environ) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8")
    value = environ.get(ENV_CREDENTIALS, "")
    if not value.strip():
        raise ValueError(f"give --credentials FILE or set {ENV_CREDENTIALS}")
    return value


def project_of(credentials_text: str) -> str:
    """The project_id inside the service-account JSON (not a secret), or '' if the value is a path."""
    text = credentials_text.strip()
    if text.startswith("{"):
        return str(json.loads(text).get("project_id", ""))
    return str(json.loads(Path(text).read_text(encoding="utf-8")).get("project_id", ""))


def google_services_problems(path: Path, server_project: str) -> list[str]:
    """The app's google-services.json must be for our package and the SAME project the server's key belongs to."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"cannot read {path} as JSON"]
    problems = []
    app_project = str((data.get("project_info") or {}).get("project_id", ""))
    if not app_project:
        problems.append("google-services.json has no project_info.project_id")
    elif server_project and app_project != server_project:
        problems.append(f"the app is registered with Firebase project '{app_project}' but the server's key is for '{server_project}': "
                        "a token from the app can never be pushed by that key. Use the service account of the SAME project.")
    packages = [(c.get("client_info", {}).get("android_client_info", {}) or {}).get("package_name") for c in data.get("client", [])]
    if EXPECTED_PACKAGE not in packages:
        problems.append(f"google-services.json is not registered for the package {EXPECTED_PACKAGE} (it lists {packages or 'none'})")
    return problems


TOKEN_REJECTED = ("Firebase rejected the token: stale (app reinstalled or data cleared), copied incompletely, or minted by a different "
                  "Firebase project than this key. Get a fresh token and compare the projects with --google-services")


def explain(exc: Exception) -> str:
    """A cause for the error classes Firebase raises, without echoing the message (it can include the token)."""
    name = type(exc).__name__
    hints = {
        "NotFoundError": "the token is stale or was never registered (reinstalled app, cleared data): get a fresh token from the phone",
        "InvalidArgumentError": "the token is malformed or the message was rejected: check the token was copied completely",
        "SenderIdMismatchError": "the token belongs to a different Firebase project than this key: use the service account of the SAME project as app/google-services.json",
        "UnauthenticatedError": "Firebase did not accept the key (revoked, wrong project, or the Cloud Messaging API is disabled for it)",
        "PermissionDeniedError": "the key may not send messages: enable the Firebase Cloud Messaging API and give the account the 'Firebase Cloud Messaging API Admin' role",
        "UnavailableError": "Firebase is unreachable or temporarily down: retry",
    }
    return f"{name}: " + hints.get(name, "see the class name above; the message is withheld because it can contain the token")


def run(args, environ=os.environ) -> int:
    ok = True

    def check(name: str, good: bool, detail: str = "") -> bool:
        nonlocal ok
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
        return good

    try:
        creds = load_credentials(args.credentials, environ)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 2
    print("1. offline checks")
    try:
        fcm_client.check_credentials_json(creds)
    except RuntimeError as exc:
        check("the service-account key loads with the server's own loader", False, str(exc))
        return 1
    project = project_of(creds)
    check("the service-account key loads with the server's own loader", True, f"project '{project}'")
    if args.google_services:
        problems = google_services_problems(args.google_services, project)
        check("app/google-services.json belongs to the same project and package", not problems, "; ".join(problems))
    if not (args.dry_run or args.send):
        print("done (offline only). Add --token-env VAR with --dry-run, then --send, to test delivery.")
        return 0 if ok else 1

    token = environ.get(args.token_env or "", "").strip()
    if not token:
        print(f"FAIL: the environment variable {args.token_env!r} is empty or not set")
        return 2
    import firebase_admin
    from firebase_admin import messaging

    if not firebase_admin._apps:
        firebase_admin.initialize_app(fcm_client._certificate(creds))
    tail = f"...{token[-6:]}"
    if args.dry_run:
        print("2. dry run (Firebase validates, nothing is delivered)")
        try:
            messaging.send(messaging.Message(notification=messaging.Notification(title="Satark push test", body="dry run"), token=token), dry_run=True)
            check(f"Firebase accepts the message for token {tail}", True)
        except Exception as exc:  # noqa: BLE001: every Firebase error class gets the same treatment
            check(f"Firebase accepts the message for token {tail}", False, explain(exc))
    if args.send:
        print("3. real push")
        try:
            fcm_client.FirebaseFcmClient(creds).send(token, "Satark push test", "If you can read this, alerts reach this phone.", {"kind": "push_test"})
            check(f"a notification was sent to token {tail}", True, "look at the phone")
        except fcm_client.FcmTokenInvalid:
            check(f"a notification was sent to token {tail}", False, TOKEN_REJECTED)
        except Exception as exc:  # noqa: BLE001
            check(f"a notification was sent to token {tail}", False, explain(exc))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--credentials", type=Path, help=f"service-account JSON file (default: ${ENV_CREDENTIALS})")
    ap.add_argument("--google-services", type=Path, help="app/google-services.json, to check it is the same project")
    ap.add_argument("--token-env", help="name of the environment variable that holds the phone's FCM token")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--send", action="store_true")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
