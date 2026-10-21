"""Contract tests for contracts/schema.json (plan 2.1). Run: pytest detector/tools/test_schema.py"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from upi_mapping import NotUpiUri, parse_upi_uri  # noqa: E402

SCHEMA = json.loads((ROOT / "contracts" / "schema.json").read_text())
VALID = Draft202012Validator(SCHEMA)
DATA = ROOT / "data" / "satarksim"
SALT = b"test-install-salt"
EVENT_FIELDS = ["event_type", "t_ms", "caller_known", "app_package", "install_source", "payee_id", "payee_is_new",
                "amount_inr", "payment_type"]


def to_wire(df: pd.DataFrame) -> list[dict]:
    """SatarkSim row -> schema event: t_sec -> t_ms; empty cells are omitted."""
    out = []
    for r in df.itertuples(index=False):
        e = {"event_type": r.event_type, "t_ms": int(r.t_sec) * 1000}
        for f, v in (("caller_known", r.caller_known), ("app_package", r.app_package), ("install_source", r.install_source),
                     ("payee_id", r.payee_id), ("payee_is_new", r.payee_is_new), ("amount_inr", r.amount_inr),
                     ("payment_type", r.payment_type)):
            if pd.notna(v):
                e[f] = {"True": True, "False": False}.get(v, v) if isinstance(v, str) else v
        out.append(e)
    return out


def errors(e):
    return [x.message for x in VALID.iter_errors(e)]


def test_schema_itself_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_every_row_of_the_36_vectors_is_schema_valid():
    df = pd.read_csv(DATA / "detector_test_vectors_events.csv")
    assert df.session_id.nunique() == 36
    bad = [(i, errors(e)) for i, e in enumerate(to_wire(df)) if errors(e)]
    assert not bad, bad[:5]


def test_every_simulated_event_is_schema_valid():
    df = pd.read_csv(DATA / "satarksim_events.csv", low_memory=False)
    wire = to_wire(df)
    bad = [(i, errors(e)) for i, e in enumerate(wire) if errors(e)]
    assert len(wire) > 100_000 and not bad, bad[:5]


@pytest.mark.parametrize("uri,is_p2p,amount", [
    ("upi://pay?pa=ramesh@okbank&pn=Ramesh%20K&am=1500.50&cu=INR&tn=rent", True, 1500.50),
    ("upi://pay?pa=shop@paytm&pn=Corner%20Shop&am=250&cu=INR&mc=5411", False, 250.0),
    ("UPI://PAY?pa=a%40b&am=1&cu=INR", True, 1.0),                     # case-insensitive scheme, URL-encoded @
])
def test_upi_uri_maps_to_valid_payment_attempt(uri, is_p2p, amount):
    e = parse_upi_uri(uri, SALT, 1_700_000_000_000, known_payee_hashes=set())
    assert errors(e) == []
    assert e["payment_type"] == ("P2P" if is_p2p else "P2M")
    assert e["amount_inr"] == amount and e["payee_is_new"] is True and e["source"] == "qr"
    assert "@" not in e["payee_id"] and len(e["payee_id"]) == 64      # hashed, never raw


def test_known_payee_is_not_new_and_missing_amount_uses_typed_amount():
    first = parse_upi_uri("upi://pay?pa=x@y&am=5", SALT, 1, set())
    again = parse_upi_uri("upi://pay?pa=X@Y", SALT, 2, {first["payee_id"]}, typed_amount=75, source="manual")
    assert again["payee_id"] == first["payee_id"] and again["payee_is_new"] is False
    assert again["amount_inr"] == 75.0 and again["source"] == "manual" and errors(again) == []


@pytest.mark.parametrize("uri", ["https://pay?pa=a@b&am=1", "upi://collect?pa=a@b&am=1", "upi://pay?am=1",
                                 "upi://pay?pa=nodomain&am=1", "upi://pay?pa=a@b&am=abc", "upi://pay?pa=a@b",
                                 "upi://pay?pa=a@b&am=1&cu=USD", "upi://pay?pa=a@b&am=-5", "", "garbage"])
def test_malformed_or_non_upi_uris_are_rejected(uri):
    with pytest.raises(NotUpiUri):
        parse_upi_uri(uri, SALT, 1, set())


@pytest.mark.parametrize("bad", [
    {"event_type": "PAYMENT_ATTEMPT", "t_ms": 1},                                        # missing required payment fields
    {"event_type": "PAYMENT_ATTEMPT", "t_ms": 1, "payee_id": "a@b.raw", "amount_inr": 5, "payment_type": "P2P"},  # raw VPA
    {"event_type": "APP_INSTALL", "t_ms": 1},                                            # no package
    {"event_type": "CALL_START", "t_ms": -5},                                            # negative time
    {"event_type": "CALL_START", "t_ms": 1, "phone_number": "9999999999"},               # unknown field (privacy)
    {"event_type": "SMS_READ", "t_ms": 1},                                               # unknown type
])
def test_invalid_events_are_rejected(bad):
    assert errors(bad)
