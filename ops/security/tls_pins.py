"""TLS check and certificate pin generator (plan 4.5; produces contracts/pins.txt for M1).

  python ops/security/tls_pins.py --host satark-server.onrender.com
  python ops/security/tls_pins.py --host satark-server.onrender.com --write contracts/pins.txt

Checks: the certificate chain verifies for the hostname, TLS >= 1.2, the leaf is not about to expire,
and (optionally) the server sends HSTS. Pins are OkHttp-style `sha256/<base64 SHA-256 of the SPKI>`.
A pin file needs a PRIMARY (leaf) and a BACKUP (an intermediate or root, which survives leaf rotation);
with fewer than two distinct pins we refuse to write one, because a single pin bricks the app on
the next certificate renewal.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import socket
import ssl
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

MIN_DAYS_LEFT = 14
# Reading the full chain needs SSLSocket.get_verified_chain(), public since Python 3.13. Without it only the
# leaf is visible, so we can show its pin but cannot produce the backup pin a pin file requires.
CHAIN_API = hasattr(ssl.SSLSocket, "get_verified_chain")


@dataclass
class TlsReport:
    host: str
    tls_version: str = ""
    chain_der: list[bytes] = field(default_factory=list)
    days_left: float = 0.0
    hsts: bool | None = None
    problems: list[str] = field(default_factory=list)


def spki_pin(cert_der: bytes) -> str:
    cert = x509.load_der_x509_certificate(cert_der)
    spki = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return "sha256/" + base64.b64encode(hashlib.sha256(spki).digest()).decode()


def fetch(host: str, port: int = 443, cafile: str | None = None, timeout: float = 10.0,
          check_hsts: bool = True) -> TlsReport:
    rep = TlsReport(host)
    ctx = ssl.create_default_context(cafile=cafile)        # verifies chain and hostname
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                rep.tls_version = tls.version() or ""
                get_chain = getattr(tls, "get_verified_chain", None)
                rep.chain_der = [ssl.PEM_cert_to_DER_cert(c) if isinstance(c, str) else c
                                 for c in get_chain()] if get_chain else []
                if not rep.chain_der:
                    rep.chain_der = [tls.getpeercert(binary_form=True)]
                if check_hsts:
                    tls.sendall(f"GET /health HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
                    head = b""
                    while b"\r\n\r\n" not in head and len(head) < 16384:
                        chunk = tls.recv(4096)
                        if not chunk:
                            break
                        head += chunk
                    rep.hsts = b"strict-transport-security" in head.lower()
    except (ssl.SSLError, OSError) as exc:
        rep.problems.append(f"TLS connection failed: {exc}")
        return rep
    if not CHAIN_API:
        rep.problems.append(f"full chain unavailable on Python {sys.version_info.major}.{sys.version_info.minor} "
                            "(needs 3.13+); only the leaf pin can be computed (warning)")
    leaf = x509.load_der_x509_certificate(rep.chain_der[0])
    rep.days_left = (leaf.not_valid_after_utc - datetime.now(timezone.utc)).total_seconds() / 86400
    if rep.days_left < MIN_DAYS_LEFT:
        rep.problems.append(f"leaf certificate expires in {rep.days_left:.0f} days (< {MIN_DAYS_LEFT})")
    if rep.hsts is False:
        rep.problems.append("no Strict-Transport-Security header on /health (warning)")
    return rep


def pins_for(rep: TlsReport) -> list[str]:
    seen, out = set(), []
    for der in rep.chain_der:
        p = spki_pin(der)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


SHORT_LIVED_DAYS = 100        # certificates valid for about 90 days are renewed automatically, often with a NEW key


@dataclass
class PinInfo:
    pin: str
    role: str                 # "leaf", "intermediate" or "root"
    subject: str
    issuer: str
    not_after: datetime
    validity_days: int


def _cn(name: x509.Name) -> str:
    cn = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return cn[0].value if cn else name.rfc4514_string()[:60]


def describe_pins(rep: "TlsReport") -> list[PinInfo]:
    """One entry per DISTINCT pin, in chain order, saying which certificate it came from."""
    out, seen = [], set()
    for i, der in enumerate(rep.chain_der):
        pin = spki_pin(der)
        if pin in seen:
            continue
        seen.add(pin)
        c = x509.load_der_x509_certificate(der)
        self_signed = c.subject == c.issuer
        role = "leaf" if i == 0 else ("root" if self_signed else "intermediate")
        out.append(PinInfo(pin, role, _cn(c.subject), _cn(c.issuer), c.not_valid_after_utc,
                           (c.not_valid_after_utc - c.not_valid_before_utc).days))
    return out


def advice(infos: list[PinInfo]) -> list[str]:
    """Plain-language warnings derived from the real certificates, not from assumptions about the host."""
    notes = []
    leaf = next((i for i in infos if i.role == "leaf"), None)
    if leaf and leaf.validity_days <= SHORT_LIVED_DAYS:
        notes.append(f"the leaf certificate is valid for only {leaf.validity_days} days, so it is renewed automatically and often with a NEW key: "
                     "the leaf pin may stop matching at the next renewal, and the intermediate backup pin is the one that keeps the app connecting")
    if not any(i.role in ("intermediate", "root") for i in infos):
        notes.append("no intermediate or root certificate was visible, so there is no stable backup pin")
    return notes


def render_pins(host: str, pins: list[str], infos: list[PinInfo] | None = None) -> str:
    if len(pins) < 2:
        raise ValueError("need at least two distinct pins (leaf + a backup in the chain) to write a pin file; "
                         "on Python < 3.13 only the leaf is visible, so run this with Python 3.13 or newer")
    lines = [f"# Certificate pins for {host}, generated by ops/security/tls_pins.py (M4).",
             "# First = leaf (primary). The rest are intermediates/roots kept as backups for leaf rotation.",
             "# Regenerate and re-ship the app BEFORE the issuing intermediate changes."]
    by_pin = {i.pin: i for i in infos or []}
    for n, p in enumerate(pins):
        info = by_pin.get(p)
        detail = f" {info.role} {info.subject}, issued by {info.issuer}, expires {info.not_after.date()}" if info else ""
        lines.append(f"{p}  # {'primary' if n == 0 else 'backup'}{detail}")
    for note in (advice(infos) if infos else []):
        lines.append(f"# NOTE: {note}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--cafile", help="extra CA bundle (tests / private CAs)")
    ap.add_argument("--write", help="write a pin file here (refuses with fewer than two pins)")
    a = ap.parse_args(argv)
    rep = fetch(a.host, a.port, a.cafile)
    print(f"{a.host}: {rep.tls_version or 'no TLS'}, {len(rep.chain_der)} cert(s) in chain, {rep.days_left:.0f} days left")
    hard = [p for p in rep.problems if "warning" not in p]
    for p in rep.problems:
        print(("WARN " if "warning" in p else "FAIL ") + p)
    if hard or not rep.chain_der:
        return 1
    pins = pins_for(rep)
    infos = describe_pins(rep)
    for i in infos:
        print(f"{i.pin}\n    {i.role}: {i.subject} (issued by {i.issuer}), expires {i.not_after.date()}, valid {i.validity_days} days in total")
    for note in advice(infos):
        print(f"WARN {note}")
    if a.write:
        try:
            text = render_pins(a.host, pins, infos)
        except ValueError as exc:
            print(f"FAIL {exc}")
            return 1
        with open(a.write, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {a.write}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
