"""Postgres-only integration tests (CI service container; skipped without SATARK_TEST_POSTGRES_URL).

1. ops/security/db_roles.sql, run for real: the app role can read and write but cannot create, drop, alter,
   truncate, or read migration bookkeeping.
2. The full auth flow through the real routers on Postgres: register, spend a payment, IDOR, refresh rotation,
   replay revokes the device.
"""
import os
import secrets
from pathlib import Path

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.attestation import AttestationPolicy
from app.auth.dependencies import get_auth_service
from app.auth.ratelimit import InMemoryRateLimiter
from app.auth.service import AuthService
from app.auth.store import SqlAuthStore
from app.core.settings import Settings
from app.db.session import get_db
from app.main import app

from .attestation_fixtures import DIGEST, PACKAGE, make_chain
from .test_it_stores import PG_URL, needs_pg, pg_migrated  # noqa: F401  (fixture re-export)
from .test_m4_auth import RISK_BODY, bearer, register

ROOT = Path(__file__).resolve().parents[2]
ROLES_SQL = ROOT / "ops" / "security" / "db_roles.sql"

DROP_ROLE = """
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'satark_app') THEN
    DROP OWNED BY satark_app;
    DROP ROLE satark_app;
  END IF;
END $$;
"""


def _denied(exc_info) -> bool:
    text = str(exc_info.value).lower()
    return "permission denied" in text or "must be owner" in text


@needs_pg
def test_least_privilege_role_can_do_dml_but_no_ddl(pg_migrated):  # noqa: F811
    password = secrets.token_hex(16)
    owner = create_engine(pg_migrated)
    with owner.begin() as c:
        c.exec_driver_sql(DROP_ROLE)
    try:
        with owner.begin() as c:
            c.exec_driver_sql(ROLES_SQL.read_text(encoding="utf-8").replace("REPLACE_WITH_A_GENERATED_PASSWORD", password))
        app_url = sa.engine.make_url(pg_migrated).set(username="satark_app", password=password)
        runtime = create_engine(app_url)

        # data access works
        with runtime.begin() as c:
            c.execute(sa.text("INSERT INTO devices (id, public_key, attestation_level, verified_boot_state, role, revoked, created_at) "
                              "VALUES ('role-it-1', 'pk-role-it-1', 'TEE', 'verified', 'device', false, now())"))
            assert c.execute(sa.text("SELECT count(*) FROM devices WHERE id = 'role-it-1'")).scalar() == 1
            c.execute(sa.text("UPDATE devices SET revoked = true WHERE id = 'role-it-1'"))
            c.execute(sa.text("DELETE FROM devices WHERE id = 'role-it-1'"))

        # schema changes and bookkeeping are off limits
        for statement in ("CREATE TABLE it_forbidden (id int)",
                          "DROP TABLE payments",
                          "ALTER TABLE devices ADD COLUMN it_forbidden int",
                          "TRUNCATE payments",
                          "SELECT * FROM alembic_version"):
            with runtime.connect() as c:
                with pytest.raises(sa.exc.DBAPIError) as exc:
                    c.execute(sa.text(statement))
                assert _denied(exc), f"{statement!r} failed for the wrong reason: {exc.value}"

        # tables created by a later migration (run as the owner) are covered by the default privileges
        with owner.begin() as c:
            c.execute(sa.text("CREATE TABLE it_future (id int)"))
        try:
            with runtime.begin() as c:
                c.execute(sa.text("SELECT count(*) FROM it_future"))
        finally:
            with owner.begin() as c:
                c.execute(sa.text("DROP TABLE it_future"))
        runtime.dispose()
    finally:
        with owner.begin() as c:
            c.exec_driver_sql(DROP_ROLE)
        owner.dispose()


@pytest.fixture
def pg_env(pg_migrated):  # noqa: F811
    engine = create_engine(pg_migrated, pool_size=10, max_overflow=10)
    factory = sessionmaker(bind=engine, future=True)
    root_key = ec.generate_private_key(ec.SECP256R1())
    settings = Settings(env="dev", jwt_secret="s" * 48, auth_expected_package=PACKAGE,
                        auth_expected_signing_sha256=DIGEST.hex())
    policy = AttestationPolicy(roots=[make_chain(b"\x00" * 32, root_key=root_key).root], expected_package=PACKAGE,
                               expected_signing_sha256=frozenset({DIGEST.hex()}), revoked=lambda: frozenset(),
                               require_hardware=True)
    limiter = InMemoryRateLimiter()

    def _db():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    def _svc(db: Session = Depends(_db)):
        return AuthService(settings, SqlAuthStore(db), limiter, policy)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_auth_service] = _svc
    yield {"client": TestClient(app), "root_key": root_key, "session_factory": factory}
    app.dependency_overrides.clear()
    engine.dispose()


@needs_pg
def test_full_auth_flow_on_postgres(pg_env):
    client = pg_env["client"]
    a, _ = register(pg_env)
    b, _ = register(pg_env)
    assert a.status_code == 200 and b.status_code == 200
    a, b = a.json(), b.json()
    assert a["device_id"] != b["device_id"] and len(a["device_id"]) == 36

    pay = client.post("/risk-check", json=RISK_BODY, headers=bearer(a["access_token"]))
    assert pay.status_code == 200 and pay.json()["decision"] == "ALLOW"          # FK-backed payment row on Postgres
    pid = pay.json()["payment_id"]
    assert client.get(f"/payments/{pid}", headers=bearer(a["access_token"])).status_code == 200
    assert client.get(f"/payments/{pid}", headers=bearer(b["access_token"])).status_code == 404       # IDOR

    rotated = client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert rotated.status_code == 200
    replay = client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_reuse"
    dead = client.post("/risk-check", json=RISK_BODY, headers=bearer(rotated.json()["access_token"]))
    assert dead.status_code == 401 and dead.json()["code"] == "invalid_token"      # revocation is immediate
    assert client.post("/risk-check", json=RISK_BODY, headers=bearer(b["access_token"])).status_code == 200  # others unaffected


@needs_pg
def test_challenge_cannot_be_replayed_on_postgres(pg_env):
    ok, body = register(pg_env)
    assert ok.status_code == 200
    again = pg_env["client"].post("/auth/device", json=body)
    assert again.status_code == 400 and again.json()["code"] == "challenge_invalid"
