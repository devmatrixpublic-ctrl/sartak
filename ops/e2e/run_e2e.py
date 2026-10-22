#!/usr/bin/env python3
"""Cross-module end-to-end run: REAL detector decisions -> REAL server over HTTP. Nothing between them is mocked.

1. `detector/src/test/.../E2EDecisionsExport.kt` runs the real Kotlin detector (bundled model.json) over hand-built scenarios
   and two real SatarkSim vectors and writes detector/build/e2e/decisions.json (the test asserts each decision).
2. This script applies the migrations to an EMPTY database, starts the real FastAPI server (dev mode, SQLite, stub Razorpay
   and FCM clients: no external credentials exist here), then walks the app's flow with those decisions:
   register -> risk-check -> hold or hand-off -> result / checkout -> webhook -> alert -> signature, plus auth, IDOR,
   mass-assignment and size-limit attacks.

What it does NOT cover: the Android app itself, a phone, real Razorpay/Firebase, Render, real Key Attestation.

Usage (repo root):  python ops/e2e/run_e2e.py [--skip-gradle] [--decisions PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
DETECTOR = ROOT / "detector"
WEBHOOK_SECRET = "e2e-webhook-secret"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    return bool(ok)


def export_decisions(path: Path) -> None:
    for attempt in (1, 2):  # Maven Central rate-limits (429); Gradle keeps what it already downloaded
        p = subprocess.run(["gradle", "--no-daemon", "-q", "--max-workers=1", "test", "--tests", "*E2EDecisionsExport"],
                           cwd=DETECTOR, capture_output=True, text=True)
        if p.returncode == 0 and path.is_file():
            return
        print(f"  gradle attempt {attempt} failed: {(p.stdout + p.stderr)[-300:]}")
    sys.exit("could not produce decisions.json from the Kotlin detector")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gradle", action="store_true")
    ap.add_argument("--decisions", type=Path, default=DETECTOR / "build" / "e2e" / "decisions.json")
    a = ap.parse_args(argv)

    print("1. real detector decisions")
    if not a.skip_gradle:
        export_decisions(a.decisions)
    data = json.loads(a.decisions.read_text())
    scen = {s["name"]: s for s in data["scenarios"]}
    check("detector exported scenarios", len(scen) >= 8, f"{len(scen)} scenarios, model {data['model_version']}")
    check("every exported decision is the level the scenario states",
          all(s["decision"]["level"] == s["expected_level"] for s in scen.values()))

    tmp = Path(tempfile.mkdtemp(prefix="satark-e2e-"))
    env = {**os.environ, "SATARK_ENV": "dev", "SATARK_AUTH_ENABLE_DEV_TOKEN": "1",
           "SATARK_DATABASE_URL": f"sqlite:///{tmp / 'e2e.db'}", "SATARK_RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
           "SATARK_RATE_LIMIT_PER_MINUTE": "1000", "SATARK_REDIS_URL": "redis://127.0.0.1:1/0"}
    print("2. migrations on an empty database")
    mig = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=SERVER, env=env, capture_output=True, text=True)
    check("alembic upgrade head applies from an empty database", mig.returncode == 0, (mig.stdout + mig.stderr)[-400:])
    if mig.returncode != 0:
        return finish()

    port = free_port()
    log = open(tmp / "server.log", "wb")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                           cwd=SERVER, env=env, stdout=log, stderr=log)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            check("server started", False, (tmp / "server.log").read_text()[-500:])
            return finish()
        run_flows(base, scen)
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
    check("server log has no Traceback (no unhandled error during the whole run)",
          "Traceback" not in (tmp / "server.log").read_text(errors="replace"))
    return finish()


def run_flows(base: str, scen: dict) -> None:
    c = httpx.Client(base_url=base, timeout=15)
    A, B, EVIL = (str(uuid.uuid4()) for _ in range(3))
    salt = b"e2e-install-salt"

    def token(dev: str) -> dict:
        r = c.post("/auth/dev-token", json={"device_id": dev})
        return {"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code == 200 else {}

    print("3. auth and registration")
    check("GET /health", c.get("/health").json() == {"status": "ok"})
    ch = c.post("/auth/challenge", json={})
    check("POST /auth/challenge returns a challenge and expiry", ch.status_code == 200 and {"challenge", "expires_at"} <= set(ch.json()))
    reg = c.post("/auth/device", json={"challenge": ch.json().get("challenge", ""), "public_key": "AAAA", "attestation_chain": ["AAAA", "BBBB"]})
    check("device registration without pinned Google roots fails closed (503), as designed in dev",
          reg.status_code in (400, 503), f"{reg.status_code} {reg.text[:120]}")
    hA, hB, hEvil = token(A), token(B), token(EVIL)
    check("dev tokens issued for three devices", all((hA, hB, hEvil)))
    check("no token -> 401", c.post("/risk-check", json={}).status_code == 401)
    check("garbage token -> 401", c.post("/risk-check", json={}, headers={"Authorization": "Bearer nonsense"}).status_code == 401)

    print("4. trusted contact")
    link = c.post("/trusted-contact", json={"trusted_device_id": B, "fcm_token": "stale-or-fake-token"}, headers=hA)
    check("A links B as trusted contact", link.status_code == 200 and link.json() == {"linked": True}, link.text)
    ghost = c.post("/trusted-contact", json={"trusted_device_id": str(uuid.uuid4()), "fcm_token": "x"}, headers=hA)
    check("an unregistered contact is refused (404), never fabricated", ghost.status_code == 404, ghost.text)

    def risk(s: dict, method: str, headers=hA, amount=None) -> httpx.Response:
        d = s["decision"]
        return c.post("/risk-check", headers=headers, json={
            "decision": {"level": d["level"], "score": d["score"], "reasons": d["reasons"]}, "method": method,
            "amount": amount if amount is not None else s["amount"], "payee_hash": sha(salt + (s["payee"] or "x").encode()),
            "is_p2p": s["is_p2p"]})

    print("5. detector decision -> /risk-check -> payment state machines")
    held_ids = {}
    for name, s in scen.items():
        if s["kind"] != "payment":
            continue
        hard = s["decision"]["level"] == "HARD"
        r = risk(s, "upi_intent")
        body = r.json() if r.status_code == 200 else {}
        check(f"{name}: upi_intent decision {s['decision']['level']} -> {'HOLD' if hard else 'ALLOW'}",
              r.status_code == 200 and body.get("decision") == ("HOLD" if hard else "ALLOW"), r.text[:160])
        if r.status_code != 200:
            continue
        pid = body["payment_id"]
        st = c.get(f"/payments/{pid}", headers=hA).json()
        res = c.post(f"/payments/{pid}/result", json={"status": "success", "txn_ref": "REF1"}, headers=hA)
        if hard:
            held_ids[name] = pid
            check(f"{name}: payment is 'held', no order created", st["state"] == "held" and "order_id" not in body)
            check(f"{name}: a result cannot be posted for a held payment (409)", res.status_code == 409, res.text[:120])
        else:
            check(f"{name}: payment handed off", st["state"] == "handed_off", st["state"])
            check(f"{name}: UPI result stored as app-reported, never 'paid'",
                  res.status_code == 200 and res.json()["state"] == "reported_success" and res.json()["state"] != "paid", res.text[:160])

    scam = scen["scam_remote_access"]
    clean = scen["clean_known_contact"]
    r = risk(scam, "checkout")
    check("scam + checkout -> HOLD with no Razorpay order", r.status_code == 200 and r.json()["decision"] == "HOLD" and "order_id" not in r.json())
    r = risk(clean, "checkout")
    rb = r.json() if r.status_code == 200 else {}
    check("clean + checkout -> ALLOW with an order id", rb.get("decision") == "ALLOW" and bool(rb.get("order_id")), r.text[:160])
    if rb.get("order_id"):
        pid, order = rb["payment_id"], rb["order_id"]

        def hook(event: str, event_id: str, created: int, secret=WEBHOOK_SECRET, sig=None) -> httpx.Response:
            body = json.dumps({"event": event, "created_at": created,
                               "payload": {"payment": {"entity": {"order_id": order}}, "order": {"entity": {"id": order}}}}).encode()
            s = sig or hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            return c.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": s, "X-Razorpay-Event-Id": event_id,
                                                                         "Content-Type": "application/json"})

        check("forged webhook signature -> 400", hook("payment.captured", "evt-forged", 100, sig="0" * 64).status_code == 400)
        check("state unchanged after a forged webhook", c.get(f"/payments/{pid}", headers=hA).json()["state"] == "allowed")
        check("verified webhook accepted", hook("payment.captured", "evt-1", 200).status_code == 200)
        check("checkout reaches 'paid' only through the verified webhook", c.get(f"/payments/{pid}", headers=hA).json()["state"] == "paid")
        check("duplicate webhook is accepted and changes nothing", hook("payment.captured", "evt-1", 200).status_code == 200
              and c.get(f"/payments/{pid}", headers=hA).json()["state"] == "paid")
        hook("payment.failed", "evt-0", 50)
        check("a stale (older) failure arriving late does not undo 'paid'", c.get(f"/payments/{pid}", headers=hA).json()["state"] == "paid")

    print("6. alerts and signatures from real detector output")
    for name in ("scam_remote_access", "scam_sideload_rule_only", "scam_long_video_rule_only"):
        s = scen[name]
        typ = "long_session" if s["decision"]["mechanism"] == "long_session" else "alarm"
        r = c.post("/alert", json={"device_id": A, "type": typ, "reasons": s["decision"]["reasons"]}, headers=hA)
        check(f"{name}: /alert ({typ}) accepted even though the contact's push token is fake", r.status_code == 200 and r.json() == {"accepted": True}, r.text[:140])
    sigs = [s for s in scen.values() if s["features"]]
    check("detector produced feature vectors for the payment scenarios", len(sigs) >= 4)
    for s in sigs:
        r = c.post("/signature", json={"pattern_id": s["decision"]["mechanism"] or "payment_score", "features": s["features"]}, headers=hA)
        check(f"{s['name']}: the detector's own 16 feature names are accepted by /signature", r.status_code == 200 and r.json() == {"accepted": True}, r.text[:140])
    r = c.post("/signature", json={"pattern_id": "x", "features": {"phone_number": 1.0}}, headers=hA)
    check("a personal-data feature key is rejected by /signature (422, as api.yaml states)", r.status_code == 422, r.text[:120])

    print("7. attacks")
    pid_held = next(iter(held_ids.values()), None)
    if pid_held:
        check("IDOR: another device cannot read A's payment (404)", c.get(f"/payments/{pid_held}", headers=hEvil).status_code == 404)
        check("IDOR: even the trusted contact cannot read it (404)", c.get(f"/payments/{pid_held}", headers=hB).status_code == 404)
        check("IDOR: another device cannot post a result to it", c.post(f"/payments/{pid_held}/result", json={"status": "success"}, headers=hEvil).status_code in (403, 404))
    r = c.post("/risk-check", headers=hA, json={"decision": {"level": "NONE", "score": 0, "reasons": []}, "method": "checkout", "amount": 1,
                                                 "payee_hash": "h", "role": "admin"})
    check("mass assignment: an unknown field is rejected (422)", r.status_code == 422, r.text[:120])
    check("the 422 body leaks no traceback or server path", "Traceback" not in r.text and "/server/" not in r.text and ".py" not in r.text)
    r = risk(scam, "checkout", amount=0)
    check("amount 0 is rejected (422)", r.status_code == 422)
    r = c.post("/risk-check", headers=hA, content=b'{"payee_hash":"' + b"z" * 70_000 + b'"}')
    check("an oversize body is refused before parsing (413)", r.status_code == 413 and r.json()["code"] == "payload_too_large", r.text[:100])
    check("a client cannot self-report ALLOW for a HARD alarm",
          risk(scam, "upi_intent").json()["decision"] == "HOLD")


def finish() -> int:
    failed = [r for r in results if not r[1]]
    print(f"\nEND-TO-END: {len(results) - len(failed)}/{len(results)} checks passed")
    for n, _, d in failed:
        print(f"  FAILED: {n}  {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
