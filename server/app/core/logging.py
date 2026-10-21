"""Structured JSON logging with request correlation.

Deliberately never logs request/response bodies: the payment amount,
payee hash, and any device-linked values stay out of the log stream by
construction, not by scrubbing after the fact. Only route, status, method,
duration and the request id are logged per request.
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True


_STANDARD_LOG_RECORD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    # uvicorn's own access log duplicates what RequestCorrelationMiddleware
    # already emits (and does it without scrubbing); silence it.
    logging.getLogger("uvicorn.access").disabled = True


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._logger = logging.getLogger("satark.request")

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        token = _request_id_ctx.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        self._logger.info(
            "request_handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
            },
        )
        response.headers["X-Request-Id"] = request_id
        return response
