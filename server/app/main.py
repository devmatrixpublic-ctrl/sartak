from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.errors import ApiError, api_error_handler, unhandled_error_handler, validation_error_handler
from app.routers import health, risk


def create_app() -> FastAPI:
    app = FastAPI(title="Satark Backend", version="0.1.0")

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health.router)
    app.include_router(risk.router)

    return app


app = create_app()
