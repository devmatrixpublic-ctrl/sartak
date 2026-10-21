import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Device, WebhookEvent


def test_webhook_event_id_is_unique(db_session):
    db_session.add(WebhookEvent(event_id="evt_1", payload_hash="h1"))
    db_session.commit()

    db_session.add(WebhookEvent(event_id="evt_1", payload_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_data_survives_session_restart(db_session, db_engine):
    db_session.add(
        Device(
            public_key="pk-1",
            attestation_level="TEE",
            verified_boot_state="verified",
            role="device",
        )
    )
    db_session.commit()
    db_session.close()

    from sqlalchemy.orm import sessionmaker

    NewSession = sessionmaker(bind=db_engine, future=True)
    with NewSession() as fresh:
        devices = fresh.query(Device).all()
        assert len(devices) == 1
        assert devices[0].public_key == "pk-1"
