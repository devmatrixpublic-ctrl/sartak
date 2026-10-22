"""Integration tests for the auth store on real databases.

Runs on SQLite always. Runs on Postgres too when SATARK_TEST_POSTGRES_URL is set (CI provides one through a
service container; the database name must contain "test", because the schema is dropped and recreated).

What these cover that the unit tests cannot: the atomic single-UPDATE guarantees under real concurrency
(challenge consumed once, refresh token used once), timezone-aware expiry against `timestamptz`, and that the
migrations produce exactly the schema the models describe.
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.store import DeviceRecord, RefreshRecord, SqlAuthStore
from app.db.base import Base
from app.db import models  # noqa: F401

SERVER_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("SATARK_TEST_POSTGRES_URL", "")
needs_pg = pytest.mark.skipif(not PG_URL, reason="set SATARK_TEST_POSTGRES_URL to run against Postgres")


def reset_postgres(url: str) -> None:
    db_name = sa.engine.make_url(url).database or ""
    assert "test" in db_name, f"refusing to wipe '{db_name}': the database name must contain 'test'"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text("DROP SCHEMA public CASCADE"))
        c.execute(sa.text("CREATE SCHEMA public"))
    eng.dispose()


def alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SATARK_DATABASE_URL=url, SATARK_MIGRATION_DATABASE_URL=url, SATARK_ENV="dev")
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=SERVER_DIR, env=env,
                          capture_output=True, text=True)


@pytest.fixture(scope="module")
def pg_migrated():
    """A Postgres database migrated from empty with the real Alembic migrations."""
    if not PG_URL:
        pytest.skip("no Postgres")
    reset_postgres(PG_URL)
    out = alembic(PG_URL, "upgrade", "head")
    assert out.returncode == 0, out.stderr[-1500:]
    return PG_URL


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=needs_pg)])
def session_factory_for_db(request, tmp_path):
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{tmp_path / 'it.db'}", connect_args={"check_same_thread": False, "timeout": 30})
        Base.metadata.create_all(eng)
    else:
        request.getfixturevalue("pg_migrated")
        eng = create_engine(PG_URL, pool_size=20, max_overflow=20)
    yield sessionmaker(bind=eng, future=True)
    eng.dispose()


def make_device(factory, device_id="dev-it-1"):
    with factory() as s:
        SqlAuthStore(s).upsert_device(DeviceRecord(device_id, f"pk-{device_id}", "TEE", "verified"))
    return device_id


def run_threads(n, target):
    results, errors = [], []
    barrier = threading.Barrier(n)

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results.append(target(i))
        except Exception as exc:                                   # surfaced by the assertions below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert not errors, errors[:3]
    return results


# --- the atomic guarantees ----------------------------------------------------------------
def test_a_challenge_can_be_consumed_exactly_once_under_concurrency(session_factory_for_db):
    factory = session_factory_for_db
    with factory() as s:
        SqlAuthStore(s).put_challenge("chal-concurrent", time.time() + 120)

    def consume(_):
        with factory() as s:
            return SqlAuthStore(s).consume_challenge("chal-concurrent", time.time())

    results = run_threads(12, consume)
    assert results.count(True) == 1 and results.count(False) == 11


def test_an_expired_challenge_is_never_consumable(session_factory_for_db):
    factory = session_factory_for_db
    with factory() as s:
        store = SqlAuthStore(s)
        store.put_challenge("chal-old", time.time() - 5)
        store.put_challenge("chal-edge", time.time() + 30)
        assert store.consume_challenge("chal-old", time.time()) is False
        assert store.consume_challenge("chal-edge", time.time()) is True          # still valid
        assert store.consume_challenge("chal-edge", time.time() + 31) is False    # used already
        assert store.consume_challenge("chal-never-issued", time.time()) is False


def test_a_refresh_token_is_used_once_and_every_replay_is_flagged(session_factory_for_db):
    factory = session_factory_for_db
    device = make_device(factory)
    with factory() as s:
        SqlAuthStore(s).put_refresh("hash-concurrent", RefreshRecord(device, time.time() + 3600))

    def take(_):
        with factory() as s:
            return SqlAuthStore(s).take_refresh("hash-concurrent")

    results = run_threads(10, take)
    fresh = [r for r in results if r is not None and not r.used]
    replays = [r for r in results if r is not None and r.used]
    assert len(fresh) == 1 and len(replays) == 9, f"fresh={len(fresh)} replays={len(replays)}"


def test_unknown_refresh_token_and_expiry_roundtrip(session_factory_for_db):
    factory = session_factory_for_db
    device = make_device(factory, "dev-it-2")
    expires = time.time() + 1234
    with factory() as s:
        store = SqlAuthStore(s)
        assert store.take_refresh("no-such-hash") is None
        store.put_refresh("hash-x", RefreshRecord(device, expires))
        got = store.take_refresh("hash-x")
        assert abs(got.expires_at - expires) < 1 and got.used is False        # timestamptz round-trips as UTC


def test_revocation_and_reattestation_roundtrip(session_factory_for_db):
    factory = session_factory_for_db
    device = make_device(factory, "dev-it-3")
    with factory() as s:
        store = SqlAuthStore(s)
        store.revoke_device(device)
        assert store.get_device(device).revoked is True
        again = store.upsert_device(DeviceRecord(device, "pk-new", "StrongBox", "verified"))
        assert again.revoked is False and again.attestation_level == "StrongBox" and again.role == "device"


# --- migrations on real Postgres ----------------------------------------------------------
@needs_pg
def test_migrations_match_the_models_on_postgres(pg_migrated):
    out = alembic(pg_migrated, "check")
    assert out.returncode == 0 and "No new upgrade operations detected" in (out.stdout + out.stderr), out.stderr[-800:]


@needs_pg
def test_latest_migration_downgrades_and_upgrades_on_postgres(pg_migrated):
    down = alembic(pg_migrated, "downgrade", "-1")
    assert down.returncode == 0, down.stderr[-800:]
    with create_engine(pg_migrated).connect() as c:
        tables = set(sa.inspect(c).get_table_names())
        assert "refresh_tokens" not in tables and "devices" in tables
    up = alembic(pg_migrated, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-800:]
    with create_engine(pg_migrated).connect() as c:
        assert "refresh_tokens" in sa.inspect(c).get_table_names()
        cols = {col["name"] for col in sa.inspect(c).get_columns("devices")}
        assert "revoked" in cols


@needs_pg
def test_postgres_enforces_what_the_schema_promises(pg_migrated):
    """Foreign keys and uniqueness are real constraints on Postgres (SQLite would accept some of these silently)."""
    eng = create_engine(pg_migrated)
    with eng.connect() as c:
        with pytest.raises(sa.exc.IntegrityError):
            c.execute(sa.text("INSERT INTO refresh_tokens (token_hash, device_id, expires_at, used, created_at) "
                              "VALUES ('h', 'no-such-device', now(), false, now())"))
            c.commit()
    eng.dispose()
