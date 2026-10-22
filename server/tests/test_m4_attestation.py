"""Unit tests for the seven attestation checks in contracts/auth.md."""
import datetime as dt

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth.attestation import (AttestationError, AttestationPolicy, SecurityLevel,
                                  verify_attestation)
from app.auth.revocation import GoogleRevocationList, parse_status, serial_key
from app.auth.errors import AuthError

from .attestation_fixtures import DIGEST, PACKAGE, make_chain, random_challenge, tamper

EXPECTED_DIGESTS = frozenset({DIGEST.hex()})


def policy(chain, *, revoked=frozenset(), require_hardware=True, roots=None):
    return AttestationPolicy(
        roots=roots or [chain.root], expected_package=PACKAGE,
        expected_signing_sha256=EXPECTED_DIGESTS, revoked=lambda: revoked,
        require_hardware=require_hardware,
    )


def check(chain, challenge, *, der=None, spki=None, **policy_kw):
    return verify_attestation(der or chain.der, spki or chain.leaf_spki, challenge, policy(chain, **policy_kw))


def code(exc_info) -> str:
    return exc_info.value.code


def test_valid_tee_chain_accepted():
    ch = random_challenge()
    chain = make_chain(ch)
    result = check(chain, ch)
    assert result.security_level == SecurityLevel.TRUSTED_ENVIRONMENT
    assert result.unverified_boot is False


def test_strongbox_level_recorded():
    ch = random_challenge()
    chain = make_chain(ch, att_level=2, km_level=2)
    assert check(chain, ch).security_level == SecurityLevel.STRONGBOX


@pytest.mark.parametrize("boot_state", [1, 2, 3, None])
def test_unverified_boot_is_flagged_not_rejected(boot_state):
    ch = random_challenge()
    chain = make_chain(ch, boot_state=boot_state)
    result = check(chain, ch)
    assert result.unverified_boot is True
    assert result.verified_boot_state == boot_state


def test_modified_certificate_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    bad = [chain.der[0], tamper(chain.der[1]), chain.der[2]]
    with pytest.raises(AttestationError) as e:
        check(chain, ch, der=bad)
    assert code(e) == "chain_invalid"


def test_modified_leaf_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    bad = [tamper(chain.der[0]), chain.der[1], chain.der[2]]
    with pytest.raises(AttestationError) as e:
        check(chain, ch, der=bad)
    assert code(e) == "chain_invalid"


def test_chain_to_unknown_root_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    other = make_chain(random_challenge())
    with pytest.raises(AttestationError) as e:
        check(chain, ch, roots=[other.root])
    assert code(e) == "chain_untrusted"


def test_chain_without_root_but_issued_by_pinned_root_accepted():
    ch = random_challenge()
    chain = make_chain(ch)
    check(chain, ch, der=chain.der[:2])


def test_non_ca_intermediate_rejected():
    ch = random_challenge()
    chain = make_chain(ch, intermediate_is_ca=False)
    with pytest.raises(AttestationError) as e:
        check(chain, ch)
    assert code(e) == "chain_invalid"


def test_expired_intermediate_rejected():
    ch = random_challenge()
    chain = make_chain(ch, expired_intermediate=True)
    with pytest.raises(AttestationError) as e:
        check(chain, ch)
    assert code(e) == "chain_invalid"


def test_revoked_serial_rejected():
    ch = random_challenge()
    chain = make_chain(ch, leaf_serial=0x1234ABCD)
    with pytest.raises(AttestationError) as e:
        check(chain, ch, revoked=frozenset({serial_key(0x1234ABCD)}))
    assert code(e) == "cert_revoked"


def test_wrong_challenge_rejected():
    chain = make_chain(random_challenge())
    with pytest.raises(AttestationError) as e:
        check(chain, random_challenge())
    assert code(e) == "challenge_invalid"


def test_software_only_rejected_when_hardware_required():
    ch = random_challenge()
    chain = make_chain(ch, att_level=0, km_level=0)
    with pytest.raises(AttestationError) as e:
        check(chain, ch)
    assert code(e) == "software_only"


def test_software_keymaster_with_tee_attestation_rejected():
    ch = random_challenge()
    chain = make_chain(ch, att_level=1, km_level=0)
    with pytest.raises(AttestationError) as e:
        check(chain, ch)
    assert code(e) == "software_only"


def test_software_only_allowed_in_dev_policy():
    ch = random_challenge()
    chain = make_chain(ch, att_level=0, km_level=0)
    assert check(chain, ch, require_hardware=False).security_level == SecurityLevel.SOFTWARE


@pytest.mark.parametrize("kw", [
    {"packages": ("com.evil.app",)},
    {"packages": (PACKAGE, "com.other.app")},
    {"digests": (bytes.fromhex("cd" * 32),)},
    {"digests": (DIGEST, bytes.fromhex("cd" * 32))},
    {"digests": ()},
])
def test_wrong_app_identity_rejected(kw):
    ch = random_challenge()
    chain = make_chain(ch, **kw)
    with pytest.raises(AttestationError) as e:
        check(chain, ch)
    assert code(e) == "app_mismatch"


def test_public_key_mismatch_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    other = make_chain(random_challenge())
    with pytest.raises(AttestationError) as e:
        check(chain, ch, spki=other.leaf_spki)
    assert code(e) == "key_mismatch"


@pytest.mark.parametrize("der", [[b"junk", b"junk"], [b"\x30\x00", b"\x30\x00"]])
def test_garbage_certificates_rejected(der):
    chain = make_chain(random_challenge())
    with pytest.raises(AttestationError) as e:
        check(chain, b"x", der=der)
    assert code(e) == "malformed_attestation"


def test_single_certificate_chain_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    with pytest.raises(AttestationError) as e:
        check(chain, ch, der=chain.der[:1])
    assert code(e) == "malformed_attestation"


def test_oversized_chain_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    with pytest.raises(AttestationError) as e:
        check(chain, ch, der=chain.der * 3)
    assert code(e) == "malformed_attestation"


def test_leaf_without_attestation_extension_rejected():
    ch = random_challenge()
    chain = make_chain(ch)
    # An intermediate has no attestation extension; presenting it as the leaf must fail cleanly.
    with pytest.raises(AttestationError) as e:
        check(chain, ch, der=chain.der[1:])
    assert code(e) == "malformed_attestation"


# --- revocation list --------------------------------------------------------------------
def test_parse_status_normalises_serials():
    assert parse_status({"entries": {"00AbC": {"status": "REVOKED"}}}) == frozenset({"abc"})


def test_revocation_list_caches_and_serves_stale_on_outage():
    now = [1000.0]
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) > 1:
            raise OSError("google down")
        return {"entries": {"1": {}}}

    lst = GoogleRevocationList(fetch=fetch, ttl_s=60, clock=lambda: now[0])
    assert lst() == frozenset({"1"})
    now[0] += 30
    assert lst() == frozenset({"1"}) and len(calls) == 1        # cached
    now[0] += 120
    assert lst() == frozenset({"1"}) and len(calls) == 2        # refresh failed, stale served


def test_revocation_list_fails_closed_when_never_fetched():
    def fetch():
        raise OSError("down")

    with pytest.raises(AuthError) as e:
        GoogleRevocationList(fetch=fetch)()
    assert e.value.status_code == 503 and e.value.code == "attestation_unavailable"
