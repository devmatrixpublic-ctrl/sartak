#!/usr/bin/env python3
"""The signing-certificate digest the server needs: SHA-256 of the DER of the certificate that signs the release APK.

The server compares it with the `attestationApplicationId` in every phone's attestation (`SATARK_AUTH_EXPECTED_SIGNING_SHA256`, 64 lowercase
hex characters, comma-separated for several). Getting this value wrong by one character means NO phone can register, so this tool derives
it and validates it instead of asking a person to lowercase and strip colons by hand.

  python ops/release/signing_digest.py --keystore satark-release.keystore --alias satark-release
  python ops/release/signing_digest.py --cert signing.pem                      # a PEM or DER certificate
  python ops/release/signing_digest.py --check "abcd...,ef01..."               # validate the value you are about to paste into Render
  add --format env | json   to print SATARK_AUTH_EXPECTED_SIGNING_SHA256=... or JSON

The keystore password is asked for with a hidden prompt (or read from the environment variable named by --storepass-env). It is never
printed, never put on a command line, and never written to disk.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ENV_NAME = "SATARK_AUTH_EXPECTED_SIGNING_SHA256"


def find_keytool(explicit: str | None = None) -> str | None:
    """keytool from --keytool, PATH, JAVA_HOME, or the usual Windows install folders."""
    candidates = [explicit] if explicit else []
    candidates.append(shutil.which("keytool"))
    if os.environ.get("JAVA_HOME"):
        candidates.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / ("keytool.exe" if os.name == "nt" else "keytool")))
    for base in (r"C:\Program Files\Java", r"C:\Program Files (x86)\Java", r"C:\Program Files\Eclipse Adoptium"):
        p = Path(base)
        if p.is_dir():
            candidates += [str(x) for x in sorted(p.glob("*/bin/keytool.exe"))]
    return next((c for c in candidates if c and Path(c).is_file()), None)


def certificate_der(data: bytes) -> bytes:
    """DER bytes of a certificate given as PEM or DER. Raises ValueError if it is neither."""
    # Imported here so the validators in this module (normalise, check_list) work on a bare CI runner with only the standard library.
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    try:
        cert = x509.load_pem_x509_certificate(data) if b"-----BEGIN" in data else x509.load_der_x509_certificate(data)
    except ValueError as exc:
        raise ValueError(f"not a valid X.509 certificate: {exc}") from None
    return cert.public_bytes(Encoding.DER)


def digest_of(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def normalise(value: str) -> str:
    """'AB:CD:...' (keytool style) or any case -> 64 lowercase hex. Raises ValueError if it is not a SHA-256."""
    cleaned = value.strip().replace(":", "").replace(" ", "").lower()
    if not HEX64.match(cleaned):
        raise ValueError(f"not a SHA-256 digest (need 64 hex characters, got {len(cleaned)}): {value[:20]}...")
    return cleaned


def check_list(value: str) -> list[str]:
    """Validate the comma-separated value for Render. Returns the digests; raises ValueError naming the first bad entry.
    Strict on purpose: colons or upper case here would be silently useless, so they are errors, not repaired."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError("empty: the server will not boot without at least one digest")
    for p in parts:
        if not HEX64.match(p):
            hint = " (looks like keytool format: lowercase it and remove the colons)" if re.match(r"^[0-9A-Fa-f:]{95}$", p) else ""
            raise ValueError(f"bad entry '{p[:24]}...': need exactly 64 lowercase hex characters{hint}")
    if len(set(parts)) != len(parts):
        raise ValueError("the same digest is listed twice")
    return parts


def export_from_keystore(keystore: Path, alias: str, keytool: str, password: str) -> bytes:
    """Ask keytool for the certificate (public data). The password goes through the child's environment, not argv."""
    env = dict(os.environ, SATARK_TMP_STOREPASS=password)
    out = subprocess.run([keytool, "-exportcert", "-rfc", "-keystore", str(keystore), "-alias", alias, "-storepass:env", "SATARK_TMP_STOREPASS"],
                         capture_output=True, env=env)
    if out.returncode != 0:
        raise RuntimeError("keytool could not read the certificate (wrong password, alias or file?): "
                           + out.stderr.decode(errors="replace").strip()[:300])
    return out.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--keystore", type=Path)
    src.add_argument("--cert", type=Path)
    src.add_argument("--check", metavar="VALUE", help="validate a comma-separated digest list")
    ap.add_argument("--alias", default="satark-release")
    ap.add_argument("--keytool")
    ap.add_argument("--storepass-env", metavar="VAR", help="read the keystore password from this environment variable")
    ap.add_argument("--format", choices=["hex", "env", "json"], default="hex")
    a = ap.parse_args(argv)

    try:
        if a.check is not None:
            parts = check_list(a.check)
            print(f"OK: {len(parts)} digest(s)" + ("; more than one is only for phone testing, remove debug digests before real use" if len(parts) > 1 else ""))
            return 0
        if a.cert:
            der = certificate_der(a.cert.read_bytes())
        else:
            keytool = find_keytool(a.keytool)
            if not keytool:
                print("FAIL: keytool not found. Install a JDK, or pass --keytool PATH, or use --cert with an exported certificate.")
                return 2
            if not a.keystore.is_file():
                print(f"FAIL: keystore not found: {a.keystore}")
                return 2
            password = os.environ[a.storepass_env] if a.storepass_env and a.storepass_env in os.environ else getpass.getpass("Keystore password (hidden): ")
            der = certificate_der(export_from_keystore(a.keystore, a.alias, keytool, password))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1

    digest = digest_of(der)
    print({"hex": digest, "env": f"{ENV_NAME}={digest}", "json": json.dumps({ENV_NAME: digest})}[a.format])
    return 0


if __name__ == "__main__":
    sys.exit(main())
