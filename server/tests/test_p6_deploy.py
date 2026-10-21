import logging

import yaml

from app.core.logging import JsonFormatter, RequestIdFilter


def test_health_returns_request_id_header(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-Id" in resp.headers


def test_request_id_propagates_from_client_header(client):
    resp = client.get("/health", headers={"X-Request-Id": "test-req-123"})
    assert resp.headers["X-Request-Id"] == "test-req-123"


def test_log_formatter_never_includes_raw_body_keys():
    record = logging.LogRecord(
        name="satark.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_handled",
        args=(),
        exc_info=None,
    )
    record.request_id = "r1"
    record.method = "POST"
    record.path = "/risk-check"
    record.status_code = 200
    record.duration_ms = 1.2

    formatted = JsonFormatter().format(record)
    assert "amount" not in formatted
    assert "payee_hash" not in formatted
    assert "phone" not in formatted
    assert '"method": "POST"' in formatted or '"method":"POST"' in formatted.replace(" ", "")


def test_render_yaml_is_valid_and_has_required_services():
    with open("../render.yaml") as f:
        spec = yaml.safe_load(f)

    assert any(db["name"] == "satark-db" for db in spec["databases"])
    service_types = {svc["type"] for svc in spec["services"]}
    assert "web" in service_types
    assert "keyvalue" in service_types

    web = next(s for s in spec["services"] if s["type"] == "web")
    assert web["healthCheckPath"] == "/health"
    env_keys = {e["key"] for e in web["envVars"]}
    assert "SATARK_DATABASE_URL" in env_keys
    assert "SATARK_REDIS_URL" in env_keys
    assert "SATARK_RAZORPAY_WEBHOOK_SECRET" in env_keys
