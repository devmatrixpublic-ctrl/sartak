#!/usr/bin/env python3
"""Fetch Google's Android Key Attestation roots from TWO official sources, cross-check them, and write a CANDIDATE bundle.

This does not decide what to trust. The server reads only server/certs/google_attestation_roots.pem; this tool writes
server/certs/CANDIDATE_google_attestation_roots.pem, which nothing reads. M4 compares the printed SHA-256 fingerprints with
Google's documentation page in a browser, deletes anything they do not want to pin, and renames the file.

Sources
  api   https://android.googleapis.com/attestation/root                                  (JSON array of PEM strings)
  docs  https://developer.android.com/privacy-and-security/security-key-attestation       (PEM blocks in the page)

Rules for the candidate bundle: a root must appear in BOTH sources and not be expired. Roots in only one source, or expired, are listed
with the reason and left out (pass --include-docs-only to add non-expired roots that only the documentation lists).

Usage (repo root):  python ops/security/attestation_roots.py [--write] [--include-docs-only]
"""
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import html
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://android.googleapis.com/attestation/root"
DOCS_URL = "https://developer.android.com/privacy-and-security/security-key-attestation"
CANDIDATE = ROOT / "server" / "certs" / "CANDIDATE_google_attestation_roots.pem"
PEM = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


@dataclass(frozen=True)
class Root:
    sha256: str          # of the DER, lowercase hex
    subject: str
    not_after: datetime.datetime
    pem: str

    def expired(self, now: datetime.datetime) -> bool:
        return self.not_after <= now

    @property
    def fingerprint(self) -> str:
        return ":".join(self.sha256[i:i + 2].upper() for i in range(0, 64, 2))


def parse_pems(text: str) -> list[Root]:
    from cryptography import x509

    out, seen = [], set()
    for block in PEM.findall(html.unescape(re.sub(r"<[^>]+>", "", text))):
        lines = [l.strip() for l in block.replace("\\n", "\n").splitlines() if l.strip()]
        body = "".join(lines[1:-1])
        der = base64.b64decode(body)
        digest = hashlib.sha256(der).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        cert = x509.load_der_x509_certificate(der)
        pem = "-----BEGIN CERTIFICATE-----\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + "\n-----END CERTIFICATE-----\n"
        out.append(Root(digest, cert.subject.rfc4514_string() or "(no subject)", cert.not_valid_after_utc, pem))
    return out


def parse_api(raw: str) -> list[Root]:
    """The API returns a JSON array of PEM strings (with escaped newlines)."""
    items = json.loads(raw)
    return parse_pems("\n".join(items if isinstance(items, list) else []))


def classify(api: list[Root], docs: list[Root], now: datetime.datetime, include_docs_only: bool = False):
    """-> (candidates, notes). A candidate is in both sources and unexpired (or docs-only and unexpired, if asked)."""
    in_api, in_docs = {r.sha256: r for r in api}, {r.sha256: r for r in docs}
    cands, notes = [], []
    for digest, r in {**in_docs, **in_api}.items():
        both = digest in in_api and digest in in_docs
        if r.expired(now):
            notes.append((r, "EXCLUDED: expired"))
        elif both:
            cands.append(r)
            notes.append((r, "candidate: in both sources"))
        elif include_docs_only and digest in in_docs:
            cands.append(r)
            notes.append((r, "candidate: documentation only (--include-docs-only); verify by hand"))
        else:
            notes.append((r, f"EXCLUDED: only in {'the API' if digest in in_api else 'the documentation page'}"))
    return cands, notes


def fetch(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "satark-roots-check"}), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help=f"write {CANDIDATE.relative_to(ROOT)}")
    ap.add_argument("--include-docs-only", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.datetime.now(datetime.timezone.utc)
    api, docs = parse_api(fetch(API_URL)), parse_pems(fetch(DOCS_URL))
    cands, notes = classify(api, docs, now, a.include_docs_only)
    print(f"API: {len(api)} root(s); documentation page: {len(docs)} root(s); checked {now:%Y-%m-%d}\n")
    for r, why in notes:
        print(f"{r.fingerprint}\n   {r.subject}  not after {r.not_after:%Y-%m-%d}\n   {why}")
    if not cands:
        print("\nNo candidate roots: do not proceed.")
        return 1
    print("\nNext: compare each fingerprint above with the documentation page IN A BROWSER, then keep only the roots you trust.")
    if a.write:
        CANDIDATE.write_text("".join(r.pem for r in cands))
        print(f"wrote {CANDIDATE.relative_to(ROOT)} ({len(cands)} root(s)). The server does not read this file; rename it to "
              "google_attestation_roots.pem only after verifying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
