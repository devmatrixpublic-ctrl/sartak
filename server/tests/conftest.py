import pytest
from fastapi import Depends, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import require_device, reset_auth_caches
from app.auth.ratelimit import reset_rate_limiter
from app.core.errors import ApiError
from app.db.base import Base
from app.db import models  # noqa: F401  (register models on Base.metadata)
from app.db.models import Device
from app.db.session import get_db
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-device-1"}


def _bearer_is_device_id(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> str:
    if not authorization or not authorization.startswith("Bearer ") or not authorization.removeprefix("Bearer ").strip():
        raise ApiError(401, "unauthorized", "Missing bearer token")
    device_id = authorization.removeprefix("Bearer ").strip()
    if db.get(Device, device_id) is None:
        db.add(Device(id=device_id, public_key=f"test:{device_id}", attestation_level="TEE",
                      verified_boot_state="verified"))
        db.commit()
    return device_id


@pytest.fixture(autouse=True)
def _fresh_auth_state():
    reset_rate_limiter()
    reset_auth_caches()
    yield
    reset_rate_limiter()
    reset_auth_caches()


@pytest.fixture
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, future=True)


@pytest.fixture
def db(db_session):
    return db_session


@pytest.fixture
def client(session_factory):
    def _override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    # Payments/alerts/webhook tests are about those modules, not about auth, so they keep their
    # `Bearer <device_id>` shorthand. This override exists ONLY in the test harness: it never ships.
    # Real JWT + attestation behaviour, including the same routers, is covered by test_m4_*.py.
    app.dependency_overrides[require_device] = _bearer_is_device_id
    yield TestClient(app)
    app.dependency_overrides.clear()
