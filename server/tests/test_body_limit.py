"""Request-body size cap: oversize bodies are refused before parsing or auth, declared or streamed."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.limits import BodySizeLimitMiddleware
from app.main import app as real_app


def tiny_app(limit=100, path_limits=None):
    a = FastAPI()
    a.add_middleware(BodySizeLimitMiddleware, max_bytes=limit, path_limits=path_limits)

    @a.post("/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    @a.post("/big/echo")
    async def big(request: Request):
        return {"n": len(await request.body())}

    return a


def test_body_at_the_limit_passes_and_one_byte_over_is_refused():
    c = TestClient(tiny_app(100))
    assert c.post("/echo", content=b"x" * 100).json() == {"n": 100}
    r = c.post("/echo", content=b"x" * 101)
    assert r.status_code == 413 and r.json() == {"code": "payload_too_large", "message": "Request body too large."}


def test_a_streamed_body_with_no_content_length_is_cut_off():
    async def run():
        transport = httpx.ASGITransport(app=tiny_app(100))
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            async def gen():
                for _ in range(50):
                    yield b"y" * 10                       # 500 bytes in chunks, no length declared
            return await c.post("/echo", content=gen())
    r = asyncio.run(run())
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


def test_malformed_content_length_is_a_400_not_a_crash():
    """Called straight at the ASGI app: an HTTP client library would refuse to send these headers."""
    for bad in (b"abc", b"-5", b"1e3"):
        sent = []

        async def run():
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(m):
                sent.append(m)

            await tiny_app(100)({"type": "http", "path": "/echo", "method": "POST",
                                 "headers": [(b"content-length", bad)]}, receive, send)
        asyncio.run(run())
        start = next(m for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        assert start["status"] == 400 and b"invalid_request" in body, (bad, start["status"], body)


def test_path_specific_limit_applies_by_prefix():
    c = TestClient(tiny_app(100, {"/big/": 1000}))
    assert c.post("/big/echo", content=b"x" * 900).status_code == 200
    assert c.post("/echo", content=b"x" * 900).status_code == 413


def test_get_without_a_body_is_untouched():
    c = TestClient(tiny_app(100))
    assert c.get("/echo").status_code == 405                    # reached the router, not blocked by the middleware


# --- the real app -----------------------------------------------------------------------------------------------------
def test_real_app_refuses_an_oversize_body_before_authentication():
    c = TestClient(real_app)
    r = c.post("/risk-check", content=b"{" + b'"a":"' + b"z" * 70_000 + b'"}', headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"     # not 401: cheap rejection first
    assert "Traceback" not in r.text


def test_real_app_normal_sized_request_still_reaches_authentication():
    r = TestClient(real_app).post("/risk-check", json={"x": 1})
    assert r.status_code in (401, 422)                           # authenticated route, no token: not a 413


def test_real_app_webhook_gets_the_larger_limit():
    r = TestClient(real_app).post("/webhooks/razorpay", content=b"{" + b'"a":"' + b"z" * 100_000 + b'"}')
    assert r.status_code != 413                                  # 100 KB is fine for a webhook (bad signature -> 400)
    r2 = TestClient(real_app).post("/webhooks/razorpay", content=b"z" * 300_000)
    assert r2.status_code == 413
