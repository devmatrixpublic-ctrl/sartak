"""Android Key Attestation verification (checks 1-7 in contracts/auth.md).

Everything here is pure: bytes in, AttestationResult or AttestationError out. Challenge
consumption and token issuing live in service.py.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Callable, Sequence

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from . import asn1
from .revocation import RevokedSerials, serial_key

KEY_ATTESTATION_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
TAG_ROOT_OF_TRUST = 704
TAG_ATTESTATION_APPLICATION_ID = 709
MAX_CHAIN_LEN = 6
MAX_CERT_BYTES = 8 * 1024


class SecurityLevel(IntEnum):
    SOFTWARE = 0
    TRUSTED_ENVIRONMENT = 1
    STRONGBOX = 2


class BootState(IntEnum):
    VERIFIED = 0
    SELF_SIGNED = 1
    UNVERIFIED = 2
    FAILED = 3


class AttestationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class KeyDescription:
    attestation_security_level: int
    keymaster_security_level: int
    challenge: bytes
    verified_boot_state: int | None
    package_names: tuple[str, ...]
    signing_digests: frozenset[str]          # lowercase hex SHA-256


@dataclass(frozen=True)
class AttestationPolicy:
    roots: Sequence[x509.Certificate]
    expected_package: str
    expected_signing_sha256: frozenset[str]
    revoked: RevokedSerials
    require_hardware: bool = True
    check_validity: bool = True
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


@dataclass(frozen=True)
class AttestationResult:
    security_level: SecurityLevel
    verified_boot_state: int | None
    unverified_boot: bool
    spki_der: bytes


def _bad(message: str) -> AttestationError:
    return AttestationError("malformed_attestation", message)


def load_roots_pem(pem_bundle: bytes) -> list[x509.Certificate]:
    roots = x509.load_pem_x509_certificates(pem_bundle)
    if not roots:
        raise ValueError("no certificates in roots bundle")
    return roots


def parse_chain(chain_der: Sequence[bytes]) -> list[x509.Certificate]:
    if not 2 <= len(chain_der) <= MAX_CHAIN_LEN:
        raise _bad("attestation chain must have 2 to 6 certificates")
    certs = []
    for raw in chain_der:
        if len(raw) > MAX_CERT_BYTES:
            raise _bad("certificate too large")
        try:
            certs.append(x509.load_der_x509_certificate(raw))
        except ValueError:
            raise _bad("certificate is not valid DER X.509")
    return certs


def parse_key_description(leaf: x509.Certificate) -> KeyDescription:
    try:
        ext = leaf.extensions.get_extension_for_oid(KEY_ATTESTATION_OID)
    except x509.ExtensionNotFound:
        raise _bad("leaf certificate has no key attestation extension")
    raw = ext.value.value  # UnrecognizedExtension -> DER bytes
    try:
        seq = asn1.expect(asn1.parse_one(raw), asn1.UNIVERSAL_SEQUENCE)
        f = asn1.children(seq)
        if len(f) < 8:
            raise asn1.DerError("KeyDescription too short")
        att_level = asn1.as_int(asn1.expect(f[1], asn1.UNIVERSAL_ENUMERATED))
        km_level = asn1.as_int(asn1.expect(f[3], asn1.UNIVERSAL_ENUMERATED))
        challenge = asn1.expect(f[4], asn1.UNIVERSAL_OCTET_STRING).value
        software = asn1.expect(f[6], asn1.UNIVERSAL_SEQUENCE)
        tee = asn1.expect(f[7], asn1.UNIVERSAL_SEQUENCE)
        fields = _auth_list(software) | _auth_list(tee)  # tee wins on clash
        boot_state = _boot_state(fields.get(TAG_ROOT_OF_TRUST))
        packages, digests = _app_id(fields.get(TAG_ATTESTATION_APPLICATION_ID))
    except asn1.DerError as exc:
        raise _bad(f"cannot parse attestation extension: {exc}")
    return KeyDescription(att_level, km_level, challenge, boot_state, packages, digests)


def _auth_list(seq: asn1.Tlv) -> dict[int, asn1.Tlv]:
    """AuthorizationList entries are [N] EXPLICIT, so each wraps exactly one inner TLV."""
    out: dict[int, asn1.Tlv] = {}
    for entry in asn1.children(seq):
        if entry.cls != asn1.CLASS_CONTEXT or not entry.constructed:
            continue
        inner = asn1.children(entry)
        if len(inner) == 1:
            out[entry.number] = inner[0]
    return out


def _boot_state(root_of_trust: asn1.Tlv | None) -> int | None:
    if root_of_trust is None:
        return None
    parts = asn1.children(asn1.expect(root_of_trust, asn1.UNIVERSAL_SEQUENCE))
    if len(parts) < 3:
        raise asn1.DerError("RootOfTrust too short")
    return asn1.as_int(asn1.expect(parts[2], asn1.UNIVERSAL_ENUMERATED))


def _app_id(octets: asn1.Tlv | None) -> tuple[tuple[str, ...], frozenset[str]]:
    if octets is None:
        return (), frozenset()
    body = asn1.expect(octets, asn1.UNIVERSAL_OCTET_STRING).value
    top = asn1.children(asn1.expect(asn1.parse_one(body), asn1.UNIVERSAL_SEQUENCE))
    if len(top) < 2:
        raise asn1.DerError("AttestationApplicationId too short")
    names: list[str] = []
    for info in asn1.children(asn1.expect(top[0], asn1.UNIVERSAL_SET)):
        name = asn1.expect(asn1.children(asn1.expect(info, asn1.UNIVERSAL_SEQUENCE))[0],
                           asn1.UNIVERSAL_OCTET_STRING)
        names.append(name.value.decode("utf-8", errors="replace"))
    digests = frozenset(
        asn1.expect(d, asn1.UNIVERSAL_OCTET_STRING).value.hex()
        for d in asn1.children(asn1.expect(top[1], asn1.UNIVERSAL_SET))
    )
    return tuple(names), digests


def _verify_chain(certs: list[x509.Certificate], policy: AttestationPolicy) -> None:
    now = policy.clock()
    if policy.check_validity:
        for c in certs:
            if not (c.not_valid_before_utc <= now <= c.not_valid_after_utc):
                raise AttestationError("chain_invalid", "A certificate in the chain is outside its validity period.")
    for child, issuer in zip(certs, certs[1:]):
        try:
            child.verify_directly_issued_by(issuer)
        except (InvalidSignature, ValueError, TypeError):
            raise AttestationError("chain_invalid", "Certificate chain signatures do not verify.")
    for issuer in certs[1:]:
        try:
            bc = issuer.extensions.get_extension_for_class(x509.BasicConstraints).value
        except x509.ExtensionNotFound:
            raise AttestationError("chain_invalid", "An issuing certificate is not a CA.")
        if not bc.ca:
            raise AttestationError("chain_invalid", "An issuing certificate is not a CA.")
    top = certs[-1]
    for root in policy.roots:
        if top == root:
            return
        try:
            top.verify_directly_issued_by(root)
            return
        except (InvalidSignature, ValueError, TypeError):
            continue
    raise AttestationError("chain_untrusted", "Certificate chain does not end at a trusted Google root.")


def verify_attestation(
    chain_der: Sequence[bytes],
    registered_spki_der: bytes,
    expected_challenge: bytes,
    policy: AttestationPolicy,
) -> AttestationResult:
    certs = parse_chain(chain_der)
    leaf = certs[0]

    _verify_chain(certs, policy)                                              # 1

    revoked = policy.revoked()                                                # 2
    if any(serial_key(c.serial_number) in revoked for c in certs):
        raise AttestationError("cert_revoked", "A certificate in the chain has been revoked.")

    kd = parse_key_description(leaf)
    if not hmac.compare_digest(kd.challenge, expected_challenge):             # 3
        raise AttestationError("challenge_invalid", "Attestation challenge does not match the issued challenge.")

    level = min(kd.attestation_security_level, kd.keymaster_security_level)   # 4
    if policy.require_hardware and level < SecurityLevel.TRUSTED_ENVIRONMENT:
        raise AttestationError("software_only", "Hardware-backed key attestation is required.")

    unverified = kd.verified_boot_state != BootState.VERIFIED                 # 5

    if (policy.expected_package not in kd.package_names                       # 6
            or len(kd.package_names) != 1
            or not (kd.signing_digests & policy.expected_signing_sha256)
            or not kd.signing_digests <= policy.expected_signing_sha256):
        raise AttestationError("app_mismatch", "Attestation was not produced by the Satark release app.")

    leaf_spki = leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    if not hmac.compare_digest(leaf_spki, registered_spki_der):               # 7
        raise AttestationError("key_mismatch", "Registered public key does not match the attested key.")

    return AttestationResult(SecurityLevel(min(level, SecurityLevel.STRONGBOX)),
                             kd.verified_boot_state, unverified, leaf_spki)


def device_id_for(spki_der: bytes) -> str:
    return hashlib.sha256(spki_der).hexdigest()[:32]
