import json
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.payments.webhook import apply_webhook_event, record_event_once, verify_signature

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger("satark.webhooks")


@router.post("/webhooks/razorpay", status_code=200)
async def post_razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    event_id = request.headers.get("X-Razorpay-Event-Id", "")

    if not settings.razorpay_webhook_secret:
        raise ApiError(400, "webhook_not_configured", "Webhook secret is not configured")

    if not verify_signature(raw_body, signature, settings.razorpay_webhook_secret):
        logger.warning("razorpay_webhook_forged_signature", extra={"event_id": event_id})
        raise ApiError(400, "invalid_signature", "Signature verification failed")

    if not event_id:
        raise ApiError(400, "missing_event_id", "X-Razorpay-Event-Id header is required")

    is_first_delivery = record_event_once(db, event_id, raw_body)
    if not is_first_delivery:
        return {"status": "already_processed"}

    try:
        payload = json.loads(raw_body)
    except ValueError as exc:
        raise ApiError(400, "malformed_payload", "Webhook body is not valid JSON") from exc

    apply_webhook_event(db, payload)
    return {"status": "processed"}
