#!/usr/bin/env python3
"""Refuse to build a release APK with a configuration that would ship something broken or unsafe.

Reads the values from environment variables (the workflow passes repository variables through `env`, never inside the script text):

  SERVER_URL                 https://<service>.onrender.com/    https only, trailing slash, not a local address
  CERT_PINS                  sha256/..=,sha256/..=              at least two valid, distinct pins
  RAZORPAY_KEY_ID            rzp_test_...                       TEST mode only (live mode is out of scope)
  EXPECTED_SIGNING_SHA256    64 lowercase hex, comma-separated  must be exactly what is set on Render
  RELEASE_TAG   (optional)   v1.2.3 or v1.2.3-rc.1

It reports EVERY problem at once (not just the first), so one failed run is enough to fix the configuration.
Standard library only, so it runs on a bare CI runner.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import signing_digest as sd  # noqa: E402  (stdlib-only at import time)

PIN = re.compile(r"^sha256/[A-Za-z0-9+/]{43}=$")
TAG = re.compile(r"^v\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2", "::1"}


def problems(env: Mapping[str, str]) -> list[str]:
    out: list[str] = []

    url = env.get("SERVER_URL", "").strip()
    if not url:
        out.append("SERVER_URL (repository variable SATARK_SERVER_URL) is not set")
    else:
        u = urlparse(url)
        if u.scheme != "https":
            out.append(f"SERVER_URL must start with https:// (got scheme '{u.scheme or 'none'}'): a release must never talk to the server in clear text")
        if not u.hostname or u.hostname in LOCAL_HOSTS or u.hostname.endswith(".local"):
            out.append(f"SERVER_URL points at a local address ({u.hostname}); a release needs the deployed server")
        if not url.endswith("/"):
            out.append("SERVER_URL must end with / (the app builds every request URL from it)")
        if u.query or u.fragment or " " in url:
            out.append("SERVER_URL must be a plain base URL, with no query, fragment or spaces")

    pins_raw = env.get("CERT_PINS", "").strip()
    if not pins_raw:
        out.append("CERT_PINS (SATARK_CERT_PINS) is not set: an empty pin list silently DISABLES certificate pinning in the app")
    else:
        pins = [p.strip() for p in pins_raw.split(",") if p.strip()]
        bad = [p[:20] for p in pins if not PIN.match(p)]
        if bad:
            out.append(f"CERT_PINS has entries that are not pins (sha256/ + 44 base64 characters): {bad}")
        if len(set(pins)) < 2:
            out.append("CERT_PINS needs at least two distinct pins (a primary and a backup): one pin locks every installed app out at the next certificate change")

    key = env.get("RAZORPAY_KEY_ID", "").strip()
    if not key:
        out.append("RAZORPAY_KEY_ID (SATARK_RAZORPAY_KEY_ID) is not set")
    elif "REPLACE" in key.upper() or not key.startswith("rzp_test_"):
        out.append("RAZORPAY_KEY_ID must be a real TEST-mode key id (rzp_test_...), not the placeholder and not a live key")

    digests = env.get("EXPECTED_SIGNING_SHA256", "").strip()
    if not digests:
        out.append("EXPECTED_SIGNING_SHA256 (SATARK_EXPECTED_SIGNING_SHA256) is not set")
    else:
        try:
            sd.check_list(digests)
        except ValueError as exc:
            out.append(f"EXPECTED_SIGNING_SHA256 is invalid: {exc}")

    tag = env.get("RELEASE_TAG", "").strip()
    if tag and not TAG.match(tag):
        out.append(f"RELEASE_TAG '{tag[:30]}' is not a version tag (expected v1.2.3 or v1.2.3-rc.1)")
    return out


def main() -> int:
    found = problems(os.environ)
    if found:
        for p in found:
            print(f"::error::{p}")
        print(f"\n{len(found)} problem(s). Fix the repository variables (see ops/release/README.md) and re-run.")
        return 1
    host = urlparse(os.environ["SERVER_URL"]).hostname
    pins = len([p for p in os.environ["CERT_PINS"].split(",") if p.strip()])
    print(f"release configuration OK: server {host}, {pins} pins, Razorpay test mode, signing digest(s) set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
