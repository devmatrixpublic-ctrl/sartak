"""Feasibility probe (offline, changes nothing): what would a '2+ signal families' eligibility gate do to the reference results?

Families, approximated from the 16 features: contact (unknown call/video/recent contact), install-or-watchlist app, new payee.
A payment-score alarm is only kept when at least `k` families are present on that payment. Rule alarms are unchanged.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
sys.path.insert(0, str(ROOT / "ops" / "eval"))
import satark_detector as sd  # noqa: E402
from run_eval import headline  # noqa: E402

params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())
det, res, (users, sessions, events, pay, alerts, first_pay) = sd.evaluate(ROOT / "data" / "satarksim", params["calibration_alpha"], params["watchlisted_remote_apps"])
print("baseline:", {k: round(v, 4) for k, v in headline(res).items() if k in ("recall", "false_alarm_rate")})

p = pay.copy()
contact = (p.unk_contact_recent > 0) | (p.unk_call_active > 0) | (p.unk_video_active > 0)
install = (p.install_play_during_unk > 0) | (p.install_sideload_during_unk > 0) | (p.watchlist_app > 0)
newp = (p.new_payee > 0) | (p.payee_added_after_unk > 0)
p["families"] = contact.astype(int) + install.astype(int) + newp.astype(int)
print("families distribution on payment rows:", p.families.value_counts().sort_index().to_dict())

for k in (1, 2):
    keep = p[p.families >= k]
    r = sd.decide(det, keep, alerts, first_pay, sessions).merge(sd.naive_flags(events), on="session_id")
    h = headline(r)
    print(f"gate families>={k}: recall {h['recall']:.4f} ({h['scam_alarmed']}/{h['scam_sessions']}), false alarms {h['false_alarm_rate']:.5f} ({h['legit_false_alarms']}/{h['legit_sessions']})")
    v = r[(r.split == 'validation') & (r.label == 'scam')]
    print("   recall by playbook:", {pb: round(g.alarm.mean(), 3) for pb, g in v.groupby('playbook')})
