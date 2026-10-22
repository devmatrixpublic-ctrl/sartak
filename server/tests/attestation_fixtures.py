"""Synthetic Android Key Attestation chains for tests.

Real X.509 certificates, signed with real keys, carrying a hand-encoded KeyDescription
extension. This exercises the verifier's parsing and chain logic end to end. It does NOT
replace the chains captured from the two physical phones (contracts/auth.md, check list in
ops/security/checklist.md): those prove we agree with real Keystore output.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.x509.oid import NameOID

OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
PACKAGE = "com.satark.app"
DIGEST = bytes.fromhex("ab" * 32)


# --- tiny DER encoder -------------------------------------------------------------------
def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(cls: int, constructed: bool, number: int, content: bytes) -> bytes:
    first = (cls << 6) | (0x20 if constructed else 0)
    if number < 31:
        head = bytes([first | number])
    else:
        parts = []
        n = number
        while n:
            parts.append(n & 0x7F)
            n >>= 7
        enc = bytes([p | 0x80 for p in reversed(parts[1:])] + [parts[0]]) if len(parts) > 1 else bytes(parts)
        head = bytes([first | 0x1F]) + enc
    return head + _len(len(content)) + content


def der_int(v: int) -> bytes:
    return tlv(0, False, 2, v.to_bytes(v.bit_length() // 8 + 1, "big", signed=True))


def der_enum(v: int) -> bytes:
    return tlv(0, False, 10, bytes([v]))


def der_bool(v: bool) -> bytes:
    return tlv(0, False, 1, b"\xff" if v else b"\x00")


def der_octets(b: bytes) -> bytes:
    return tlv(0, False, 4, b)


def der_seq(*items: bytes) -> bytes:
    return tlv(0, True, 16, b"".join(items))


def der_set(*items: bytes) -> bytes:
    return tlv(0, True, 17, b"".join(items))


def explicit(number: int, inner: bytes) -> bytes:
    return tlv(2, True, number, inner)


def key_description(
    challenge: bytes,
    *,
    att_level: int = 1,
    km_level: int = 1,
    boot_state: int | None = 0,
    packages: tuple[str, ...] = (PACKAGE,),
    digests: tuple[bytes, ...] = (DIGEST,),
) -> bytes:
    app_id = der_seq(
        der_set(*[der_seq(der_octets(p.encode()), der_int(1)) for p in packages]),
        der_set(*[der_octets(d) for d in digests]),
    )
    software = der_seq(explicit(709, der_octets(app_id)))
    tee_items = []
    if boot_state is not None:
        tee_items.append(explicit(704, der_seq(der_octets(b"k" * 32), der_bool(True),
                                               der_enum(boot_state), der_octets(b"h" * 32))))
    return der_seq(der_int(4), der_enum(att_level), der_int(4), der_enum(km_level),
                   der_octets(challenge), der_octets(b""), software, der_seq(*tee_items))


# --- certificate chain ------------------------------------------------------------------
@dataclass
class Chain:
    root: x509.Certificate
    der: list[bytes]                 # leaf first, root last (what the phone sends)
    leaf_spki: bytes
    certs: list[x509.Certificate] = field(default_factory=list)


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, pub, signer, *, ca, serial=None, ext=None, nb=None, na=None):
    now = dt.datetime.now(dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(pub)
         .serial_number(serial or x509.random_serial_number())
         .not_valid_before(nb or now - dt.timedelta(days=1))
         .not_valid_after(na or now + dt.timedelta(days=1)))
    if ca is not None:
        b = b.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    if ext is not None:
        b = b.add_extension(x509.UnrecognizedExtension(OID, ext), critical=False)
    return b.sign(signer, hashes.SHA256())


def make_chain(
    challenge: bytes,
    *,
    root_key=None,
    leaf_key=None,
    intermediate_is_ca: bool = True,
    leaf_serial: int | None = None,
    expired_intermediate: bool = False,
    **kd_kwargs,
) -> Chain:
    root_key = root_key or ec.generate_private_key(ec.SECP256R1())
    inter_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = leaf_key or ec.generate_private_key(ec.SECP256R1())
    root = _cert(_name("Test Root"), _name("Test Root"), root_key.public_key(), root_key, ca=True)
    now = dt.datetime.now(dt.timezone.utc)
    inter = _cert(_name("Test Inter"), _name("Test Root"), inter_key.public_key(), root_key,
                  ca=intermediate_is_ca,
                  nb=now - dt.timedelta(days=30) if expired_intermediate else None,
                  na=now - dt.timedelta(days=1) if expired_intermediate else None)
    leaf = _cert(_name("Android Keystore Key"), _name("Test Inter"), leaf_key.public_key(), inter_key,
                 ca=False, serial=leaf_serial, ext=key_description(challenge, **kd_kwargs))
    certs = [leaf, inter, root]
    return Chain(root, [c.public_bytes(Encoding.DER) for c in certs],
                 leaf_key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo), certs)


def tamper(der: bytes) -> bytes:
    """Flip one bit inside the signature (last bytes) so the certificate still parses."""
    b = bytearray(der)
    b[-5] ^= 0x01
    return bytes(b)


def random_challenge() -> bytes:
    return os.urandom(32)
