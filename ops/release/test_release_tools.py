import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import make_keystore as mk  # noqa: E402
import set_github_secrets as sg  # noqa: E402
import signing_digest as sd  # noqa: E402

KEYTOOL = sd.find_keytool()
needs_keytool = pytest.mark.skipif(not KEYTOOL, reason="keytool (a JDK) is not installed here")
TEST_PW = "test-only-password-123"                     # a throwaway value for throwaway keystores in tmp dirs

GOOD_DIGEST = "ab" * 32
PIN_A = "sha256/" + "A" * 43 + "="
PIN_B = "sha256/" + "B" * 43 + "="


def make_test_keystore(tmp_path: Path, name="t.keystore") -> Path:
    ks = tmp_path / name
    subprocess.run([KEYTOOL, "-genkeypair", "-keystore", str(ks), "-alias", "satark-release", "-keyalg", "RSA", "-keysize", "2048",
                    "-validity", "30", "-dname", "CN=Test, O=Test", "-storepass", TEST_PW, "-keypass", TEST_PW],
                   check=True, capture_output=True)
    return ks


def keytool_sha256(ks: Path) -> str:
    out = subprocess.run([KEYTOOL, "-list", "-v", "-keystore", str(ks), "-alias", "satark-release", "-storepass", TEST_PW],
                         check=True, capture_output=True, text=True).stdout
    return sd.normalise(re.search(r"SHA256:\s*([0-9A-F:]+)", out).group(1))


# --- signing_digest ---------------------------------------------------------------------------------------------------
def test_normalise_turns_keytool_format_into_what_the_server_wants():
    assert sd.normalise("AB:CD:" + ":".join(["00"] * 30)) == "abcd" + "00" * 30
    assert sd.normalise(" " + GOOD_DIGEST.upper() + " ") == GOOD_DIGEST


@pytest.mark.parametrize("bad", ["", "abc", "zz" * 32, "ab" * 31, "ab" * 33])
def test_normalise_rejects_anything_that_is_not_a_sha256(bad):
    with pytest.raises(ValueError):
        sd.normalise(bad)


def test_check_list_accepts_one_or_several_and_rejects_the_silent_mistakes():
    assert sd.check_list(GOOD_DIGEST) == [GOOD_DIGEST]
    assert sd.check_list(f"{GOOD_DIGEST}, {'cd' * 32}") == [GOOD_DIGEST, "cd" * 32]
    with pytest.raises(ValueError, match="empty"):
        sd.check_list("  , ")
    with pytest.raises(ValueError, match="keytool format"):
        sd.check_list(":".join(["AB"] * 32))                       # colons and upper case would be silently useless on Render
    with pytest.raises(ValueError, match="64 lowercase"):
        sd.check_list(GOOD_DIGEST.upper())
    with pytest.raises(ValueError, match="twice"):
        sd.check_list(f"{GOOD_DIGEST},{GOOD_DIGEST}")


def _self_signed(tmp_path):
    import datetime as dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "t")])
    now = dt.datetime.now(dt.timezone.utc)
    c = x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(1) \
        .not_valid_before(now).not_valid_after(now + dt.timedelta(days=1)).sign(k, hashes.SHA256())
    return c.public_bytes(Encoding.PEM), c.public_bytes(Encoding.DER)


def test_pem_and_der_give_the_same_digest_and_it_is_sha256_of_the_der(tmp_path):
    pem, der = _self_signed(tmp_path)
    assert sd.digest_of(sd.certificate_der(pem)) == sd.digest_of(sd.certificate_der(der)) == hashlib.sha256(der).hexdigest()


def test_garbage_is_not_a_certificate():
    with pytest.raises(ValueError, match="not a valid X.509"):
        sd.certificate_der(b"hello")


def test_cli_cert_modes_and_check(tmp_path, capsys):
    pem, der = _self_signed(tmp_path)
    f = tmp_path / "c.pem"
    f.write_bytes(pem)
    assert sd.main(["--cert", str(f), "--format", "env"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == f"SATARK_AUTH_EXPECTED_SIGNING_SHA256={hashlib.sha256(der).hexdigest()}"
    assert sd.main(["--cert", str(f), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)[sd.ENV_NAME] == hashlib.sha256(der).hexdigest()
    assert sd.main(["--check", GOOD_DIGEST]) == 0
    assert sd.main(["--check", "nope"]) == 1
    assert sd.main(["--cert", str(tmp_path / "missing.pem")]) == 1                # a missing file is a clean failure, not a traceback


@needs_keytool
def test_digest_from_a_real_keystore_equals_what_keytool_itself_reports(tmp_path, monkeypatch):
    ks = make_test_keystore(tmp_path)
    monkeypatch.setenv("TEST_STOREPASS", TEST_PW)
    der = sd.certificate_der(sd.export_from_keystore(ks, "satark-release", KEYTOOL, TEST_PW))
    assert sd.digest_of(der) == keytool_sha256(ks)                          # independent confirmation from Java's own tool


@needs_keytool
def test_wrong_password_and_wrong_alias_fail_cleanly(tmp_path):
    ks = make_test_keystore(tmp_path)
    with pytest.raises(RuntimeError, match="could not read"):
        sd.export_from_keystore(ks, "satark-release", KEYTOOL, "wrong-password")
    with pytest.raises(RuntimeError, match="could not read"):
        sd.export_from_keystore(ks, "no-such-alias", KEYTOOL, TEST_PW)


@needs_keytool
def test_the_password_never_appears_on_the_keytool_command_line(tmp_path, monkeypatch):
    ks = make_test_keystore(tmp_path)
    seen = []
    real_run = subprocess.run

    def spy(cmd, *a, **k):
        seen.append(list(cmd))
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(sd.subprocess, "run", spy)
    sd.export_from_keystore(ks, "satark-release", KEYTOOL, TEST_PW)
    assert seen and all(TEST_PW not in part for cmd in seen for part in cmd)


# --- make_keystore ------------------------------------------------------------------------------------------------------
def test_refuses_to_create_a_keystore_inside_the_repo(tmp_path, capsys):
    inside = mk.REPO / "ops" / "release" / "should_never_exist.keystore"
    assert mk.main(["--out", str(inside), "--keytool", KEYTOOL or sys.executable]) == 2
    assert "inside the git repository" in capsys.readouterr().out
    assert not inside.exists()


def test_refuses_to_overwrite_an_existing_keystore(tmp_path, capsys):
    existing = tmp_path / "old.keystore"
    existing.write_bytes(b"precious")
    assert mk.main(["--out", str(existing), "--keytool", KEYTOOL or sys.executable]) == 2
    assert "already exists" in capsys.readouterr().out
    assert existing.read_bytes() == b"precious"


def test_refuses_a_weak_key_size(tmp_path, capsys):
    assert mk.main(["--out", str(tmp_path / "x.keystore"), "--keysize", "1024", "--keytool", KEYTOOL or sys.executable]) == 2


def test_build_command_passes_passwords_by_environment_not_value():
    cmd = mk.build_command("keytool", Path("k"), "a", 4096, 10000, "CN=T", "SP", "KP")
    assert "-storepass:env" in cmd and "-keypass:env" in cmd and "SP" in cmd
    assert "-storepass" not in cmd and "-keypass" not in cmd


@needs_keytool
def test_end_to_end_creates_a_keystore_and_prints_the_right_digest(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("T_STORE", TEST_PW)
    monkeypatch.setenv("T_KEY", TEST_PW)
    out = tmp_path / "sub" / "r.keystore"
    code = mk.main(["--out", str(out), "--keysize", "2048", "--keytool", KEYTOOL, "--dname", "CN=Test, O=Test",
                    "--storepass-env", "T_STORE", "--keypass-env", "T_KEY"])
    text = capsys.readouterr().out
    assert code == 0 and out.is_file()
    printed = re.search(r"SHA-256 \(public, safe to share\): ([0-9a-f]{64})", text).group(1)
    assert printed == keytool_sha256(out)
    assert TEST_PW not in text                                              # the password is never echoed
    assert mk.main(["--out", str(out), "--keytool", KEYTOOL]) == 2          # and a second run refuses to overwrite it


# --- set_github_secrets -------------------------------------------------------------------------------------------------
def write_pins(tmp_path, *lines):
    f = tmp_path / "pins.txt"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


def test_read_pins_accepts_the_generated_format_and_ignores_comments(tmp_path):
    f = write_pins(tmp_path, "# header", f"{PIN_A}  # primary", f"{PIN_B}  # backup", "")
    assert sg.read_pins(f) == [PIN_A, PIN_B]


@pytest.mark.parametrize("lines,msg", [
    ([f"{PIN_A}"], "at least two"),
    ([f"{PIN_A}", f"{PIN_A}"], "at least two"),
    ([f"{PIN_A}", "sha256/short"], "not a pin"),
    (["# only comments"], "at least two"),
])
def test_read_pins_refuses_unsafe_pin_files(tmp_path, lines, msg):
    with pytest.raises(ValueError, match=msg):
        sg.read_pins(write_pins(tmp_path, *lines))


def args(**kw):
    base = dict(repo="o/r", keystore=None, alias="satark-release", keystore_password_env=None, key_password_env=None, keytool=None,
                google_services=None, deploy_hook=False, deploy_hook_env=None, server_url=None, pins_file=None, razorpay_key_id=None,
                dry_run=True)
    base.update(kw)
    import argparse
    return argparse.Namespace(**base)


def test_plan_rules_https_testmode_and_nothing_to_do(tmp_path):
    with pytest.raises(ValueError, match="https"):
        sg.build_plan(args(server_url="http://insecure.example"))
    with pytest.raises(ValueError, match="TEST-mode"):
        sg.build_plan(args(razorpay_key_id="rzp_live_abcdef"))
    with pytest.raises(ValueError, match="nothing to do"):
        sg.build_plan(args())
    plan = sg.build_plan(args(server_url="https://x.onrender.com", razorpay_key_id="rzp_test_abc", pins_file=write_pins(tmp_path, PIN_A, PIN_B)))
    byname = {i.name: i for i in plan}
    assert byname["SATARK_SERVER_URL"].value == "https://x.onrender.com/"           # trailing slash normalised (the app builds URLs from it)
    assert byname["SATARK_CERT_PINS"].value == f"{PIN_A},{PIN_B}"
    assert all(i.kind == "variable" for i in plan)


def test_google_services_is_base64_encoded_secret(tmp_path):
    f = tmp_path / "google-services.json"
    f.write_text('{"project_info": {}}')
    (item,) = sg.build_plan(args(google_services=f))
    assert item.kind == "secret" and base64.b64decode(item.value) == f.read_bytes()


def test_describe_never_shows_values(tmp_path):
    f = tmp_path / "gs.json"
    f.write_text('{"private_key": "SUPER-SECRET-VALUE"}')
    text = sg.describe(sg.build_plan(args(google_services=f)))
    assert "SUPER-SECRET-VALUE" not in text and base64.b64encode(f.read_bytes()).decode() not in text


FAKE_GH = '''import json, os, sys
log = os.environ["FAKE_GH_LOG"]
rec = {"argv": sys.argv[1:], "stdin": sys.stdin.read()}
open(log, "a").write(json.dumps(rec) + "\\n")
sys.exit(1 if os.environ.get("FAKE_GH_FAIL") and sys.argv[3] == os.environ["FAKE_GH_FAIL"] else 0)
'''


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    script = tmp_path / "fake_gh.py"
    script.write_text(FAKE_GH)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    return [sys.executable, str(script)], log


def test_values_go_on_stdin_never_on_the_command_line(fake_gh):
    gh, log = fake_gh
    plan = [sg.Item("secret", "ANDROID_KEYSTORE_PASSWORD", "hunter2-not-real", "x"), sg.Item("variable", "SATARK_SERVER_URL", "https://x/", "y")]
    assert sg.apply_plan(plan, "o/r", gh) == ["ANDROID_KEYSTORE_PASSWORD", "SATARK_SERVER_URL"]
    records = [json.loads(l) for l in log.read_text().splitlines()]
    assert records[0]["argv"] == ["secret", "set", "ANDROID_KEYSTORE_PASSWORD", "--repo", "o/r"]
    assert records[0]["stdin"] == "hunter2-not-real" and records[1]["argv"][0] == "variable"
    assert all("hunter2-not-real" not in " ".join(r["argv"]) for r in records)


def test_the_first_failure_stops_the_run_and_names_the_item(fake_gh, monkeypatch):
    gh, log = fake_gh
    monkeypatch.setenv("FAKE_GH_FAIL", "SECOND")
    plan = [sg.Item("secret", n, "v", "s") for n in ("FIRST", "SECOND", "THIRD")]
    with pytest.raises(RuntimeError, match="SECOND"):
        sg.apply_plan(plan, "o/r", gh)
    assert [json.loads(l)["argv"][2] for l in log.read_text().splitlines()] == ["FIRST", "SECOND"]       # THIRD never sent


def test_a_missing_value_is_an_error_not_an_empty_secret(fake_gh):
    gh, _ = fake_gh
    with pytest.raises(RuntimeError, match="no value"):
        sg.apply_plan([sg.Item("secret", "X", None, "s")], "o/r", gh)


def test_confirmation_must_be_the_exact_repo_name():
    assert sg.confirmed("o/r", "o/r") and sg.confirmed(" o/r \n", "o/r")
    assert not sg.confirmed("", "o/r") and not sg.confirmed("yes", "o/r") and not sg.confirmed("O/R", "o/r")


def test_dry_run_cli_sends_nothing_and_prints_no_values(tmp_path, capsys):
    gs = tmp_path / "gs.json"
    gs.write_text('{"k": "VERY-SECRET"}')
    assert sg.main(["--repo", "o/r", "--google-services", str(gs), "--server-url", "https://x.example", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "GOOGLE_SERVICES_JSON_BASE64" in out and "VERY-SECRET" not in out
    assert sg.main(["--repo", "not a repo", "--server-url", "https://x", "--dry-run"]) == 2


@needs_keytool
def test_keystore_dry_run_derives_the_digest_from_the_keystore(tmp_path, monkeypatch, capsys):
    ks = make_test_keystore(tmp_path)
    monkeypatch.setenv("KS_PW", TEST_PW)
    plan = sg.build_plan(args(keystore=ks, keystore_password_env="KS_PW", key_password_env="KS_PW", keytool=KEYTOOL))
    byname = {i.name: i for i in plan}
    assert byname["SATARK_EXPECTED_SIGNING_SHA256"].value == keytool_sha256(ks)
    assert base64.b64decode(byname["ANDROID_KEYSTORE_BASE64"].value) == ks.read_bytes()
    assert set(byname) == {"ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD", "SATARK_EXPECTED_SIGNING_SHA256"}
    assert TEST_PW not in sg.describe(plan)


# --- pins_value ---------------------------------------------------------------------------------------------------------
def test_pins_value_prints_the_gradle_value_and_refuses_unsafe_files(tmp_path, capsys):
    import pins_value as pv
    good = write_pins(tmp_path, f"{PIN_A}  # primary", f"{PIN_B}  # backup")
    assert pv.main(["--file", str(good)]) == 0 and capsys.readouterr().out.strip() == f"{PIN_A},{PIN_B}"
    assert pv.main(["--file", str(good), "--gradle"]) == 0 and capsys.readouterr().out.strip() == f"-PsatarkPins={PIN_A},{PIN_B}"
    assert pv.main(["--file", str(write_pins(tmp_path, PIN_A))]) == 1                      # one pin is refused
    assert pv.main(["--file", str(tmp_path / "absent.txt")]) == 1                         # absent file: says how to generate it
    assert "does not exist yet" in capsys.readouterr().out
