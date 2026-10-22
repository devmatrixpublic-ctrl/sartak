"""Reference mapping from a `upi://pay` URI to a schema.json PAYMENT_ATTEMPT event (plan 2.1).

This documents the rules the schema fixes (P2P/P2M, hashed VPA, amount from `am`, source qr|manual) and follows
contracts/upi.md, which M1 owns. The production parser is M1's UpiUriParser; both must agree on these cases.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlsplit


class NotUpiUri(ValueError):
    pass


_VPA = re.compile(r"^[A-Za-z0-9._-]{2,256}@[A-Za-z][A-Za-z0-9.-]{1,63}$")
_AMOUNT = re.compile(r"^\d{1,9}(\.\d{1,2})?$")


def hash_vpa(vpa: str, salt: bytes) -> str:
    """contracts/upi.md: lowercase hex SHA-256(install_salt || lowercase(trim(pa))). The raw VPA is never stored or sent."""
    return hashlib.sha256(salt + vpa.strip().lower().encode()).hexdigest()


def parse_upi_uri(uri: str, salt: bytes, t_ms: int, known_payee_hashes: set[str], typed_amount: float | None = None,
                  source: str = "qr") -> dict:
    parts = urlsplit(uri.strip())
    if parts.scheme.lower() != "upi" or parts.netloc.lower() != "pay":
        raise NotUpiUri(f"not a upi://pay URI: {uri!r}")
    q = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
    pa = q.get("pa", "").strip()
    if not _VPA.match(pa):
        raise NotUpiUri("missing or malformed payee VPA (pa)")
    if q.get("cu", "INR").upper() != "INR":
        raise NotUpiUri("only INR is supported")
    am = q.get("am", "").strip()
    if am:
        if not _AMOUNT.match(am):
            raise NotUpiUri("malformed amount (am): decimal, at most 2 places")
        amount = float(am)
        if amount <= 0:
            raise NotUpiUri("amount must be positive")
    elif typed_amount is not None:
        amount = float(typed_amount)
    else:
        raise NotUpiUri("amount missing: the user must enter it")
    if not (amount > 0 and amount != float("inf")):
        raise NotUpiUri("amount must be a positive finite number")
    h = hash_vpa(pa, salt)
    return {
        "event_type": "PAYMENT_ATTEMPT",
        "t_ms": t_ms,
        "payee_id": h,
        "payee_is_new": h not in known_payee_hashes,
        "amount_inr": amount,
        "payment_type": "P2M" if q.get("mc", "").strip() else "P2P",
        "source": source,
    }
