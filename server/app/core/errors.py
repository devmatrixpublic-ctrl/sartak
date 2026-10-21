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


async def validation_error_handler(_request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": str(exc)},
    )
