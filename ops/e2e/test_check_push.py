import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).parent))

import check_push as cp  # noqa: E402

TOKEN = "fcm-token-SECRETVALUE-abcdef"


@pytest.fixture(scope="module")
def sa():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return {"type": "service_account", "project_id": "satark-demo", "private_key_id": "k", "private_key": pem,
            "client_email": "fb@satark-demo.iam.gserviceaccount.com", "client_id": "1", "token_uri": "https://oauth2.googleapis.com/token"}


@pytest.fixture(autouse=True)
def clean_firebase():
    import firebase_admin
    yield
    for app in list(firebase_admin._apps.values()):
        firebase_admin.delete_app(app)


def gs(project="satark-demo", package="com.satark.app"):
    return {"project_info": {"project_id": project, "project_number": "1"},
            "client": [{"client_info": {"mobilesdk_app_id": "1:1:android:a", "android_client_info": {"package_name": package}}}]}


def write(tmp_path, name, data):
    f = tmp_path / name
    f.write_text(json.dumps(data))
    return f


def test_offline_check_passes_for_a_good_key_and_matching_app(sa, tmp_path, capsys):
    code = cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--google-services", str(write(tmp_path, "g.json", gs()))])
    out = capsys.readouterr().out
    assert code == 0 and "project 'satark-demo'" in out and "done (offline only)" in out


def test_a_project_mismatch_is_the_failure_it_names(sa, tmp_path, capsys):
    code = cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--google-services", str(write(tmp_path, "g.json", gs(project="other-project")))])
    out = capsys.readouterr().out
    assert code == 1 and "other-project" in out and "SAME project" in out


def test_wrong_package_is_reported(sa, tmp_path, capsys):
    assert cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--google-services", str(write(tmp_path, "g.json", gs(package="com.x.y")))]) == 1
    assert "not registered for the package com.satark.app" in capsys.readouterr().out


def test_the_key_or_the_google_services_file_never_appears_in_output(sa, tmp_path, capsys):
    f = write(tmp_path, "sa.json", sa)
    cp.main(["--credentials", str(f), "--google-services", str(write(tmp_path, "g.json", gs(project="zzz")))])
    out = capsys.readouterr().out
    assert sa["private_key"][40:80] not in out and "BEGIN PRIVATE KEY" not in out


def test_credentials_can_come_from_the_render_environment_variable(sa, monkeypatch, capsys):
    monkeypatch.setenv(cp.ENV_CREDENTIALS, json.dumps(sa))
    assert cp.main([]) == 0


def test_no_credentials_is_a_clear_error(monkeypatch, capsys):
    monkeypatch.delenv(cp.ENV_CREDENTIALS, raising=False)
    assert cp.main([]) == 2 and "--credentials" in capsys.readouterr().out


def test_an_unusable_key_fails_offline_without_echoing_it(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text('{"type": "service_account", "project_id": "p", "client_email": "e", "private_key": "NOT-A-KEY-MARKER"}')
    assert cp.main(["--credentials", str(f)]) == 1
    out = capsys.readouterr().out
    assert "NOT-A-KEY-MARKER" not in out and "could not be read" in out


def test_dry_run_calls_firebase_with_dry_run_true_and_never_prints_the_token(sa, tmp_path, monkeypatch, capsys):
    from firebase_admin import messaging
    seen = {}
    monkeypatch.setattr(messaging, "send", lambda m, **kw: seen.update(msg=m, kw=kw) or "id")
    monkeypatch.setenv("T", TOKEN)
    code = cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--token-env", "T", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0 and seen["kw"] == {"dry_run": True} and seen["msg"].token == TOKEN
    assert TOKEN not in out and "abcdef" in out                                  # only the last six characters are shown


def test_a_firebase_error_is_explained_and_does_not_leak_the_token(sa, tmp_path, monkeypatch, capsys):
    from firebase_admin import messaging
    from firebase_admin.exceptions import UnauthenticatedError

    def boom(m, **kw):
        raise UnauthenticatedError(f"auth failed for {TOKEN}")

    monkeypatch.setattr(messaging, "send", boom)
    monkeypatch.setenv("T", TOKEN)
    code = cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--token-env", "T", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 1 and "UnauthenticatedError" in out and "SECRETVALUE" not in out


def test_send_uses_the_servers_real_client_and_reports_a_stale_token(sa, tmp_path, monkeypatch, capsys):
    from firebase_admin import messaging
    from firebase_admin.exceptions import NotFoundError
    monkeypatch.setattr(messaging, "send", lambda m, **kw: "projects/p/messages/1")
    monkeypatch.setenv("T", TOKEN)
    f = write(tmp_path, "sa.json", sa)
    assert cp.main(["--credentials", str(f), "--token-env", "T", "--send"]) == 0
    assert "look at the phone" in capsys.readouterr().out

    def stale(m, **kw):
        raise NotFoundError("gone")

    monkeypatch.setattr(messaging, "send", stale)
    assert cp.main(["--credentials", str(f), "--token-env", "T", "--send"]) == 1
    assert "Firebase rejected the token" in capsys.readouterr().out


def test_a_missing_token_variable_is_a_clear_error(sa, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("T", raising=False)
    assert cp.main(["--credentials", str(write(tmp_path, "sa.json", sa)), "--token-env", "T", "--dry-run"]) == 2
    assert "empty or not set" in capsys.readouterr().out
