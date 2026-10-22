"""Auth through the real app: real routers, real SQL store, real JWTs (contracts/auth.md).

The attestation chains are synthetic; see attestation_fixtures.py for what that does and
does not prove.
"""
import base64

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.attestation import AttestationPolicy
from app.auth.dependencies import ensure_owner, get_auth_service, require_role
from app.auth.ratelimit import InMemoryRateLimiter
from app.auth.service import AuthService, DeviceIdentity, b64url
from app.auth.store import SqlAuthStore
from app.core.settings import Settings
from app.db.models import Device
from app.db.session import get_db
from app.main import app

from .attestation_fixtures import DIGEST, PACKAGE, make_chain

SECRET = "s" * 48
RISK_BODY = {"decision": {"level": "NONE", "score": 0.0, "reasons": []}, "method": "checkout",
             "amount": 42.0, "payee_hash": "ph"}


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def now(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# Test-only routes on the real app, to exercise admin role and ensure_owner.
@app.get("/_m4/admin-ping", include_in_schema=False)
def _admin_ping(who: DeviceIdentity = Depends(require_role("admin"))):
    return {"admin": who.device_id}


@pytest.fixture
def make_env(session_factory):
    created = []

    def _make(**settings_kw):
        clock = Clock()
        root_key = ec.generate_private_key(ec.SECP256R1())
        root = make_chain(b"\x00" * 32, root_key=root_key).root
        settings = Settings(env="dev", jwt_secret=SECRET, auth_expected_package=PACKAGE,
                            auth_expected_signing_sha256=DIGEST.hex(), **settings_kw)
        policy = AttestationPolicy(roots=[root], expected_package=PACKAGE,
                                   expected_signing_sha256=frozenset({DIGEST.hex()}),
                                   revoked=lambda: frozenset(), require_hardware=True)
        limiter = InMemoryRateLimiter(clock.now)

        def _db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        def _svc(db: Session = Depends(_db)):
            return AuthService(settings, SqlAuthStore(db), limiter, policy, clock.now)

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_auth_service] = _svc
        created.append(1)
        return {"clock": clock, "root_key": root_key, "client": TestClient(app), "settings": settings,
                "session_factory": session_factory}

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def env(make_env):
    return make_env()


def register(env, *, leaf_key=None, **chain_kw):
    client = env["client"]
    ch = client.post("/auth/challenge").json()["challenge"]
    raw = base64.urlsafe_b64decode(ch + "=" * (-len(ch) % 4))
    chain = make_chain(raw, root_key=env["root_key"], leaf_key=leaf_key, **chain_kw)
    body = {"challenge": ch, "public_key": b64(chain.leaf_spki),
            "attestation_chain": [b64(c) for c in chain.der]}
    return client.post("/auth/device", json=body), body


def test_register_matches_contract_shape_and_tokens_work_on_real_routes(env):
    r, _ = register(env)
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"access_token", "refresh_token", "token_type", "expires_in", "device_id"}
    assert data["token_type"] == "bearer" and data["expires_in"] == 900
    assert len(data["device_id"]) == 36
    risk = env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(data["access_token"]))
    assert risk.status_code == 200 and risk.json()["decision"] == "ALLOW"


def test_device_row_records_attestation_level_and_boot_state(env):
    r, _ = register(env, att_level=2, km_level=2, boot_state=2)
    with env["session_factory"]() as s:
        row = s.get(Device, r.json()["device_id"])
        assert (row.attestation_level, row.verified_boot_state, row.role) == ("StrongBox", "unverified", "device")


def test_challenge_response_is_iso_datetime(env):
    body = env["client"].post("/auth/challenge", json={}).json()
    assert set(body) == {"challenge", "expires_at"} and "T" in body["expires_at"]


def test_challenge_cannot_be_reused(env):
    r, body = register(env)
    assert r.status_code == 200
    again = env["client"].post("/auth/device", json=body)
    assert again.status_code == 400 and again.json()["code"] == "challenge_invalid"


def test_expired_challenge_rejected(env):
    client = env["client"]
    ch = client.post("/auth/challenge").json()["challenge"]
    raw = base64.urlsafe_b64decode(ch + "=" * (-len(ch) % 4))
    chain = make_chain(raw, root_key=env["root_key"])
    env["clock"].advance(121)
    r = client.post("/auth/device", json={"challenge": ch, "public_key": b64(chain.leaf_spki),
                                          "attestation_chain": [b64(c) for c in chain.der]})
    assert r.status_code == 400 and r.json()["code"] == "challenge_invalid"


def test_unknown_challenge_rejected(env):
    chain = make_chain(b"\x01" * 32, root_key=env["root_key"])
    r = env["client"].post("/auth/device", json={"challenge": b64url(b"\x01" * 32),
                                                 "public_key": b64(chain.leaf_spki),
                                                 "attestation_chain": [b64(c) for c in chain.der]})
    assert r.status_code == 400 and r.json()["code"] == "challenge_invalid"


def test_software_only_attestation_rejected(env):
    r, _ = register(env, att_level=0, km_level=0)
    assert r.status_code == 400 and r.json()["code"] == "software_only"


def test_wrong_app_rejected(env):
    r, _ = register(env, packages=("com.evil.app",))
    assert r.status_code == 400 and r.json()["code"] == "app_mismatch"


def test_reregistering_same_key_gives_same_device_id(env):
    key = ec.generate_private_key(ec.SECP256R1())
    ids = [register(env, leaf_key=key)[0].json()["device_id"] for _ in range(2)]
    assert ids[0] == ids[1]


def test_role_field_may_only_be_device_and_extras_are_rejected(env):
    _, body = register(env)
    for bad in ({"role": "admin"}, {"device_id": "victim"}, {"is_admin": True}):
        r = env["client"].post("/auth/device", json=dict(body, **bad))
        assert r.status_code == 422
    assert "victim" not in r.text


def test_no_token_garbage_token_and_basic_auth(env):
    c = env["client"]
    assert c.post("/risk-check", json=RISK_BODY).json()["code"] == "missing_token"
    assert c.post("/risk-check", json=RISK_BODY, headers=bearer("nope")).json()["code"] == "invalid_token"
    assert c.post("/risk-check", json=RISK_BODY, headers={"Authorization": "Basic abc"}).json()["code"] == "missing_token"


def test_401_carries_www_authenticate_and_only_code_message(env):
    r = env["client"].post("/risk-check", json=RISK_BODY)
    assert r.status_code == 401 and set(r.json()) == {"code", "message"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_expired_access_token_401(env):
    r, _ = register(env)
    env["clock"].advance(16 * 60)
    resp = env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(r.json()["access_token"]))
    assert resp.status_code == 401 and resp.json()["code"] == "token_expired"


def test_forged_tokens_rejected(env):
    r, _ = register(env)
    claims = {"sub": r.json()["device_id"], "role": "device", "typ": "access",
              "exp": int(env["clock"].now()) + 600}
    for tok in (jwt.encode(claims, "x" * 48, algorithm="HS256"), jwt.encode(claims, None, algorithm="none"),
                jwt.encode(dict(claims, role="admin"), "x" * 48, algorithm="HS256")):
        assert env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(tok)).json()["code"] == "invalid_token"


def test_token_for_unregistered_device_rejected(env):
    claims = {"sub": "no-such-device", "role": "device", "typ": "access", "exp": int(env["clock"].now()) + 600}
    tok = jwt.encode(claims, SECRET, algorithm="HS256")
    assert env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(tok)).json()["code"] == "invalid_token"


def test_refresh_token_is_not_an_access_token(env):
    r, _ = register(env)
    resp = env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(r.json()["refresh_token"]))
    assert resp.json()["code"] == "invalid_token"


def test_wrong_role_is_403(env):
    r, _ = register(env)
    resp = env["client"].get("/_m4/admin-ping", headers=bearer(r.json()["access_token"]))
    assert resp.status_code == 403 and resp.json()["code"] == "forbidden_role"


def test_admin_device_cannot_use_device_routes_and_vice_versa(env):
    with env["session_factory"]() as s:
        s.add(Device(id="admin-1", public_key="pk-admin", attestation_level="TEE",
                     verified_boot_state="verified", role="admin"))
        s.commit()
    tok = jwt.encode({"sub": "admin-1", "role": "admin", "typ": "access",
                      "exp": int(env["clock"].now()) + 600}, SECRET, algorithm="HS256")
    assert env["client"].get("/_m4/admin-ping", headers=bearer(tok)).status_code == 200
    assert env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(tok)).status_code == 403


def test_burst_gets_429_with_retry_after_then_recovers(make_env):
    env = make_env(rate_limit_per_minute=3)
    r, _ = register(env)
    tok = bearer(r.json()["access_token"])
    codes = [env["client"].get("/payments/x", headers=tok).status_code for _ in range(5)]
    assert codes == [404, 404, 404, 429, 429]
    limited = env["client"].get("/payments/x", headers=tok)
    assert limited.json()["code"] == "rate_limited" and int(limited.headers["retry-after"]) >= 1
    env["clock"].advance(61)
    assert env["client"].get("/payments/x", headers=tok).status_code == 404


def test_challenge_endpoint_is_rate_limited(env):
    codes = [env["client"].post("/auth/challenge").status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_idor_other_device_cannot_read_my_payment_on_real_routes(env):
    a, _ = register(env)
    b, _ = register(env)
    assert a.json()["device_id"] != b.json()["device_id"]
    pay = env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(a.json()["access_token"])).json()
    mine = env["client"].get(f"/payments/{pay['payment_id']}", headers=bearer(a.json()["access_token"]))
    theirs = env["client"].get(f"/payments/{pay['payment_id']}", headers=bearer(b.json()["access_token"]))
    missing = env["client"].get("/payments/does-not-exist", headers=bearer(b.json()["access_token"]))
    assert mine.status_code == 200
    assert theirs.status_code == 404 and theirs.json() == missing.json()


def test_ensure_owner_helper():
    ensure_owner(DeviceIdentity("d1", "device"), "d1")
    ensure_owner(DeviceIdentity("a", "admin"), "d1")
    with pytest.raises(Exception) as e:
        ensure_owner(DeviceIdentity("d2", "device"), "d1")
    assert e.value.status_code == 404


def test_refresh_rotates_and_reuse_revokes_device(env):
    old = register(env)[0].json()
    c = env["client"]
    new = c.post("/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert new.status_code == 200 and new.json()["device_id"] == old["device_id"]
    assert c.post("/risk-check", json=RISK_BODY, headers=bearer(new.json()["access_token"])).status_code == 200

    replay = c.post("/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["code"] == "refresh_reuse"
    # the whole device is now dead, including the freshly rotated pair
    assert c.post("/risk-check", json=RISK_BODY, headers=bearer(new.json()["access_token"])).json()["code"] == "invalid_token"
    assert c.post("/auth/refresh", json={"refresh_token": new.json()["refresh_token"]}).status_code == 401


def test_refresh_garbage_and_expiry(env):
    r, _ = register(env)
    c = env["client"]
    assert c.post("/auth/refresh", json={"refresh_token": "a" * 43}).json()["code"] == "invalid_refresh"
    env["clock"].advance(31 * 24 * 3600)
    assert c.post("/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}).json()["code"] == "invalid_refresh"


def test_refresh_tokens_are_stored_hashed(env):
    from app.db.models import RefreshToken
    r, _ = register(env)
    with env["session_factory"]() as s:
        hashes = [t.token_hash for t in s.query(RefreshToken).all()]
    assert hashes and r.json()["refresh_token"] not in hashes and all(len(h) == 64 for h in hashes)


def test_reattesting_revives_a_revoked_device(env):
    key = ec.generate_private_key(ec.SECP256R1())
    first = register(env, leaf_key=key)[0].json()
    env["client"].post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    env["client"].post("/auth/refresh", json={"refresh_token": first["refresh_token"]})    # replay -> revoked
    assert env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(first["access_token"])).json()["code"] == "invalid_token"
    again = register(env, leaf_key=key)[0].json()
    assert env["client"].post("/risk-check", json=RISK_BODY, headers=bearer(again["access_token"])).status_code == 200


def test_trusted_contact_requires_a_registered_device_with_real_auth(env):
    owner = register(env)[0].json()
    friend = register(env)[0].json()
    c = env["client"]
    ok = c.post("/trusted-contact", json={"trusted_device_id": friend["device_id"], "fcm_token": "tok"},
                headers=bearer(owner["access_token"]))
    assert ok.status_code == 200
    ghost = c.post("/trusted-contact", json={"trusted_device_id": "ghost", "fcm_token": "tok"},
                   headers=bearer(owner["access_token"]))
    assert ghost.status_code == 404


# --- dev-token stub ---------------------------------------------------------------------
def test_dev_token_is_404_unless_enabled(env):
    assert env["client"].post("/auth/dev-token", json={"device_id": "d1"}).status_code == 404


def test_dev_token_works_when_enabled(make_env):
    env = make_env(auth_enable_dev_token=True)
    c = env["client"]
    tok = c.post("/auth/dev-token", json={"device_id": "dev-1"}).json()["access_token"]
    assert c.post("/risk-check", json=RISK_BODY, headers=bearer(tok)).status_code == 200
    assert c.get("/_m4/admin-ping", headers=bearer(tok)).status_code == 403
    adm = c.post("/auth/dev-token", json={"device_id": "adm-1", "role": "admin"}).json()["access_token"]
    assert c.get("/_m4/admin-ping", headers=bearer(adm)).status_code == 200


def test_no_policy_means_503_not_a_crash(env):
    svc_settings = env["settings"]
    svc = AuthService(svc_settings, store=None, limiter=InMemoryRateLimiter(), policy=None)
    from app.auth.errors import AuthError
    with pytest.raises(AuthError) as e:
        svc.register_device("c" * 43, "AAAA", ["AAAA", "AAAA"])
    assert e.value.status_code == 503


# --- client address behind a proxy (app/core/clientip.py) -------------------------------------------------------------------------
def _challenge(env, xff: str | None):
    return env["client"].post("/auth/challenge", headers={"X-Forwarded-For": xff} if xff else {}).status_code


def test_default_a_caller_cannot_dodge_the_limit_by_rotating_x_forwarded_for(make_env):
    env = make_env()                                                    # trusted_proxy_hops = 0: the header is ignored
    codes = [_challenge(env, f"203.0.113.{i}") for i in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_with_one_trusted_hop_clients_get_separate_buckets_and_spoofed_prefixes_do_not_help(make_env):
    env = make_env(trusted_proxy_hops=1)
    assert [_challenge(env, "198.51.100.1") for _ in range(10)] == [200] * 10
    assert _challenge(env, "198.51.100.1") == 429                       # client A is limited ...
    assert _challenge(env, "198.51.100.2") == 200                       # ... client B has its own bucket
    assert _challenge(env, "192.0.2.77, 198.51.100.1") == 429           # a forged left-hand entry does not escape A's bucket
