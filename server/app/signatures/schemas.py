import math
import re

from typing import Annotated

from pydantic import Field, field_validator

from app.core.schemas import StrictInput

PATTERN_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# Feature keys that could carry raw personal data are rejected outright,
# matched as a case-insensitive substring. Deliberately narrower than the
# detector's own vocabulary (contracts/schema.json's FeatureExtractor uses
# words like "payee" and "contact" in abstract/hashed feature names such as
# unk_contact_recent, new_payee, repeat_to_payee — those are legitimate and
# must not be blocked here). This list targets substrings that only show up
# when something raw has been smuggled in: a literal phone number, VPA,
# email, postal address, or device identifier.
DISALLOWED_KEY_SUBSTRINGS = (
    "phone",
    "number",
    "name",
    "amount",
    "vpa",
    "email",
    "address",
    "device_id",
    "imei",
    "account",
)


class SignatureIn(StrictInput):
    pattern_id: str
    features: dict[Annotated[str, Field(min_length=1, max_length=64)], float]

    @field_validator("pattern_id")
    @classmethod
    def validate_pattern_id(cls, v: str) -> str:
        if not PATTERN_ID_RE.match(v):
            raise ValueError("pattern_id must be 1-64 alphanumeric/underscore/hyphen characters")
        return v

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("features must not be empty")
        if len(v) > 64:
            raise ValueError("features must not exceed 64 entries")
        if not all(math.isfinite(x) for x in v.values()):
            raise ValueError("feature values must be finite numbers")
        lowered = {k.lower() for k in v}
        for bad in DISALLOWED_KEY_SUBSTRINGS:
            if any(bad in key for key in lowered):
                raise ValueError(f"feature key must not reference personal data (matched {bad!r})")
        return v
