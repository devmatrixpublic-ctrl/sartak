import base64
import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

spec = importlib.util.spec_from_file_location("roots", Path(__file__).with_name("attestation_roots.py"))
roots = importlib.util.module_from_spec(spec)
sys.modules["roots"] = roots                      # dataclasses look their module up here
spec.loader.exec_module(roots)
NOW = datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc)


def make_pem(cn: str, days: int) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    start = NOW - datetime.timedelta(days=400)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(start).not_valid_after(NOW + datetime.timedelta(days=days))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope="module")
def pems():
    return {"valid_both": make_pem("both", 3000), "expired": make_pem("expired", -10), "api_only": make_pem("api-only", 3000),
            "docs_only": make_pem("docs-only", 3000)}


def test_parses_the_api_json_with_escaped_newlines_and_the_html_page(pems):
    api = roots.parse_api(json.dumps([pems["valid_both"].replace("\n", "\n"), pems["api_only"]]))
    assert len(api) == 2 and all(len(r.sha256) == 64 for r in api)
    page = "<html><pre>" + pems["valid_both"].replace("\n", "<br>\n") + "</pre><p>" + pems["docs_only"] + "</p></html>"
    docs = roots.parse_pems(page)
    assert len(docs) == 2
    assert {r.sha256 for r in api} & {r.sha256 for r in docs}                      # the shared certificate has the same fingerprint


def test_fingerprint_is_the_sha256_of_the_der(pems):
    import hashlib
    r = roots.parse_pems(pems["valid_both"])[0]
    der = base64.b64decode("".join(pems["valid_both"].splitlines()[1:-1]))
    assert r.sha256 == hashlib.sha256(der).hexdigest() and r.fingerprint.count(":") == 31


def test_only_roots_in_both_sources_and_unexpired_become_candidates(pems):
    api = roots.parse_api(json.dumps([pems["valid_both"], pems["api_only"], pems["expired"]]))
    docs = roots.parse_pems(pems["valid_both"] + pems["expired"] + pems["docs_only"])
    cands, notes = roots.classify(api, docs, NOW)
    assert [c.subject for c in cands] == ["CN=both"]
    why = {r.subject: w for r, w in notes}
    assert "expired" in why["CN=expired"] and "only in the API" in why["CN=api-only"] and "only in the documentation" in why["CN=docs-only"]


def test_docs_only_roots_are_added_only_on_request_and_expired_never(pems):
    api = roots.parse_api(json.dumps([pems["valid_both"]]))
    docs = roots.parse_pems(pems["valid_both"] + pems["docs_only"] + pems["expired"])
    cands, _ = roots.classify(api, docs, NOW, include_docs_only=True)
    assert sorted(c.subject for c in cands) == ["CN=both", "CN=docs-only"]


def test_the_server_does_not_read_the_candidate_file_name():
    assert roots.CANDIDATE.name != "google_attestation_roots.pem"
    assert "CANDIDATE" in roots.CANDIDATE.name
