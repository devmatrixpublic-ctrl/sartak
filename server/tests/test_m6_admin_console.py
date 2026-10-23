"""Analyst console: admin only, every action audited, no personal data on the page."""

import jwt
import pytest

from app.db.models import Alert, AuditLog, Device

from .test_m4_auth import SECRET, bearer, env, make_env  # noqa: F401  (fixtures)


def _device(env, device_id, role):
    s = env["session_factory"]()
    s.add(Device(id=device_id, public_key=f"pk-{device_id}", attestation_level="TEE", verified_boot_state="verified", role=role))
    s.commit(); s.close()
    claims = {"sub": device_id, "role": role, "typ": "access", "exp": int(env["clock"].now()) + 600}
    return bearer(jwt.encode(claims, SECRET, algorithm="HS256"))


def _alert(env, **kw):
    s = env["session_factory"]()
    s.add(Device(id="phone-1", public_key="pk-phone-1", attestation_level="TEE", verified_boot_state="verified")) if not s.get(Device, "phone-1") else None
    a = Alert(device_id="phone-1", type=kw.get("type", "alarm"), delivered=kw.get("delivered", True), failure_reason=kw.get("failure_reason"))
    s.add(a); s.commit(); aid = a.id; s.close()
    return aid


def test_non_admin_gets_403_on_every_admin_endpoint(env):
    dev = _device(env, "dev-1", "device")
    aid = _alert(env)
    c = env["client"]
    assert c.get("/admin/alerts", headers=dev).status_code == 403
    assert c.post(f"/admin/alerts/{aid}/approve", headers=dev).status_code == 403
    assert c.post(f"/admin/alerts/{aid}/clear", headers=dev).status_code == 403


def test_no_token_is_401(env):
    assert env["client"].get("/admin/alerts").status_code == 401


def test_admin_lists_and_acts_and_every_action_is_audited(env):
    adm = _device(env, "adm-1", "admin")
    a1, a2 = _alert(env), _alert(env, type="long_session", delivered=False, failure_reason="trusted_contact_not_accepted")
    c = env["client"]
    listed = c.get("/admin/alerts", headers=adm).json()["alerts"]
    assert {a["id"] for a in listed} == {a1, a2} and all(a["review_status"] == "open" for a in listed)

    assert c.post(f"/admin/alerts/{a1}/approve", headers=adm).json()["review_status"] == "approved"
    assert c.post(f"/admin/alerts/{a2}/clear", headers=adm).json()["review_status"] == "cleared"

    s = env["session_factory"]()
    rows = s.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [(r.actor_device_id, r.action, r.alert_id) for r in rows] == [("adm-1", "approve", a1), ("adm-1", "clear", a2)]
    s.close()


def test_an_alert_is_reviewed_once_and_unknown_ids_are_404(env):
    adm = _device(env, "adm-2", "admin")
    aid = _alert(env)
    c = env["client"]
    assert c.post(f"/admin/alerts/{aid}/approve", headers=adm).status_code == 200
    assert c.post(f"/admin/alerts/{aid}/clear", headers=adm).status_code == 409
    assert c.post("/admin/alerts/nope/approve", headers=adm).status_code == 404
    s = env["session_factory"]()
    assert s.query(AuditLog).count() == 1  # the refused ones wrote nothing
    s.close()


def test_page_and_listing_contain_no_personal_data(env):
    adm = _device(env, "adm-3", "admin")
    _alert(env)
    page = env["client"].get("/admin/console")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    body = env["client"].get("/admin/alerts", headers=adm).text
    for text in (page.text, body):
        assert "phone-1" not in text, "the protected phone's device id must not appear"
        assert "payee" not in text.lower() and "upi" not in text.lower() and "amount" not in text.lower()
        assert "http://" not in text and "https://" not in text
    assert "phone-1" not in page.text


def test_console_page_holds_no_data_and_never_stores_the_token(env):
    page = env["client"].get("/admin/console").text
    assert "localStorage" not in page and "sessionStorage" not in page and "document.cookie" not in page
