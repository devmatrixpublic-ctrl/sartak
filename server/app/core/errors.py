from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Error carrying the {code, message} contract body. Never leaks a stack trace."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "message": "An internal error occurred."},
    )


def _describe(errors: list[dict]) -> str:
    """Field names and generic reasons only. str(exc) includes the client's input and, in this
    FastAPI version, server file paths and source lines, so it must never reach the response."""
    parts = []
    for e in errors[:5]:
        loc = ".".join(str(x) for x in e.get("loc", ())[1:]) or "body"
        parts.append(f"{loc}: {e.get('msg', 'invalid')}")
    return "Invalid request: " + "; ".join(parts) if parts else "Invalid request."


async def validation_error_handler(_request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": _describe(exc.errors())},
    )
