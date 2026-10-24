#!/usr/bin/env python3
"""Check that the built release APK is signed with the certificate the server expects, and not unsigned or debug-signed.

  apksigner verify --print-certs app-release.apk > certs.txt
  python ops/release/check_apk_signature.py --certs certs.txt --expected "<digest>[,<digest>]"
  python ops/release/check_apk_signature.py --find-apk app/build/outputs/apk/release     # prints the single APK to publish

If the APK's signing certificate is not in the list the server was told to expect (SATARK_AUTH_EXPECTED_SIGNING_SHA256), every phone running
this build would be rejected at registration (check 6, app_mismatch). Catching that here is far cheaper than finding it on a phone.
Standard library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import signing_digest as sd  # noqa: E402

SIGNER = re.compile(r"Signer\s*#\d+\s+certificate SHA-256 digest:\s*([0-9a-fA-F:]+)")


def signer_digests(apksigner_output: str) -> list[str]:
    """Signing-certificate digests (lowercase hex, no colons) from `apksigner verify --print-certs`."""
    return [sd.normalise(m) for m in SIGNER.findall(apksigner_output)]


def check(apksigner_output: str, expected: str) -> list[str]:
    """Problems with the signature, or an empty list. Every signer must be one the server expects, and there must be at least one."""
    problems: list[str] = []
    try:
        want = set(sd.check_list(expected))
    except ValueError as exc:
        return [f"expected digest list is invalid: {exc}"]
    got = signer_digests(apksigner_output)
    if not got:
        return ["the APK has no signing certificate (it is unsigned: was the keystore passed to the build?)"]
    for d in got:
        if d not in want:
            problems.append(f"the APK is signed with {d[:16]}..., which is NOT in the expected list: the server would reject every phone running this build "
                            "(wrong keystore, or a debug-signed build)")
    return problems


def find_apk(directory: Path) -> Path:
    apks = sorted(directory.glob("*.apk"))
    if not apks:
        raise FileNotFoundError(f"no APK in {directory}")
    if len(apks) > 1:
        raise ValueError(f"expected exactly one APK in {directory}, found: {[a.name for a in apks]}")
    if "unsigned" in apks[0].name.lower():
        raise ValueError(f"{apks[0].name} is unsigned: the build did not receive the signing configuration")
    return apks[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--certs", type=Path, help="saved output of apksigner verify --print-certs")
    g.add_argument("--find-apk", type=Path, metavar="DIR")
    ap.add_argument("--expected", help="comma-separated signing digests (required with --certs)")
    a = ap.parse_args(argv)
    try:
        if a.find_apk:
            print(find_apk(a.find_apk))
            return 0
        if not a.expected:
            print("FAIL: --expected is required with --certs")
            return 2
        found = check(a.certs.read_text(encoding="utf-8", errors="replace"), a.expected)
    except (OSError, ValueError) as exc:
        print(f"::error::{exc}")
        return 1
    if found:
        for p in found:
            print(f"::error::{p}")
        return 1
    print("APK signature OK: signed by the expected certificate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
