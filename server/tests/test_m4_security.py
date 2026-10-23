"""OWASP-style checks against the real app (ops/security/checklist.md links each item to a test here).

These run WITHOUT the harness auth override, so they exercise real authentication.
"""
import re
import json

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.session import get_db
from app.main import app

PUBLIC = {"/health", "/webhooks/razorpay", "/auth/challenge", "/auth/device", "/auth/refresh", "/auth/dev-token"}
DOC_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
RISK_OK = {"decision": {"level": "NONE", "score": 0.0, "reasons": []}, "method": "checkout",
           "amount": 42.0, "payee_hash": "ph"}


@pytest.fixture
def raw_client(session_factory):
    """Real auth (no override) over the test database."""
    def _db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def authed(client, session_factory):
    """A client that IS authenticated, using the harness shorthand, for input-validation probes."""
    return client


# --- A1/A2: authentication on every route ----------------------------------------------
def _route_cases():
    """Enumerate through the OpenAPI schema: FastAPI nests included routers, so app.routes is not reliable."""
    for path, ops in app.openapi()["paths"].items():
        if path in PUBLIC or path in DOC_PATHS or path.startswith("/_m4"):
            continue
        for method in ops:
            yield method.upper(), path


def test_every_non_public_route_rejects_a_request_with_no_token(raw_client):
    cases = list(_route_cases())
    assert len(cases) >= 6                         # guard against the enumeration silently finding nothing
    for method, path in cases:
        url = re.sub(r"\{[a-z_]+\}", "x", path)
        assert "{" not in url, f"unhandled path parameter in {path}"
        resp = raw_client.request(method, url, json={} if method in {"POST", "PUT", "PATCH"} else None)
        assert resp.status_code == 401, f"{method} {path} answered {resp.status_code} without a token"
        assert resp.json()["code"] in {"missing_token", "unauthorized"}


def test_webhook_is_not_bearer_protected_but_fails_closed_without_a_valid_signature(raw_client):
    resp = raw_client.post("/webhooks/razorpay", content=b"{}")
    assert resp.status_code == 400


# --- A3: mass assignment ---------------------------------------------------------------
def test_every_request_body_model_forbids_unknown_fields():
    spec = app.openapi()
    seen = 0
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if not body or "$ref" not in body:
                continue
            schema = spec["components"]["schemas"][body["$ref"].rsplit("/", 1)[1]]
            seen += 1
            assert schema.get("additionalProperties") is False, (
                f"{method.upper()} {path}: {body['$ref']} accepts unknown fields (mass assignment)")
    assert seen >= 6                                  # guard against the enumeration silently finding nothing


# --- A4: error handling never leaks ----------------------------------------------------
def test_validation_errors_do_not_echo_what_the_client_sent(authed):
    canary = "canary-payee-value"
    resp = authed.post("/risk-check", json={**RISK_OK, "amount": "not-a-number", "payee_hash": canary,
                                            "surprise": canary},
                       headers={"Authorization": "Bearer dev-device-1"})
    assert resp.status_code == 422
    assert set(resp.json()) == {"code", "message"}
    assert canary not in resp.text and "not-a-number" not in resp.text


def test_unhandled_exception_returns_a_generic_500_with_no_stack_trace(raw_client):
    @app.get("/_m4/boom", include_in_schema=False)
    def boom(request: Request):
        raise RuntimeError("database password is hunter2")

    resp = raw_client.get("/_m4/boom")
    assert resp.status_code == 500
    assert resp.json() == {"code": "internal_error", "message": "An internal error occurred."}
    assert "hunter2" not in resp.text and "Traceback" not in resp.text


def test_path_ids_with_sql_metacharacters_are_just_not_found(authed):
    for evil in ("1' OR '1'='1", "x%27%3B%20DROP%20TABLE%20payments%3B--", "../../etc/passwd"):
        resp = authed.get(f"/payments/{evil}", headers={"Authorization": "Bearer dev-device-1"})
        assert resp.status_code in (404, 422), evil
        assert "sql" not in resp.text.lower() and "syntax" not in resp.text.lower()


# --- A5: input validation --------------------------------------------------------------
@pytest.mark.parametrize("amount", [0, -1, -0.01, 1e300, float("inf"), float("nan")])
def test_payment_amount_must_be_positive_and_finite(authed, amount):
    body = json.dumps({**RISK_OK, "amount": amount}, allow_nan=True)
    resp = authed.post("/risk-check", content=body, headers={"Authorization": "Bearer dev-device-1",
                                                              "content-type": "application/json"})
    assert resp.status_code == 422, f"amount={amount!r} was accepted"


def test_oversized_strings_are_rejected(authed):
    h = {"Authorization": "Bearer dev-device-1"}
    assert authed.post("/risk-check", json={**RISK_OK, "payee_hash": "x" * 5000}, headers=h).status_code == 422
    assert authed.post("/signature", json={"pattern_id": "p" * 5000, "features": {"new_payee": 1.0}},
                       headers=h).status_code == 422
    assert authed.post("/trusted-contact", json={"trusted_device_id": "d" * 5000, "fcm_token": "t"},
                       headers=h).status_code == 422


def test_reasons_list_is_capped_at_three(authed):
    body = {**RISK_OK, "decision": {"level": "HARD", "score": 1.0, "reasons": ["a", "b", "c", "d"]}}
    assert authed.post("/risk-check", json=body, headers={"Authorization": "Bearer dev-device-1"}).status_code == 422


# --- A6: no cross-origin access is granted ---------------------------------------------
def test_no_cors_headers_are_emitted(raw_client):
    resp = raw_client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


# --- P1: privacy by schema and by logging ----------------------------------------------
def test_no_table_has_a_raw_personal_data_column():
    banned = ("phone", "msisdn", "email", "vpa", "upi_id", "name", "address", "aadhaar", "pan", "contact_number")
    for table in Base.metadata.tables.values():
        for col in table.columns:
            lowered = col.name.lower()
            assert not any(b in lowered for b in banned if not (b == "name" and lowered in {"tablename"})), \
                f"{table.name}.{col.name} looks like raw personal data"


def test_signatures_cannot_be_linked_to_a_device():
    cols = {c.name for c in Base.metadata.tables["signatures"].columns}
    assert "device_id" not in cols and not any("device" in c for c in cols)


def test_request_logs_contain_no_bodies_amounts_or_payee_hashes(authed, caplog):
    import logging

    marker = "PAYEE-HASH-MARKER-98765"
    with caplog.at_level(logging.DEBUG):
        authed.post("/risk-check", json={**RISK_OK, "payee_hash": marker, "amount": 123456.78},
                    headers={"Authorization": "Bearer dev-device-1"})
    everything = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "request_handled" in everything           # logging is on, so the next assertions mean something
    assert marker not in everything and "123456.78" not in everything
    assert "Authorization" not in everything and "Bearer" not in everything


# --- A7: security misconfiguration -----------------------------------------------------
def test_docs_and_schema_are_not_served_outside_dev(monkeypatch, tmp_path):
    from app.core import settings as settings_module
    from app.main import create_app

    roots = tmp_path / "roots.pem"
    roots.write_text("x")
    for name, value in {"SATARK_ENV": "production", "SATARK_JWT_SECRET": "p" * 48,
                        "SATARK_AUTH_ATTESTATION_ROOTS": str(roots), "SATARK_AUTH_EXPECTED_PACKAGE": "com.satark.app",
                        "SATARK_AUTH_EXPECTED_SIGNING_SHA256": "ab" * 32}.items():
        monkeypatch.setenv(name, value)
    settings_module.get_settings.cache_clear()
    try:
        prod = TestClient(create_app(), raise_server_exceptions=False)
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert prod.get(path).status_code == 404, path
        assert prod.get("/health").status_code == 200
    finally:
        settings_module.get_settings.cache_clear()


def test_docs_are_available_in_dev(raw_client):
    assert raw_client.get("/openapi.json").status_code == 200
