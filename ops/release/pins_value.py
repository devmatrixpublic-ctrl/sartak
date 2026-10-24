#!/usr/bin/env python3
"""Turn contracts/pins.txt into the single comma-separated value the Android build wants.

  python ops/release/pins_value.py                    # sha256/AAAA...=,sha256/BBBB...=
  python ops/release/pins_value.py --gradle           # -PsatarkPins=sha256/AAAA...=,sha256/BBBB...=

The same value is what the GitHub variable SATARK_CERT_PINS holds (ops/release/set_github_secrets.py sets it from the same file). It uses the same
validation: every line must be a real pin, and there must be at least two distinct ones, because a single pin locks every installed app out at the
next certificate change.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from set_github_secrets import read_pins  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[2] / "contracts" / "pins.txt"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=DEFAULT)
    ap.add_argument("--gradle", action="store_true", help="print as -PsatarkPins=<value>")
    a = ap.parse_args(argv)
    if not a.file.is_file():
        print(f"FAIL: {a.file} does not exist yet. Generate it once the domain is live: "
              "python ops/security/tls_pins.py --host <domain> --write contracts/pins.txt")
        return 1
    try:
        value = ",".join(read_pins(a.file))
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"-PsatarkPins={value}" if a.gradle else value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
