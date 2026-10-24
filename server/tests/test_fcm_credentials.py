"""The real Firebase path: SATARK_FIREBASE_CREDENTIALS_JSON is the service-account JSON itself (render.yaml, DEPLOY_CHECKLIST).
firebase_admin's Certificate takes a file path or a parsed dict, never JSON text, so passing the text straight through crashed the first real alert.
These tests use a throwaway key generated here; nothing reaches Google."""
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.alerts import fcm_client
from app.alerts.fcm_client import FcmTokenInvalid, FirebaseFcmClient, check_credentials_json

MARKER = "TOPSECRETMARKER"


@pytest.fixture(scope="module")
def service_account():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return {"type": "service_account", "project_id": "satark-test", "private_key_id": "abc123", "private_key": pem,
            "client_email": "firebase-adminsdk@satark-test.iam.gserviceaccount.com", "client_id": "1",
            "token_uri": "https://oauth2.googleapis.com/token"}


@pytest.fixture(autouse=True)
def no_leftover_firebase_app():
    import firebase_admin
    yield
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)


def test_the_json_text_in_the_environment_variable_builds_a_client(service_account):
    FirebaseFcmClient(json.dumps(service_account))                      # was: ValueError, text is not a path or a dict


def test_a_file_path_still_works_for_local_use(service_account, tmp_path):
    f = tmp_path / "sa.json"
    f.write_text(json.dumps(service_account))
    FirebaseFcmClient(str(f))


def test_json_with_surrounding_whitespace_and_newlines_is_accepted(service_account):
    FirebaseFcmClient("\n  " + json.dumps(service_account, indent=2) + "\n")      # how a pasted dashboard value often arrives


@pytest.mark.parametrize("bad", [MARKER + " not json {", "{" + MARKER, '{"type": "service_account", "private_key": "' + MARKER + '"}', "[1, 2]"])
def test_a_bad_value_is_refused_with_a_message_that_does_not_echo_the_secret(bad):
    with pytest.raises(RuntimeError) as err:
        check_credentials_json(bad)
    assert MARKER not in str(err.value)
    with pytest.raises(RuntimeError) as err2:
        FirebaseFcmClient(bad)
    assert MARKER not in str(err2.value)


def test_check_accepts_empty_means_stub_and_a_valid_account(service_account):
    check_credentials_json("")                                          # no credentials: the local stub is used, on purpose
    check_credentials_json(json.dumps(service_account))


def test_the_check_demands_a_service_account_not_just_any_json(service_account):
    wrong = dict(service_account, type="authorized_user")
    with pytest.raises(RuntimeError, match="service_account"):
        check_credentials_json(json.dumps(wrong))
    missing = {k: v for k, v in service_account.items() if k != "client_email"}
    with pytest.raises(RuntimeError, match="client_email"):
        check_credentials_json(json.dumps(missing))


def test_the_server_refuses_to_boot_with_unusable_credentials(monkeypatch):
    from app.core.settings import Settings
    from app.main import validate_push_settings
    validate_push_settings(Settings(firebase_credentials_json=""))
    with pytest.raises(RuntimeError, match="FIREBASE"):
        validate_push_settings(Settings(firebase_credentials_json="garbage"))


def test_a_stale_token_becomes_fcm_token_invalid_not_a_500(service_account, monkeypatch):
    from firebase_admin import messaging
    from firebase_admin.exceptions import NotFoundError
    client = FirebaseFcmClient(json.dumps(service_account))

    def boom(message, **kw):
        raise NotFoundError("Requested entity was not found.")

    monkeypatch.setattr(messaging, "send", boom)
    with pytest.raises(FcmTokenInvalid):
        client.send("stale-token", "t", "b", {"k": "v"})


def test_send_builds_the_message_the_phone_expects(service_account, monkeypatch):
    from firebase_admin import messaging
    sent = {}
    monkeypatch.setattr(messaging, "send", lambda m, **kw: sent.setdefault("m", m) and "projects/x/messages/1")
    client = FirebaseFcmClient(json.dumps(service_account))
    assert client.send("tok", "Title", "Body", {"kind": "alert"}) == "projects/x/messages/1"
    m = sent["m"]
    assert (m.token, m.notification.title, m.notification.body, m.data) == ("tok", "Title", "Body", {"kind": "alert"})


def test_get_fcm_client_uses_the_stub_only_when_nothing_is_configured(service_account):
    assert isinstance(fcm_client.get_fcm_client(""), fcm_client.LocalStubFcmClient)
    assert isinstance(fcm_client.get_fcm_client(json.dumps(service_account)), FirebaseFcmClient)


def test_create_app_itself_runs_the_check(monkeypatch):
    """Not just the helper: the real application factory must refuse to start (a mutation that dropped the call would otherwise pass)."""
    from app.core.settings import get_settings
    from app.main import create_app
    monkeypatch.setenv("SATARK_FIREBASE_CREDENTIALS_JSON", "garbage")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SATARK_FIREBASE_CREDENTIALS_JSON"):
            create_app()
    finally:
        monkeypatch.delenv("SATARK_FIREBASE_CREDENTIALS_JSON")
        get_settings.cache_clear()


def test_text_that_is_neither_json_nor_a_real_file_says_exactly_that(tmp_path):
    with pytest.raises(RuntimeError, match="neither the service-account JSON nor the path"):
        check_credentials_json("not-json-and-not-a-file")
    with pytest.raises(RuntimeError, match="neither the service-account JSON nor the path"):
        check_credentials_json(str(tmp_path / "missing.json"))
