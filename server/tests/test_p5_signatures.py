import json

import pytest

from app.db.models import Signature
from app.signatures.schemas import SignatureIn

AUTH = {"Authorization": "Bearer dev-device-1"}


def test_valid_signature_accepted(client):
    resp = client.post(
        "/signature",
        json={"pattern_id": "sideload_during_unk", "features": {"f1": 0.5, "f2": 1.0}},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_stored_row_has_no_personal_fields(client, db):
    client.post(
        "/signature",
        json={"pattern_id": "p1", "features": {"unk_contact_recent": 1.0}},
        headers=AUTH,
    )
    rows = db.query(Signature).all()
    assert len(rows) == 1
    row = rows[0]
    # Only pattern_id, features_json and created_at exist on the model —
    # there is no device_id/phone/name/amount column to begin with.
    assert not hasattr(row, "device_id")
    assert not hasattr(row, "phone_number")
    assert not hasattr(row, "amount")
    assert "unk_contact_recent" in row.features_json


@pytest.mark.parametrize(
    "features",
    [
        {"phone_number": 123.0},
        {"payee_vpa_hash": 1.0},
        {"user_name": 1.0},
        {"amount_inr": 500.0},
        {"device_id_hash": 1.0},
        {"contact_email": 1.0},
    ],
)
def test_personal_data_like_feature_keys_rejected(features):
    with pytest.raises(ValueError):
        SignatureIn(pattern_id="p1", features=features)


def test_mass_assignment_extra_field_rejected():
    with pytest.raises(ValueError):
        SignatureIn(pattern_id="p1", features={"f1": 1.0}, phone_number="+911234567890")


def test_real_detector_feature_names_are_not_blocked():
    # These are literal names from the Member-2 detector's 16-feature set
    # (contracts/schema.json). They contain "payee"/"contact" but are
    # abstract/hashed signals, not raw personal data, so they must pass.
    features = {
        "unk_contact_recent": 1.0,
        "unk_call_active": 0.0,
        "new_payee": 1.0,
        "payee_added_after_unk": 1.0,
        "repeat_to_payee": 0.0,
        "newpayee_x_amt": 0.3,
        "unk_x_newpayee": 0.2,
        "log_amt_ratio": 1.4,
    }
    parsed = SignatureIn(pattern_id="detector_vector_1", features=features)
    assert parsed.features == features


def test_malformed_body_is_4xx(client):
    resp = client.post("/signature", json={"pattern_id": "p1"}, headers=AUTH)
    assert 400 <= resp.status_code < 500
    assert "code" in resp.json()


def test_bad_pattern_id_is_4xx(client):
    resp = client.post(
        "/signature",
        json={"pattern_id": "bad id with spaces!", "features": {"f1": 1.0}},
        headers=AUTH,
    )
    assert 400 <= resp.status_code < 500


def test_empty_features_rejected(client):
    resp = client.post("/signature", json={"pattern_id": "p1", "features": {}}, headers=AUTH)
    assert 400 <= resp.status_code < 500


def test_signature_requires_auth(client):
    resp = client.post("/signature", json={"pattern_id": "p1", "features": {"f1": 1.0}})
    assert resp.status_code == 401
