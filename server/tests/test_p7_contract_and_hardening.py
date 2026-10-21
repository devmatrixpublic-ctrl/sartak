import yaml

from app.main import app

AUTH = {"Authorization": "Bearer dev-device-1"}

# /auth/* is owned by M4 but mounted on this app, so the contract check covers it too.
AUTH_OWNED_BY_M4: set[str] = set()


def _load_contract():
    with open("../contracts/api.yaml") as f:
        spec = yaml.safe_load(f)
    spec["paths"] = {p: v for p, v in spec["paths"].items() if p not in AUTH_OWNED_BY_M4}
    return spec


def test_every_contract_path_is_mounted_on_the_app():
    contract = _load_contract()
    app_paths = set(app.openapi()["paths"].keys())

    for path in contract["paths"]:
        # OpenAPI {id} -> FastAPI {payment_id}; compare by segment count/shape
        # rather than literal string, since param names differ by design.
        normalized = path.replace("{id}", "{payment_id}")
        assert normalized in app_paths or path in app_paths, f"{path} not mounted"


def test_every_contract_operation_has_a_route_method():
    contract = _load_contract()
    app_schema = app.openapi()["paths"]

    for path, operations in contract["paths"].items():
        normalized = path.replace("{id}", "{payment_id}")
        app_ops = app_schema.get(normalized) or app_schema.get(path) or {}
        for http_method in operations:
            assert http_method.lower() in app_ops, f"{http_method.upper()} {path} not implemented"


# --- IDOR / authorization ---

def test_device_a_cannot_read_device_b_payment(client):
    resp = client.post(
        "/risk-check",
        json={
            "decision": {"level": "NONE", "score": 0.0, "reasons": []},
            "method": "checkout",
            "amount": 42.0,
            "payee_hash": "ph",
        },
        headers={"Authorization": "Bearer device-a"},
    )
    payment_id = resp.json()["payment_id"]

    resp_b = client.get(f"/payments/{payment_id}", headers={"Authorization": "Bearer device-b"})
    assert resp_b.status_code == 404  # not found, not leaked as "forbidden"


def test_no_token_is_401_everywhere_except_health_and_webhook(client):
    protected = [
        ("post", "/risk-check", {"decision": {"level": "NONE", "score": 0, "reasons": []}, "method": "checkout", "amount": 1, "payee_hash": "x"}),
        ("get", "/payments/does-not-matter", None),
        ("post", "/payments/does-not-matter/result", {"status": "success"}),
        ("post", "/trusted-contact", {"trusted_device_id": "x", "fcm_token": "y"}),
        ("post", "/alert", {"device_id": "x", "type": "alarm"}),
        ("post", "/signature", {"pattern_id": "p", "features": {"f": 1.0}}),
    ]
    for method, path, body in protected:
        resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert resp.status_code == 401, f"{method.upper()} {path} should require auth"


def test_error_body_never_contains_stack_trace_markers(client):
    resp = client.post("/risk-check", json={"method": "checkout"}, headers=AUTH)
    text = resp.text
    for marker in ("Traceback", "site-packages", ".py\", line"):
        assert marker not in text


def test_mass_assignment_extra_field_on_risk_check_is_rejected(client):
    resp = client.post(
        "/risk-check",
        json={
            "decision": {"level": "NONE", "score": 0.0, "reasons": []},
            "method": "checkout",
            "amount": 10.0,
            "payee_hash": "x",
            "is_admin": True,
        },
        headers=AUTH,
    )
    assert resp.status_code == 422


def test_openapi_docs_do_not_expose_internal_settings(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    text = resp.text
    assert "jwt_secret" not in text
    assert "razorpay_key_secret" not in text
