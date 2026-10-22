import datetime as dt
import socket
import ssl
import sys
import threading
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).parent))

import tls_pins as tp  # noqa: E402


def make_cert(cn, issuer_name, issuer_key, key, *, ca, days=365, san=None):
    now = dt.datetime.now(dt.timezone.utc)
    b = (x509.CertificateBuilder()
         .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
         .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
         .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
         .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False))
    if ca:
        b = b.add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                          key_encipherment=False, data_encipherment=False, key_agreement=False,
                                          encipher_only=False, decipher_only=False), critical=True)
    if san:
        b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    return b.sign(issuer_key, hashes.SHA256())


@pytest.fixture
def tls_server(tmp_path):
    """A real local TLS server: root CA -> intermediate -> leaf for 'localhost'."""
    def build(leaf_days=365, hsts=True):
        root_k, int_k, leaf_k = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
        root = make_cert("Test Root", "Test Root", root_k, root_k, ca=True)
        inter = make_cert("Test Inter", "Test Root", root_k, int_k, ca=True)
        leaf = make_cert("localhost", "Test Inter", int_k, leaf_k, ca=False, days=leaf_days, san="localhost")
        chain = tmp_path / "chain.pem"
        chain.write_bytes(leaf.public_bytes(Encoding.PEM) + inter.public_bytes(Encoding.PEM))
        key = tmp_path / "key.pem"
        key.write_bytes(leaf_k.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        ca = tmp_path / "ca.pem"
        ca.write_bytes(root.public_bytes(Encoding.PEM))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(chain, key)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)

        def serve():
            try:
                conn, _ = srv.accept()
                with ctx.wrap_socket(conn, server_side=True) as s:
                    s.recv(4096)
                    extra = "Strict-Transport-Security: max-age=31536000\r\n" if hsts else ""
                    s.sendall(f"HTTP/1.1 200 OK\r\n{extra}Content-Length: 2\r\nConnection: close\r\n\r\nok".encode())
            except (ssl.SSLError, OSError):
                pass
            finally:
                srv.close()

        threading.Thread(target=serve, daemon=True).start()
        return srv.getsockname()[1], str(ca), (leaf, inter, root)

    return build


needs_chain = pytest.mark.skipif(not tp.CHAIN_API, reason="reading the full chain needs Python 3.13+ (CI runs the tls-tool job on 3.13)")


@needs_chain
def test_good_server_passes_and_yields_a_leaf_plus_backup_pin(tls_server):
    port, ca, (leaf, inter, _) = tls_server()
    rep = tp.fetch("localhost", port, cafile=ca)
    assert rep.problems == [] and rep.tls_version in {"TLSv1.2", "TLSv1.3"} and rep.hsts is True
    pins = tp.pins_for(rep)
    assert pins[0] == tp.spki_pin(leaf.public_bytes(Encoding.DER))
    assert tp.spki_pin(inter.public_bytes(Encoding.DER)) in pins and len(pins) >= 2


def test_untrusted_chain_is_a_hard_failure(tls_server):
    port, _, _ = tls_server()
    rep = tp.fetch("localhost", port)                     # system trust store: our test root is not in it
    assert rep.chain_der == [] and "TLS connection failed" in rep.problems[0]


def test_hostname_mismatch_is_a_hard_failure(tls_server):
    port, ca, _ = tls_server()
    rep = tp.fetch("127.0.0.1", port, cafile=ca)          # cert is for 'localhost', not the IP
    assert rep.chain_der == [] and rep.problems


def test_expiring_leaf_is_flagged(tls_server):
    port, ca, _ = tls_server(leaf_days=3)
    rep = tp.fetch("localhost", port, cafile=ca)
    assert any("expires in" in p for p in rep.problems)


def test_missing_hsts_is_only_a_warning(tls_server, capsys):
    port, ca, _ = tls_server(hsts=False)
    assert tp.main(["--host", "localhost", "--port", str(port), "--cafile", ca]) == 0
    assert "WARN" in capsys.readouterr().out


def test_leaf_only_view_is_reported_honestly_when_the_chain_api_is_missing(tls_server, monkeypatch):
    monkeypatch.setattr(tp, "CHAIN_API", False)
    port, ca, _ = tls_server()
    rep = tp.fetch("localhost", port, cafile=ca)
    assert any("full chain unavailable" in p and "warning" in p for p in rep.problems)


def test_pin_file_needs_two_distinct_pins():
    with pytest.raises(ValueError, match="at least two"):
        tp.render_pins("h", ["sha256/a"])
    text = tp.render_pins("h", ["sha256/a", "sha256/b"])
    assert "sha256/a  # primary" in text and "sha256/b  # backup" in text


@needs_chain
def test_cli_writes_a_pin_file(tls_server, tmp_path):
    port, ca, _ = tls_server()
    out = tmp_path / "pins.txt"
    assert tp.main(["--host", "localhost", "--port", str(port), "--cafile", ca, "--write", str(out)]) == 0
    lines = [l for l in out.read_text().splitlines() if l.startswith("sha256/")]
    assert len(lines) >= 2 and lines[0].endswith("# primary")
