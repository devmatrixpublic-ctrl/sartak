"""Auth errors reuse M3's {code, message} contract body and add response headers."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError


class AuthError(ApiError):
    def __init__(self, status_code: int, code: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(status_code, code, message)
        self.headers = headers or {}


def unauthorized(code: str, message: str) -> AuthError:
    return AuthError(401, code, message, {"WWW-Authenticate": "Bearer"})


async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
        headers=exc.headers,
    )
