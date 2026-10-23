from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.auth.config import validate_auth_settings
from app.auth.errors import AuthError, auth_error_handler
from app.auth.routes import router as auth_router
from app.core.limits import BodySizeLimitMiddleware
from app.core.errors import ApiError, api_error_handler, unhandled_error_handler, validation_error_handler
from app.core.logging import RequestCorrelationMiddleware, configure_logging
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.payments.jobs import TimeoutSweeper
from app.payments.service import DEFAULT_HANDED_OFF_TIMEOUT_SECONDS
from app.routers import alerts, health, payments, risk, signatures, trusted_contact, webhooks, device, admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    sweeper = TimeoutSweeper(SessionLocal, ttl_seconds=DEFAULT_HANDED_OFF_TIMEOUT_SECONDS)
    if not get_settings().is_dev:
        sweeper.start()
    yield
    sweeper.stop()


def create_app() -> FastAPI:
    configure_logging()
    validate_auth_settings(get_settings())    # refuse to boot with an unsafe auth config

    settings = get_settings()
    # Interactive docs and the schema are for dev only; the contract lives in contracts/api.yaml.
    docs = {} if settings.is_dev else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Satark Backend", version="0.1.0", lifespan=lifespan, **docs)
    app.add_middleware(RequestCorrelationMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes,
                       path_limits={"/webhooks/": settings.webhook_max_body_bytes})

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(AuthError, auth_error_handler)   # same body, plus WWW-Authenticate / Retry-After
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(risk.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    app.include_router(trusted_contact.router)
    app.include_router(alerts.router)
    app.include_router(signatures.router)
    app.include_router(device.router)
    app.include_router(admin.router)

    return app


app = create_app()
