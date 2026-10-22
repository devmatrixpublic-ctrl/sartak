"""Minimal DER reader: just enough to read the Android Key Attestation extension.

Not a general ASN.1 library. Strict on purpose: truncation, indefinite lengths and
oversized tags are errors, because the input comes from an untrusted phone.
"""
from __future__ import annotations

from dataclasses import dataclass

UNIVERSAL_INTEGER = 2
UNIVERSAL_OCTET_STRING = 4
UNIVERSAL_ENUMERATED = 10
UNIVERSAL_SEQUENCE = 16
UNIVERSAL_SET = 17

CLASS_UNIVERSAL = 0
CLASS_CONTEXT = 2

_MAX_TAG_BYTES = 4


class DerError(ValueError):
    pass


@dataclass(frozen=True)
class Tlv:
    cls: int
    constructed: bool
    number: int
    value: bytes


def read_tlv(buf: bytes, pos: int = 0) -> tuple[Tlv, int]:
    if pos >= len(buf):
        raise DerError("truncated tag")
    first = buf[pos]
    pos += 1
    cls = first >> 6
    constructed = bool(first & 0x20)
    number = first & 0x1F
    if number == 0x1F:
        number = 0
        for _ in range(_MAX_TAG_BYTES):
            if pos >= len(buf):
                raise DerError("truncated tag number")
            b = buf[pos]
            pos += 1
            number = (number << 7) | (b & 0x7F)
            if not b & 0x80:
                break
        else:
            raise DerError("tag number too long")
    if pos >= len(buf):
        raise DerError("truncated length")
    length = buf[pos]
    pos += 1
    if length & 0x80:
        n = length & 0x7F
        if n == 0 or n > 4:
            raise DerError("unsupported length form")
        if pos + n > len(buf):
            raise DerError("truncated length")
        length = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    end = pos + length
    if end > len(buf):
        raise DerError("truncated value")
    return Tlv(cls, constructed, number, buf[pos:end]), end


def parse_one(buf: bytes) -> Tlv:
    tlv, end = read_tlv(buf, 0)
    if end != len(buf):
        raise DerError("trailing bytes")
    return tlv


def children(tlv: Tlv) -> list[Tlv]:
    out: list[Tlv] = []
    pos = 0
    while pos < len(tlv.value):
        child, pos = read_tlv(tlv.value, pos)
        out.append(child)
    return out


def expect(tlv: Tlv, number: int, cls: int = CLASS_UNIVERSAL) -> Tlv:
    if tlv.cls != cls or tlv.number != number:
        raise DerError(f"expected tag {cls}/{number}, got {tlv.cls}/{tlv.number}")
    return tlv


def as_int(tlv: Tlv) -> int:
    if not tlv.value:
        raise DerError("empty integer")
    return int.from_bytes(tlv.value, "big", signed=True)


def as_bool(tlv: Tlv) -> bool:
    if len(tlv.value) != 1:
        raise DerError("bad boolean")
    return tlv.value[0] != 0
