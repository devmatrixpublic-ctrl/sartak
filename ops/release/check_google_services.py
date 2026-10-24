#!/usr/bin/env python3
"""Check that app/google-services.json is the Firebase config for THIS app, before it is baked into a release.

A google-services.json from the wrong Firebase project (or for a different package name) still builds, and then push alerts silently never
arrive. So the release workflow runs this right after decoding the secret. It prints no contents, only which check failed.

  python ops/release/check_google_services.py app/google-services.json [--package com.satark.app]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_PACKAGE = "com.satark.app"


def problems(raw: str, package: str = DEFAULT_PACKAGE) -> list[str]:
    try:
        d = json.loads(raw)
    except ValueError:
        return ["the file is not valid JSON (was the secret base64-encoded from the real file?)"]
    if not isinstance(d, dict):
        return ["the top level is not a JSON object"]
    out = []
    info = d.get("project_info") or {}
    if not info.get("project_id"):
        out.append("no project_info.project_id: this does not look like a google-services.json")
    clients = d.get("client") or []
    if not isinstance(clients, list) or not clients:
        return out + ["no client entries: register the Android app in the Firebase console and download the file again"]
    names = [((c.get("client_info") or {}).get("android_client_info") or {}).get("package_name") for c in clients if isinstance(c, dict)]
    if package not in names:
        out.append(f"none of its client entries is for package {package} (it lists {sorted(n for n in names if n)}): "
                   "register this package in Firebase, or the push will never reach the app")
    mine = next((c for c in clients if isinstance(c, dict) and
                 ((c.get("client_info") or {}).get("android_client_info") or {}).get("package_name") == package), None)
    if mine is not None:
        if not (mine.get("client_info") or {}).get("mobilesdk_app_id"):
            out.append("the client entry has no mobilesdk_app_id")
        if not any(k.get("current_key") for k in (mine.get("api_key") or []) if isinstance(k, dict)):
            out.append("the client entry has no API key")
    if not info.get("project_number"):
        out.append("no project_number (the FCM sender id)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--package", default=DEFAULT_PACKAGE)
    a = ap.parse_args(argv)
    try:
        found = problems(a.file.read_text(encoding="utf-8"), a.package)
    except OSError as exc:
        print(f"::error::cannot read {a.file}: {exc}")
        return 1
    if found:
        for p in found:
            print(f"::error::{p}")
        return 1
    print(f"google-services.json OK for {a.package}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
