"""Response shapes the contract promises, found by driving the real server with the real detector's decisions
(ops/e2e/run_e2e.py): optional fields are ABSENT, not null (api.yaml types them as plain strings)."""
import pytest

from tests.conftest import AUTH_HEADERS

BODY = {"decision": {"level": "NONE", "score": 0.0, "reasons": []}, "method": "checkout", "amount": 42.0,
        "payee_hash": "ph", "is_p2p": True}


def risk(client, level="NONE", method="checkout"):
    body = {**BODY, "method": method, "decision": {**BODY["decision"], "level": level}}
    return client.post("/risk-check", json=body, headers=AUTH_HEADERS)


def test_order_id_is_present_only_for_an_allowed_checkout(client):
    allowed = risk(client).json()
    assert allowed["decision"] == "ALLOW" and allowed["order_id"]
    for held in (risk(client, "HARD"), risk(client, "NONE", "upi_intent"), risk(client, "HARD", "upi_intent")):
        assert "order_id" not in held.json(), held.json()          # absent, not null


def test_payment_responses_omit_unset_optional_fields(client):
    pid = risk(client, "NONE", "upi_intent").json()["payment_id"]
    p = client.get(f"/payments/{pid}", headers=AUTH_HEADERS).json()
    assert p["state"] == "handed_off"
    for k in ("razorpay_order_id", "reported_status", "reported_txn_ref"):
        assert k not in p, p
    done = client.post(f"/payments/{pid}/result", json={"status": "success", "txn_ref": "R1"}, headers=AUTH_HEADERS).json()
    assert done["reported_status"] == "success" and done["reported_txn_ref"] == "R1" and "razorpay_order_id" not in done


def test_signature_with_a_personal_data_key_is_a_422_as_the_contract_states(client):
    r = client.post("/signature", json={"pattern_id": "x", "features": {"phone_number": 1.0}}, headers=AUTH_HEADERS)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    spec = open(__import__("pathlib").Path(__file__).resolve().parents[2] / "contracts" / "api.yaml").read()
    seg = spec[spec.index("  /signature:"):]
    assert "'422':" in seg and "'400':" not in seg
