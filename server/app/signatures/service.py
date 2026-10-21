import json

from sqlalchemy.orm import Session

from app.db.models import Signature


def store_signature(db: Session, pattern_id: str, features: dict[str, float]) -> Signature:
    row = Signature(pattern_id=pattern_id, features_json=json.dumps(features, sort_keys=True))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
