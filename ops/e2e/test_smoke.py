"""Proves smoke_deployed.py itself: it passes against a PRODUCTION-configured local server and FAILS against a dev server, so its
checks are not vacuous. Opt-in (starts real servers): RUN_E2E=1 pytest ops/e2e/test_smoke.py"""
import datetime
import importlib.util
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("smoke_deployed.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

pytestmark = pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 (starts real servers, about 20 s)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _throwaway_root(path: Path) -> None:
    """A self-signed certificate that only lets the production-mode server BOOT in this test. It is not a trust decision."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "satark smoke-test throwaway root")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _serve(tmp: Path, **extra):
    env = {**os.environ, "SATARK_DATABASE_URL": f"sqlite:///{tmp / 's.db'}", "SATARK_REDIS_URL": "redis://127.0.0.1:1/0",
           "SATARK_RATE_LIMIT_PER_MINUTE": "1000", **extra}
    mig = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=SERVER, env=env, capture_output=True, text=True)
    assert mig.returncode == 0, mig.stderr[-400:]
    port = _free_port()
    log = open(tmp / f"server-{port}.log", "wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=SERVER, env=env, stdout=log, stderr=log)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            return proc, f"http://127.0.0.1:{port}"
        except Exception:
            time.sleep(0.25)
    proc.kill()
    pytest.fail((tmp / f"server-{port}.log").read_text()[-600:])


def test_smoke_passes_on_a_production_configured_server_and_fails_on_a_dev_server(tmp_path):
    roots = tmp_path / "roots.pem"
    _throwaway_root(roots)
    prod, url = _serve(tmp_path, SATARK_ENV="production", SATARK_JWT_SECRET=secrets.token_urlsafe(48),
                       SATARK_AUTH_ATTESTATION_ROOTS=str(roots), SATARK_AUTH_EXPECTED_PACKAGE="com.satark.app",
                       SATARK_AUTH_EXPECTED_SIGNING_SHA256="ab" * 32)
    try:
        res = smoke.run(url, allow_http=True)
        failed = [(n, d) for n, ok, d in res if not ok]
        assert not failed, failed
        assert len(res) >= 14
    finally:
        prod.terminate()
        prod.wait(10)

    dev, url = _serve(tmp_path, SATARK_ENV="dev", SATARK_AUTH_ENABLE_DEV_TOKEN="1")
    try:
        names = {n for n, ok, _ in smoke.run(url, allow_http=True) if not ok}
    finally:
        dev.terminate()
        dev.wait(10)
    assert "dev-token stub is off (404)" in names                                  # a dev server is caught, not waved through
    assert any("/docs" in n for n in names)
