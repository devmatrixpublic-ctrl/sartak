from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_device
from app.db.session import get_db
from app.signatures.schemas import SignatureIn
from app.signatures.service import store_signature

router = APIRouter(tags=["signatures"])


class SignatureOut(BaseModel):
    accepted: bool


@router.post("/signature", response_model=SignatureOut)
async def post_signature(
    body: SignatureIn,
    _device_id: str = Depends(require_device),
    db: Session = Depends(get_db),
) -> SignatureOut:
    store_signature(db, body.pattern_id, body.features)
    return SignatureOut(accepted=True)
