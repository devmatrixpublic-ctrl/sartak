"""Minimal analyst console: list alerts, Approve or Clear them, every action audited. Admin role only.

The HTML page is a static shell with no data in it. A browser cannot send an Authorization header when it navigates, so the
page asks the analyst to paste an admin token (kept in memory only) and calls the admin-only JSON endpoints below with it.
The token is never stored by the page and the endpoints refuse every non-admin token (403).
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.service import DeviceIdentity
from app.core.errors import ApiError
from app.db.models import Alert, AuditLog
from app.db.session import get_db

router = APIRouter(tags=["admin"])

require_admin = require_role("admin")


class AdminAlert(BaseModel):
    id: str
    type: str
    delivered: bool
    failure_reason: str | None = None
    review_status: Literal["open", "approved", "cleared"]
    created_at: datetime


class AdminAlerts(BaseModel):
    alerts: list[AdminAlert]


@router.get("/admin/alerts", response_model=AdminAlerts)
async def list_alerts(_: DeviceIdentity = Depends(require_admin), db: Session = Depends(get_db)) -> AdminAlerts:
    rows = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(200)).all()
    return AdminAlerts(alerts=[
        AdminAlert(id=a.id, type=a.type, delivered=a.delivered, failure_reason=a.failure_reason,
                   review_status=a.review_status, created_at=a.created_at)
        for a in rows
    ])


def _act(db: Session, who: DeviceIdentity, alert_id: str, action: str, status: str) -> AdminAlert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise ApiError(404, "not_found", "Alert not found")
    if alert.review_status != "open":
        raise ApiError(409, "already_reviewed", "This alert was already reviewed.")
    alert.review_status = status
    db.add(AuditLog(actor_device_id=who.device_id, action=action, alert_id=alert.id))
    db.commit()
    db.refresh(alert)
    return AdminAlert(id=alert.id, type=alert.type, delivered=alert.delivered, failure_reason=alert.failure_reason,
                      review_status=alert.review_status, created_at=alert.created_at)


@router.post("/admin/alerts/{alert_id}/approve", response_model=AdminAlert)
async def approve(alert_id: str, who: DeviceIdentity = Depends(require_admin), db: Session = Depends(get_db)) -> AdminAlert:
    return _act(db, who, alert_id, "approve", "approved")


@router.post("/admin/alerts/{alert_id}/clear", response_model=AdminAlert)
async def clear(alert_id: str, who: DeviceIdentity = Depends(require_admin), db: Session = Depends(get_db)) -> AdminAlert:
    return _act(db, who, alert_id, "clear", "cleared")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Satark analyst console</title>
<style>body{font:15px system-ui,sans-serif;margin:24px;max-width:900px}table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #ccc;padding:6px 8px;text-align:left}button{margin-right:6px}#msg{color:#a00}</style></head>
<body><h1>Satark analyst console</h1>
<p>Alerts raised by Satark on protected phones. <b>Approve</b> confirms an alert was a real escalation; <b>Clear</b> dismisses it.
Every action is recorded. No names, numbers or payment details are shown. All figures come from simulated or test data unless this is a live deployment.</p>
<p><label>Admin token <input id="tok" type="password" size="40" autocomplete="off"></label> <button id="load">Load alerts</button></p>
<p id="msg"></p><table><thead><tr><th>Alert</th><th>Type</th><th>Delivered</th><th>Why not</th><th>Status</th><th>Time</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<script>
const tok = document.getElementById('tok'), rows = document.getElementById('rows'), msg = document.getElementById('msg');
async function call(path, method) {
  const r = await fetch(path, {method, headers: {Authorization: 'Bearer ' + tok.value.trim()}});
  if (!r.ok) throw new Error(r.status === 403 ? 'This token is not an admin token.' : r.status === 401 ? 'Sign-in failed.' : 'Error ' + r.status);
  return r.json();
}
function cell(tr, text) { const td = document.createElement('td'); td.textContent = text; tr.appendChild(td); return td; }
async function load() {
  msg.textContent = ''; rows.textContent = '';
  try {
    const data = await call('/admin/alerts', 'GET');
    for (const a of data.alerts) {
      const tr = document.createElement('tr');
      cell(tr, a.id.slice(0, 8)); cell(tr, a.type); cell(tr, a.delivered ? 'yes' : 'no'); cell(tr, a.failure_reason || ''); cell(tr, a.review_status);
      cell(tr, new Date(a.created_at).toLocaleString());
      const td = document.createElement('td');
      if (a.review_status === 'open') for (const act of ['approve', 'clear']) {
        const b = document.createElement('button'); b.textContent = act === 'approve' ? 'Approve' : 'Clear';
        b.onclick = async () => { try { await call('/admin/alerts/' + a.id + '/' + act, 'POST'); load(); } catch (e) { msg.textContent = e.message; } };
        td.appendChild(b);
      }
      tr.appendChild(td); rows.appendChild(tr);
    }
  } catch (e) { msg.textContent = e.message; }
}
document.getElementById('load').onclick = load;
</script></body></html>"""


@router.get("/admin/console", response_class=HTMLResponse, include_in_schema=False)
async def console() -> HTMLResponse:
    """The page itself holds no data; the data calls above need an admin token."""
    return HTMLResponse(PAGE)
