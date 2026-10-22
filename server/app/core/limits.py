"""Request-body size cap (OWASP API4, unrestricted resource consumption).

Pure ASGI so an oversize body is rejected before it is parsed or authenticated, whether the size is declared in
Content-Length or arrives as a stream with no length. The response uses the same `{code, message}` body as every other error.
"""
import json


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int, path_limits: dict[str, int] | None = None):
        self.app = app
        self.max_bytes = max_bytes
        self.path_limits = path_limits or {}   # path prefix -> limit, first match wins

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self.path_limits.items():
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    @staticmethod
    async def _respond(send, status: int, code: str, message: str) -> None:
        body = json.dumps({"code": code, "message": message}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self._limit_for(scope.get("path", ""))

        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                n = int(declared)
                if n < 0:
                    raise ValueError
            except ValueError:
                return await self._respond(send, 400, "invalid_request", "Malformed Content-Length header.")
            if n > limit:
                return await self._respond(send, 413, "payload_too_large", "Request body too large.")

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._respond(send, 413, "payload_too_large", "Request body too large.")
