import base64
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "server" / "tests"))

import verify_captured_chain as vc  # noqa: E402
from attestation_fixtures import DIGEST, PACKAGE, make_chain  # noqa: E402

CHALLENGE = bytes(range(32))


def b64(b):
    return base64.b64encode(b).decode()


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Case:
    """A synthetic phone: a real X.509 chain plus the export JSON M1's debug build would write."""

    def __init__(self, tmp_path, name="phone.json", *, chain_kw=None, export_digest=None, challenge_in_export=CHALLENGE, swap_key=False,
                 level="TEE", other_root=False):
        self.root_key = ec.generate_private_key(ec.SECP256R1())
        self.chain = make_chain(CHALLENGE, root_key=self.root_key, **(chain_kw or {}))
        pub = self.chain.leaf_spki
        if swap_key:
            pub = make_chain(CHALLENGE).leaf_spki
        self.export = {
            "format": vc.FORMAT, "captured_at": "2026-10-24T10:00:00Z",
            "device": {"manufacturer": "TestCo", "model": "T1", "sdk_int": 35, "release": "15", "security_patch": "2026-10-01", "strongbox_feature": False},
            "app": {"package": PACKAGE, "version_name": "0.1", "build_type": "debug", "signing_cert_sha256": [export_digest or DIGEST.hex()]},
            "key_security_level": level, "challenge": b64url(challenge_in_export), "challenge_source": "local",
            "public_key": b64(pub), "attestation_chain": [b64(c) for c in self.chain.der],
        }
        self.path = tmp_path / name
        self.path.write_text(json.dumps(self.export))
        root_pem = (make_chain(CHALLENGE).root if other_root else self.chain.root).public_bytes(Encoding.PEM)
        self.roots = tmp_path / f"roots_{name}.pem"
        self.roots.write_bytes(root_pem)

    def run(self, capsys, *extra, expect=None):
        argv = [str(self.path), "--roots", str(self.roots), "--skip-revocation", *extra]
        code = vc.main(argv)
        out = capsys.readouterr().out
        if expect is not None:
            assert code == expect, out
        return code, out


def line(out, prefix):
    return next(l for l in out.splitlines() if prefix in l)


def test_a_good_chain_is_accepted_and_every_check_is_shown_as_passing(tmp_path, capsys):
    code, out = Case(tmp_path).run(capsys, expect=0)
    assert "SERVER VERDICT: ACCEPT" in out
    for n in ("1  Chain", "3  Challenge", "4  Key is hardware", "6a", "6b", "7  Certificate key"):
        assert "[PASS]" in line(out, n), out
    assert "TestCo T1" in out                                                   # says which phone it is


def test_wrong_package_is_rejected_and_named(tmp_path, capsys):
    code, out = Case(tmp_path, chain_kw={"packages": ("com.evil.app",)}).run(capsys, expect=1)
    assert "[FAIL]" in line(out, "6a") and "com.evil.app" in out and "REJECT (app_mismatch" in out


def test_a_different_signing_certificate_gets_the_actionable_hint(tmp_path, capsys):
    code, out = Case(tmp_path, export_digest="cd" * 32).run(capsys, expect=1)       # the chain says DIGEST, the build's own digest says cd..
    assert "[FAIL]" in line(out, "6b") and "SATARK_AUTH_EXPECTED_SIGNING_SHA256" in line(out, "6b")


def test_passing_the_release_digest_explicitly_overrides_the_exports_own(tmp_path, capsys):
    c = Case(tmp_path, export_digest="cd" * 32)
    c.run(capsys, "--expected-digests", DIGEST.hex(), expect=0)
    code, _ = c.run(capsys, "--expected-digests", "ef" * 32)
    assert code == 1


def test_an_emulator_chain_is_rejected_with_a_hint_and_inspectable_with_allow_software(tmp_path, capsys):
    c = Case(tmp_path, chain_kw={"att_level": 0, "km_level": 0}, level="software")
    code, out = c.run(capsys, expect=1)
    assert "[FAIL]" in line(out, "4  Key is hardware") and "emulator" in out and "REJECT (software_only" in out
    c.run(capsys, "--allow-software", expect=0)


def test_a_chain_to_an_unknown_root_shows_the_top_certificate_fingerprint_and_the_pinned_ones(tmp_path, capsys):
    code, out = Case(tmp_path, other_root=True).run(capsys, expect=1)
    l = line(out, "1  Chain")
    assert "[FAIL]" in l and "chain_untrusted" in out and "pinned roots are" in l


def test_a_challenge_that_differs_from_the_exported_one_is_caught(tmp_path, capsys):
    code, out = Case(tmp_path, challenge_in_export=bytes(32)).run(capsys, expect=1)
    assert "[FAIL]" in line(out, "3  Challenge") and "DIFFER" in out and "challenge_invalid" in out


def test_an_exported_key_that_is_not_the_attested_key_is_caught(tmp_path, capsys):
    code, out = Case(tmp_path, swap_key=True).run(capsys, expect=1)
    assert "[FAIL]" in line(out, "7  Certificate key") and "key_mismatch" in out


def test_unverified_boot_is_accepted_but_clearly_flagged(tmp_path, capsys):
    code, out = Case(tmp_path, chain_kw={"boot_state": 2}).run(capsys, expect=0)
    assert "Unverified" in line(out, "5  Verified boot") and "unverified_boot=True" in out


def test_all_failures_are_reported_in_one_run_not_just_the_first(tmp_path, capsys):
    code, out = Case(tmp_path, chain_kw={"packages": ("com.evil.app",), "att_level": 0, "km_level": 0}, level="software").run(capsys, expect=1)
    assert out.count("[FAIL]") >= 2 and "[FAIL]" in line(out, "4  Key") and "[FAIL]" in line(out, "6a")


def test_revocation_list_file_is_honoured(tmp_path, capsys):
    c = Case(tmp_path, chain_kw={"leaf_serial": 0x1234ABCD})
    listing = tmp_path / "status.json"
    listing.write_text(json.dumps({"entries": {"1234abcd": {"status": "REVOKED"}}}))
    argv = [str(c.path), "--roots", str(c.roots), "--revocation-file", str(listing)]
    assert vc.main(argv) == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in line(out, "2  Not revoked") and "REVOKED" in out and "cert_revoked" in out
    listing.write_text(json.dumps({"entries": {"ffff": {}}}))
    assert vc.main(argv) == 0


def test_two_phones_get_a_summary_and_one_bad_phone_fails_the_run(tmp_path, capsys):
    good = Case(tmp_path, "good.json")
    bad = Case(tmp_path, "bad.json", chain_kw={"packages": ("com.evil.app",)})
    # the two cases use different roots, so pin both in one bundle
    both = tmp_path / "both.pem"
    both.write_bytes(good.chain.root.public_bytes(Encoding.PEM) + bad.chain.root.public_bytes(Encoding.PEM))
    code = vc.main([str(good.path), str(bad.path), "--roots", str(both), "--skip-revocation"])
    out = capsys.readouterr().out
    assert code == 1 and "Summary: good.json: ACCEPT, bad.json: REJECT" in out


def test_json_output_is_machine_readable(tmp_path, capsys):
    c = Case(tmp_path)
    assert vc.main([str(c.path), "--roots", str(c.roots), "--skip-revocation", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["verdict"] == "ACCEPT" and any(ch["name"].startswith("1") and ch["ok"] for ch in data[0]["checks"])


def test_bad_inputs_fail_cleanly(tmp_path, capsys):
    c = Case(tmp_path)
    garbage = tmp_path / "g.json"
    garbage.write_text("{}")
    assert vc.main([str(garbage), "--roots", str(c.roots), "--skip-revocation"]) == 1
    assert "not a satark-attestation-export/1 file" in capsys.readouterr().out
    assert vc.main([str(c.path), "--roots", str(tmp_path / "absent.pem"), "--skip-revocation"]) == 2
    assert "cannot load the pinned roots" in capsys.readouterr().out
    assert vc.main([str(tmp_path / "missing.json"), "--roots", str(c.roots), "--skip-revocation"]) == 1


def test_the_tool_agrees_with_the_servers_own_verifier_on_every_case(tmp_path, capsys):
    """The verdict line IS the server's verify_attestation result: for a spread of chains the two must never disagree."""
    from app.auth import attestation as att
    cases = [dict(), dict(chain_kw={"packages": ("x",)}), dict(chain_kw={"att_level": 0, "km_level": 0}), dict(other_root=True), dict(swap_key=True)]
    for i, kw in enumerate(cases):
        c = Case(tmp_path, f"c{i}.json", **kw)
        code, out = c.run(capsys)
        roots = att.load_roots_pem(c.roots.read_bytes())
        policy = att.AttestationPolicy(roots=roots, expected_package=PACKAGE, expected_signing_sha256=frozenset({DIGEST.hex()}),
                                       revoked=lambda: frozenset(), require_hardware=True)
        try:
            att.verify_attestation([base64.b64decode(x) for x in c.export["attestation_chain"]], base64.b64decode(c.export["public_key"]), CHALLENGE, policy)
            server = "ACCEPT"
        except att.AttestationError:
            server = "REJECT"
        assert f"SERVER VERDICT: {server}" in out, (i, out)
