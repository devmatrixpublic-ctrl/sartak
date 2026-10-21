"""Reference mapping from a `upi://pay` URI to a schema.json PAYMENT_ATTEMPT event (plan 2.1).

This documents the rules the schema fixes (P2P/P2M, hashed VPA, amount from `am`, source qr|manual). The production
parser is M1's UpiUriParser (contracts/upi.md); M1's tests and this module must agree on these cases.
"""
from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlsplit


class NotUpiUri(ValueError):
    pass


def hash_vpa(vpa: str, salt: bytes) -> str:
    """HMAC-SHA256 hex of the lower-cased VPA with a per-install salt. The raw VPA is never stored or sent."""
    return hmac.new(salt, vpa.strip().lower().encode(), hashlib.sha256).hexdigest()


def parse_upi_uri(uri: str, salt: bytes, t_ms: int, known_payee_hashes: set[str], typed_amount: float | None = None,
                  source: str = "qr") -> dict:
    parts = urlsplit(uri.strip())
    if parts.scheme.lower() != "upi" or parts.netloc.lower() != "pay":
        raise NotUpiUri(f"not a upi://pay URI: {uri!r}")
    q = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
    pa = q.get("pa", "").strip()
    if not pa or "@" not in pa or pa.count("@") != 1 or pa.startswith("@") or pa.endswith("@"):
        raise NotUpiUri("missing or malformed payee VPA (pa)")
    if q.get("cu", "INR").upper() != "INR":
        raise NotUpiUri("only INR is supported")
    if q.get("am"):
        try:
            amount = float(q["am"])
        except ValueError as e:
            raise NotUpiUri("malformed amount (am)") from e
    elif typed_amount is not None:
        amount = float(typed_amount)
    else:
        raise NotUpiUri("amount missing: the user must enter it")
    if not (amount >= 0 and amount == amount and amount != float("inf")):
        raise NotUpiUri("amount must be a finite non-negative number")
    h = hash_vpa(pa, salt)
    return {
        "event_type": "PAYMENT_ATTEMPT",
        "t_ms": t_ms,
        "payee_id": h,
        "payee_is_new": h not in known_payee_hashes,
        "amount_inr": amount,
        "payment_type": "P2M" if q.get("mc") else "P2P",
        "source": source,
    }
