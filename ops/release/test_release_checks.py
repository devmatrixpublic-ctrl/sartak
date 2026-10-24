import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import check_apk_signature as ca  # noqa: E402
import check_release_config as cr  # noqa: E402

PIN_A = "sha256/" + "A" * 43 + "="
PIN_B = "sha256/" + "B" * 43 + "="
GOOD = {
    "SERVER_URL": "https://satark-server.onrender.com/",
    "CERT_PINS": f"{PIN_A},{PIN_B}",
    "RAZORPAY_KEY_ID": "rzp_test_AbCdEf123456",
    "EXPECTED_SIGNING_SHA256": "ab" * 32,
    "RELEASE_TAG": "v1.0.0",
}


def with_(**kw):
    env = dict(GOOD)
    env.update(kw)
    return env


# --- check_release_config -----------------------------------------------------------------------------------------------
def test_a_complete_configuration_has_no_problems():
    assert cr.problems(GOOD) == []
    assert cr.problems(with_(RELEASE_TAG="v2.3.4-rc.1")) == []


@pytest.mark.parametrize("env,needle", [
    (with_(SERVER_URL=""), "not set"),
    (with_(SERVER_URL="http://satark.onrender.com/"), "https://"),
    (with_(SERVER_URL="https://localhost/"), "local address"),
    (with_(SERVER_URL="https://10.0.2.2/"), "local address"),
    (with_(SERVER_URL="https://satark.onrender.com"), "end with /"),
    (with_(SERVER_URL="https://satark.onrender.com/?x=1"), "plain base URL"),
    (with_(CERT_PINS=""), "DISABLES certificate pinning"),
    (with_(CERT_PINS=PIN_A), "at least two"),
    (with_(CERT_PINS=f"{PIN_A},{PIN_A}"), "at least two"),
    (with_(CERT_PINS=f"{PIN_A},sha256/short"), "not pins"),
    (with_(RAZORPAY_KEY_ID=""), "not set"),
    (with_(RAZORPAY_KEY_ID="rzp_test_REPLACE_ME"), "TEST-mode"),
    (with_(RAZORPAY_KEY_ID="rzp_live_AbCdEf123456"), "TEST-mode"),
    (with_(EXPECTED_SIGNING_SHA256=""), "not set"),
    (with_(EXPECTED_SIGNING_SHA256="AB:" * 31 + "AB"), "keytool format"),
    (with_(EXPECTED_SIGNING_SHA256="abc"), "invalid"),
    (with_(RELEASE_TAG="release-1"), "not a version tag"),
])
def test_each_unsafe_value_is_reported(env, needle):
    found = cr.problems(env)
    assert any(needle in p for p in found), found


def test_every_problem_is_reported_at_once_not_just_the_first():
    found = cr.problems({"SERVER_URL": "http://x", "CERT_PINS": "", "RAZORPAY_KEY_ID": "", "EXPECTED_SIGNING_SHA256": ""})
    assert len(found) >= 5


def test_main_exit_codes_and_github_error_annotations(monkeypatch, capsys):
    for k in GOOD:
        monkeypatch.setenv(k, GOOD[k])
    assert cr.main() == 0 and "release configuration OK" in capsys.readouterr().out
    monkeypatch.setenv("CERT_PINS", "")
    assert cr.main() == 1
    assert "::error::" in capsys.readouterr().out                              # shows up as an annotation on the run


# --- check_apk_signature ------------------------------------------------------------------------------------------------
def apksigner_output(*digests):
    lines = []
    for i, d in enumerate(digests, 1):
        lines += [f"Signer #{i} certificate DN: CN=Satark, O=Satark",
                  f"Signer #{i} certificate SHA-256 digest: {d}",
                  f"Signer #{i} certificate SHA-1 digest: " + "0" * 40,
                  f"Signer #{i} certificate MD5 digest: " + "1" * 32,
                  f"Signer #{i} key algorithm: RSA"]
    return "\n".join(lines) + "\n"


def test_signer_digests_ignore_sha1_and_md5_lines():
    assert ca.signer_digests(apksigner_output("ab" * 32)) == ["ab" * 32]


def test_signed_with_the_expected_certificate_passes():
    assert ca.check(apksigner_output("ab" * 32), "ab" * 32) == []
    assert ca.check(apksigner_output("cd" * 32), f"{'ab' * 32},{'cd' * 32}") == []          # a second digest (debug, while testing) is allowed


def test_wrong_certificate_is_rejected_with_the_consequence_spelled_out():
    found = ca.check(apksigner_output("cd" * 32), "ab" * 32)
    assert found and "NOT in the expected list" in found[0] and "reject every phone" in found[0]


def test_unsigned_apk_is_rejected():
    found = ca.check("", "ab" * 32)
    assert found and "unsigned" in found[0]


def test_every_signer_must_be_expected():
    assert ca.check(apksigner_output("ab" * 32, "cd" * 32), "ab" * 32)                       # a second, unexpected signer fails the build


def test_a_bad_expected_list_is_reported_not_crashed_on():
    assert "invalid" in ca.check(apksigner_output("ab" * 32), "not-a-digest")[0]


def test_find_apk_wants_exactly_one_signed_apk(tmp_path):
    with pytest.raises(FileNotFoundError):
        ca.find_apk(tmp_path)
    (tmp_path / "app-release.apk").write_bytes(b"x")
    assert ca.find_apk(tmp_path).name == "app-release.apk"
    (tmp_path / "other.apk").write_bytes(b"x")
    with pytest.raises(ValueError, match="exactly one"):
        ca.find_apk(tmp_path)
    (tmp_path / "other.apk").unlink()
    (tmp_path / "app-release.apk").rename(tmp_path / "app-release-unsigned.apk")
    with pytest.raises(ValueError, match="unsigned"):
        ca.find_apk(tmp_path)


def test_cli_modes(tmp_path, capsys):
    certs = tmp_path / "certs.txt"
    certs.write_text(apksigner_output("ab" * 32))
    assert ca.main(["--certs", str(certs), "--expected", "ab" * 32]) == 0
    assert ca.main(["--certs", str(certs), "--expected", "cd" * 32]) == 1
    assert ca.main(["--certs", str(certs)]) == 2
    assert ca.main(["--certs", str(tmp_path / "missing.txt"), "--expected", "ab" * 32]) == 1
    capsys.readouterr()
    (tmp_path / "app-release.apk").write_bytes(b"x")
    assert ca.main(["--find-apk", str(tmp_path)]) == 0 and capsys.readouterr().out.strip().endswith("app-release.apk")


# --- check_google_services ----------------------------------------------------------------------------------------------
import json as _json  # noqa: E402

import check_google_services as cg  # noqa: E402


def gs(package="com.satark.app", **over):
    d = {"project_info": {"project_number": "123456789", "project_id": "satark-demo"},
         "client": [{"client_info": {"mobilesdk_app_id": "1:123:android:abc", "android_client_info": {"package_name": package}},
                     "api_key": [{"current_key": "NOT-A-REAL-KEY"}]}]}
    d.update(over)
    return _json.dumps(d)


def test_a_matching_google_services_file_passes():
    assert cg.problems(gs()) == []


@pytest.mark.parametrize("raw,needle", [
    ("not json", "not valid JSON"),
    ("[]", "not a JSON object"),
    (gs(package="com.other.app"), "none of its client entries is for package com.satark.app"),
    (gs(client=[]), "no client entries"),
    (_json.dumps({"client": []}), "project_id"),
    (gs(project_info={"project_id": "x"}), "project_number"),
])
def test_each_wrong_google_services_file_is_explained(raw, needle):
    assert any(needle in p for p in cg.problems(raw)), cg.problems(raw)


def test_the_check_never_prints_the_file_contents(tmp_path, capsys):
    f = tmp_path / "google-services.json"
    f.write_text(gs(package="com.other.app"))
    assert cg.main([str(f)]) == 1
    out = capsys.readouterr().out
    assert "NOT-A-REAL-KEY" not in out and "123456789" not in out
    assert cg.main([str(tmp_path / "absent.json")]) == 1
    f.write_text(gs())
    assert cg.main([str(f)]) == 0
