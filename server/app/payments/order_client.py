"""Minimal Razorpay Orders API client.

Falls back to a local deterministic order id when no API keys are
configured (dev/test), so the payment flow is exercisable without real
Razorpay credentials. Real deploys (P6) must set the keys via env vars.
"""

import uuid
from typing import Protocol

import httpx

from app.core.settings import Settings


class OrderClient(Protocol):
    def create_order(self, amount: float, currency: str, receipt: str) -> str: ...


class RazorpayOrderClient:
    def __init__(self, key_id: str, key_secret: str):
        self._key_id = key_id
        self._key_secret = key_secret

    def create_order(self, amount: float, currency: str, receipt: str) -> str:
        resp = httpx.post(
            "https://api.razorpay.com/v1/orders",
            auth=(self._key_id, self._key_secret),
            json={"amount": int(round(amount * 100)), "currency": currency, "receipt": receipt},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["id"]


class LocalStubOrderClient:
    """Used when Razorpay keys aren't configured (local dev, CI)."""

    def create_order(self, amount: float, currency: str, receipt: str) -> str:
        return f"order_local_{uuid.uuid4().hex[:16]}"


def get_order_client(settings: Settings) -> OrderClient:
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        return RazorpayOrderClient(settings.razorpay_key_id, settings.razorpay_key_secret)
    return LocalStubOrderClient()
