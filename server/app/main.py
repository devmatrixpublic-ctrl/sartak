from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.errors import ApiError, api_error_handler, unhandled_error_handler, validation_error_handler
from app.core.logging import RequestCorrelationMiddleware, configure_logging
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.payments.jobs import TimeoutSweeper
from app.payments.service import DEFAULT_HANDED_OFF_TIMEOUT_SECONDS
from app.routers import alerts, health, payments, risk, signatures, trusted_contact, webhooks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    sweeper = TimeoutSweeper(SessionLocal, ttl_seconds=DEFAULT_HANDED_OFF_TIMEOUT_SECONDS)
    if not get_settings().is_dev:
        sweeper.start()
    yield
    sweeper.stop()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Satark Backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestCorrelationMiddleware)

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(risk.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    app.include_router(trusted_contact.router)
    app.include_router(alerts.router)
    app.include_router(signatures.router)

    return app


app = create_app()
