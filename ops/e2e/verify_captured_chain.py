#!/usr/bin/env python3
"""Would our server accept this phone? Run a captured attestation chain through the server's own verifier and explain every check.

M1's debug build exports a JSON file (format satark-attestation-export/1; `python app/tools/phone_check.py --build` saves one under
app/build/phone_check/). This tool takes that file and prints, for EACH of the server's checks, what the real chain said and whether it passes,
then the verdict of the server's actual `verify_attestation` (the same code `/auth/device` runs). Unlike the server it does not stop at the first
failure, because with a real phone you want the whole picture in one run.

  python ops/e2e/verify_captured_chain.py app/build/phone_check/attestation_Pixel_8_*.json
  python ops/e2e/verify_captured_chain.py phoneA.json phoneB.json --expected-digests "<release digest>,<debug digest>"
  add --allow-software to see what an emulator chain looks like; --skip-revocation to work offline; --json for machine-readable output

Defaults: roots from server/certs/google_attestation_roots.pem, package com.satark.app, signing digest(s) taken from the export itself (the build
that made it), and Google's live revocation list. To test the RELEASE certificate, pass the release digest with --expected-digests.

Exit code 0 only if every file is accepted. The challenge in a capture is already spent, so it is compared with the one the export recorded
instead of being consumed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

from app.auth import attestation as att  # noqa: E402
from app.auth.revocation import GoogleRevocationList, parse_status, serial_key  # noqa: E402

FORMAT = "satark-attestation-export/1"
DEFAULT_ROOTS = ROOT / "server" / "certs" / "google_attestation_roots.pem"
BOOT = {0: "Verified", 1: "SelfSigned", 2: "Unverified", 3: "Failed"}
LEVEL = {0: "Software", 1: "TEE", 2: "StrongBox"}


def fp(der: bytes) -> str:
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


@dataclass
class Check:
    name: str
    ok: bool | None            # None = informational
    detail: str


@dataclass
class Report:
    source: str
    checks: list[Check] = field(default_factory=list)
    verdict: str = "REJECT"
    code: str = ""
    message: str = ""

    def add(self, name, ok, detail):
        self.checks.append(Check(name, ok, detail))


def _b64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_export(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} file (format is {d.get('format')!r})")
    for k in ("challenge", "public_key", "attestation_chain"):
        if not d.get(k):
            raise ValueError(f"the export has no '{k}'")
    return d


def anchor_of(certs, roots):
    """The pinned root the chain ends at (equal to the top certificate, or directly issuing it), or None."""
    top = certs[-1]
    for r in roots:
        if top == r:
            return r
        try:
            top.verify_directly_issued_by(r)
            return r
        except Exception:
            continue
    return None


def diagnose(export: dict, source: str, roots, expected_package: str, expected_digests: frozenset[str], revoked_serials: frozenset[str] | None,
             allow_software: bool) -> Report:
    rep = Report(source)
    dev = export.get("device", {})
    rep.add("Phone", None, f"{dev.get('manufacturer', '?')} {dev.get('model', '?')}, Android {dev.get('release', '?')} "
                           f"(SDK {dev.get('sdk_int', '?')}), security patch {dev.get('security_patch', '?')}, "
                           f"StrongBox feature: {dev.get('strongbox_feature', '?')}; build {export.get('app', {}).get('build_type', '?')}")
    try:
        chain_der = [_b64(c) for c in export["attestation_chain"]]
        spki = _b64(export["public_key"])
        challenge = _b64url(export["challenge"])
        certs = att.parse_chain(chain_der)
    except (ValueError, att.AttestationError) as exc:
        rep.add("Parse", False, f"cannot read the chain: {getattr(exc, 'message', exc)}")
        rep.code, rep.message = "malformed_attestation", str(getattr(exc, "message", exc))
        return rep
    leaf = certs[0]
    rep.add("Chain", None, f"{len(certs)} certificates: " + " -> ".join(
        x509.Name.rfc4514_string(c.subject).split(",")[0][:48] or "?" for c in certs))

    # 1. chain signatures, dates, CA flags, anchored at a pinned root
    policy = att.AttestationPolicy(roots=roots, expected_package=expected_package, expected_signing_sha256=expected_digests,
                                   revoked=lambda: revoked_serials or frozenset(), require_hardware=not allow_software)
    try:
        att._verify_chain(certs, policy)
        root = anchor_of(certs, roots)
        rep.add("1  Chain verifies and ends at a pinned Google root", True, f"anchored at {fp(root.public_bytes(Encoding.DER))[:23]}... ({x509.Name.rfc4514_string(root.subject)[:40]})")
    except att.AttestationError as exc:
        top = certs[-1]
        rep.add("1  Chain verifies and ends at a pinned Google root", False,
                f"{exc.code}: {exc.message} The chain's top certificate is {fp(top.public_bytes(Encoding.DER))} "
                f"({x509.Name.rfc4514_string(top.subject)[:50]}); the pinned roots are " + ", ".join(fp(r.public_bytes(Encoding.DER))[:11] + "..." for r in roots))

    # 2. revocation
    if revoked_serials is None:
        rep.add("2  Not revoked", None, "skipped (--skip-revocation)")
    else:
        hit = [hex(c.serial_number) for c in certs if serial_key(c.serial_number) in revoked_serials]
        rep.add("2  Not revoked", not hit, f"{len(revoked_serials)} serials on the list; " + (f"REVOKED: {hit}" if hit else "none of this chain's serials is on it"))

    # 3-7. what the leaf says
    try:
        kd = att.parse_key_description(leaf)
    except att.AttestationError as exc:
        rep.add("KeyDescription", False, f"{exc.code}: {exc.message}")
        kd = None
    if kd is not None:
        same = kd.challenge == challenge
        rep.add("3  Challenge in the certificate equals the one issued", same,
                f"exported challenge source: {export.get('challenge_source', '?')}; " + ("they match" if same else "they DIFFER"))
        lv = min(kd.attestation_security_level, kd.keymaster_security_level)
        ok_level = lv >= att.SecurityLevel.TRUSTED_ENVIRONMENT or allow_software
        rep.add("4  Key is hardware-backed (TEE or StrongBox)", ok_level,
                f"attestation level {LEVEL.get(kd.attestation_security_level, kd.attestation_security_level)}, keymaster level "
                f"{LEVEL.get(kd.keymaster_security_level, kd.keymaster_security_level)}; the app reports '{export.get('key_security_level', '?')}'"
                + ("" if lv >= 1 else "  <- an emulator or a phone without secure hardware looks like this"))
        boot = BOOT.get(kd.verified_boot_state, "not reported" if kd.verified_boot_state is None else str(kd.verified_boot_state))
        rep.add("5  Verified boot state (recorded, never a rejection)", None, f"{boot}" + ("" if boot == "Verified" else "  -> the server stores unverified_boot for this device"))
        pk_ok = kd.package_names == (expected_package,)
        rep.add("6a App package is exactly ours", pk_ok, f"package(s) in the attestation: {list(kd.package_names)}; expected {expected_package}")
        dg_ok = bool(kd.signing_digests & expected_digests) and kd.signing_digests <= expected_digests
        rep.add("6b App signing certificate is one we expect", dg_ok,
                f"attested digest(s): {sorted(d[:16] + '...' for d in kd.signing_digests)}; expected {sorted(d[:16] + '...' for d in expected_digests)}"
                + ("" if dg_ok else "  <- add this build's digest to SATARK_AUTH_EXPECTED_SIGNING_SHA256 (debug build) or use the release build"))
    leaf_spki = leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    rep.add("7  Certificate key equals the key the app registers", leaf_spki == spki, "match" if leaf_spki == spki else "the exported public key is NOT the attested key")

    # The truth: the server's own function.
    try:
        res = att.verify_attestation(chain_der, spki, challenge, policy)
        rep.verdict, rep.code = "ACCEPT", ""
        rep.message = f"level {res.security_level.name}, boot {BOOT.get(res.verified_boot_state, 'unknown')}, unverified_boot={res.unverified_boot}"
    except att.AttestationError as exc:
        rep.verdict, rep.code, rep.message = "REJECT", exc.code, exc.message
    return rep


def render(rep: Report) -> str:
    lines = [f"=== {rep.source}"]
    for c in rep.checks:
        mark = "info" if c.ok is None else ("PASS" if c.ok else "FAIL")
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    lines.append(f"  --> SERVER VERDICT: {rep.verdict}" + (f" ({rep.code}: {rep.message})" if rep.verdict == "REJECT" else f" ({rep.message})"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--roots", type=Path, default=DEFAULT_ROOTS)
    ap.add_argument("--package", default="com.satark.app")
    ap.add_argument("--expected-digests", help="comma-separated signing digests (default: the digest(s) recorded in each export)")
    ap.add_argument("--allow-software", action="store_true", help="do not require TEE/StrongBox (to inspect an emulator chain)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--skip-revocation", action="store_true")
    g.add_argument("--revocation-file", type=Path, help="a saved copy of Google's status list instead of fetching it")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        roots = att.load_roots_pem(a.roots.read_bytes())
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot load the pinned roots from {a.roots}: {exc}")
        return 2
    if a.skip_revocation:
        revoked = None
    elif a.revocation_file:
        revoked = parse_status(json.loads(a.revocation_file.read_text(encoding="utf-8")))
    else:
        try:
            revoked = GoogleRevocationList()()
        except Exception as exc:  # the server fails closed here, so say so plainly
            print(f"FAIL: could not fetch Google's revocation list ({getattr(exc, 'message', exc)}). The server fails closed without it; use --skip-revocation to continue offline.")
            return 2

    reports, all_ok = [], True
    for f in a.files:
        try:
            export = load_export(f)
        except (OSError, ValueError) as exc:
            print(f"FAIL: {f}: {exc}")
            all_ok = False
            continue
        if a.expected_digests:
            digests = frozenset(d.strip().lower() for d in a.expected_digests.split(",") if d.strip())
        else:
            raw = export.get("app", {}).get("signing_cert_sha256") or []
            digests = frozenset(d.replace(":", "").lower() for d in (raw if isinstance(raw, list) else [raw]))
        rep = diagnose(export, str(f), roots, a.package, digests, revoked, a.allow_software)
        reports.append(rep)
        all_ok &= rep.verdict == "ACCEPT"
    if a.json:
        print(json.dumps([{"source": r.source, "verdict": r.verdict, "code": r.code, "message": r.message,
                           "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in r.checks]} for r in reports], indent=2))
    else:
        print("\n\n".join(render(r) for r in reports))
        if len(reports) > 1:
            print("\nSummary: " + ", ".join(f"{Path(r.source).name}: {r.verdict}" for r in reports))
    return 0 if all_ok and reports else 1


if __name__ == "__main__":
    sys.exit(main())
