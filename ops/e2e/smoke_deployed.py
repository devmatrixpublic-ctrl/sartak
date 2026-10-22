#!/usr/bin/env python3
"""Smoke test for a DEPLOYED Satark server (Render): is it up, locked down, and behaving like production?

Needs no credentials and changes nothing that matters (it requests one challenge and sends a few rejected requests).

    python ops/e2e/smoke_deployed.py https://<your-service>.onrender.com

Checks (each prints PASS or FAIL):
  * served over HTTPS; plain HTTP is refused or redirected to HTTPS
  * GET /health is 200 {"status": "ok"}
  * interactive docs and the schema are NOT served (/docs, /redoc, /openapi.json)
  * the dev-token stub is off (/auth/dev-token is 404)
  * every protected route answers 401 without a token, with a {code, message} body and no stack trace
  * /auth/challenge works; /auth/device rejects a bogus attestation (400 or 503, never a 500)
  * a forged Razorpay webhook signature is refused (400)
  * an oversize body is refused before parsing (413)

What it cannot check: Key Attestation with a real phone, a real payment, the push notification, certificate pinning (see
ops/security/tls_pins.py), the database role, or the Redis-backed rate limit. `--allow-http` is for a local server only.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse

import httpx

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    return bool(ok)


def clean_error(r: httpx.Response) -> bool:
    """A {code, message} JSON error that leaks no traceback or file path."""
    try:
        body = r.json()
    except ValueError:
        return False
    text = r.text
    return isinstance(body, dict) and {"code", "message"} <= set(body) and "Traceback" not in text and ".py" not in text


def run(base_url: str, allow_http: bool = False) -> list[tuple[str, bool, str]]:
    results.clear()
    base = base_url.rstrip("/")
    parts = urllib.parse.urlsplit(base)
    c = httpx.Client(base_url=base, timeout=20, follow_redirects=False)

    print("transport")
    check("served over HTTPS", parts.scheme == "https" or allow_http, f"scheme is {parts.scheme!r}")
    if parts.scheme == "https":
        try:
            r = httpx.get("http://" + parts.netloc + "/health", timeout=10, follow_redirects=False)
            check("plain HTTP is redirected to HTTPS", r.status_code in (301, 302, 307, 308) and r.headers.get("location", "").startswith("https://"),
                  f"HTTP answered {r.status_code}")
        except httpx.HTTPError:
            check("plain HTTP is refused", True)

    print("liveness and exposure")
    try:
        h = c.get("/health")
    except httpx.HTTPError as e:
        check("GET /health reachable", False, str(e)[:150])
        return results
    check("GET /health is 200 {status: ok}", h.status_code == 200 and h.json() == {"status": "ok"}, f"{h.status_code} {h.text[:100]}")
    for path in ("/docs", "/redoc", "/openapi.json"):
        status = c.get(path).status_code
        check(f"{path} is not served", status == 404, f"status {status}")
    dt = c.post("/auth/dev-token", json={"device_id": "smoke-test"})
    check("dev-token stub is off (404)", dt.status_code == 404, f"status {dt.status_code}")

    print("authentication is required")
    protected = [("POST", "/risk-check", {}), ("GET", "/payments/00000000-0000-0000-0000-000000000000", None),
                 ("POST", "/payments/00000000-0000-0000-0000-000000000000/result", {}), ("POST", "/alert", {}),
                 ("POST", "/signature", {}), ("POST", "/trusted-contact", {})]
    for method, path, body in protected:
        r = c.request(method, path, json=body) if body is not None else c.request(method, path)
        check(f"{method} {path} without a token -> 401 with a clean error", r.status_code == 401 and clean_error(r), f"{r.status_code} {r.text[:120]}")
    r = c.get("/payments/x", headers={"Authorization": "Bearer not-a-real-token"})
    check("a garbage bearer token -> 401", r.status_code == 401, f"{r.status_code}")

    print("device registration fails closed")
    ch = c.post("/auth/challenge", json={})
    check("POST /auth/challenge returns a challenge and an expiry", ch.status_code == 200 and {"challenge", "expires_at"} <= set(ch.json()),
          f"{ch.status_code} {ch.text[:120]}")
    reg = c.post("/auth/device", json={"challenge": ch.json().get("challenge", "x" * 43) if ch.status_code == 200 else "x" * 43,
                                        "public_key": "AAAA", "attestation_chain": ["AAAA", "BBBB"]})
    check("a bogus attestation is rejected (400 or 503, never 200 or 500) with a clean error",
          reg.status_code in (400, 503) and clean_error(reg), f"{reg.status_code} {reg.text[:160]}")

    print("input handling")
    wh = c.post("/webhooks/razorpay", content=b'{"event":"payment.captured"}',
                headers={"X-Razorpay-Signature": "0" * 64, "X-Razorpay-Event-Id": "smoke-forged", "Content-Type": "application/json"})
    check("a forged webhook signature is refused (400)", wh.status_code == 400 and clean_error(wh), f"{wh.status_code} {wh.text[:120]}")
    big = c.post("/risk-check", content=b'{"payee_hash":"' + b"z" * 70_000 + b'"}', headers={"Content-Type": "application/json"})
    check("an oversize body is refused before parsing (413)", big.status_code == 413 and clean_error(big), f"{big.status_code} {big.text[:100]}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", help="e.g. https://satark-server.onrender.com")
    ap.add_argument("--allow-http", action="store_true", help="local server only")
    a = ap.parse_args(argv)
    print(f"smoke test of {a.base_url}")
    res = run(a.base_url, a.allow_http)
    failed = [r for r in res if not r[1]]
    print(f"\nSMOKE TEST: {len(res) - len(failed)}/{len(res)} checks passed")
    for n, _, d in failed:
        print(f"  FAILED: {n}  {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
