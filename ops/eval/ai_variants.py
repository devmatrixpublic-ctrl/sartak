"""AI-style scam variants: does the detector still catch scams that look different on the surface? (problem statement: "AI-enabled")

AI changes how convincing the caller is (a script written by a language model, a fake support chat, payments split into small
pieces). It does not change what the scam has to do on the victim's phone. Satark reads that phone-side trail only. It does not
analyse voices or video, so it cannot say whether a voice is cloned or a video is a deepfake; those are separate problems. This tests the claim:
each scenario is a different AI-era workflow written as the events the phone would see, run through M2's reference
detector fitted on SatarkSim. Genuine look-alikes are run beside them, because catching scams by alarming everyone proves nothing.

What this is, and is not: scenarios written by the team and never used to train or calibrate the detector. They show how the
detector's logic behaves on workflows it was not built around. They are simulated events, not recordings of real scams, and
the detector is the Python reference of the on-device one. The misses are reported, not hidden.

Usage (repo root):  python ops/eval/ai_variants.py [--data data/satarksim] [--per-band 30] [--out ops/eval/reports]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
BANDS = ["18-35", "36-59", "60+"]
REMOTE_APP = "com.anydesk.anydeskandroid"
OTHER_APK = "com.example.supportapp"
COLUMNS = ["session_id", "user_id", "split", "day", "t_sec", "ts_abs", "event_type", "caller_known", "call_direction", "app_package",
           "install_source", "payee_id", "payee_is_new", "amount_inr", "payment_type", "merchant_category", "channel", "initiator",
           "is_duplicate"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


class Ev:
    """Builds one session's events in the simulator's schema."""

    def __init__(self, sid: str, uid: str):
        self.sid, self.uid, self.rows = sid, uid, []

    def add(self, t: float, etype: str, **kw):
        base = {c: None for c in COLUMNS}
        base.update(session_id=self.sid, user_id=self.uid, split="validation", day=10, t_sec=int(t), ts_abs=1_000_000 + int(t),
                    event_type=etype, channel="upi", initiator="user", is_duplicate=False)
        base.update(kw)
        self.rows.append(base)
        return self


def _pay(ev: Ev, t, payee, amount, new, p2p=True):
    if new:
        ev.add(t - 1, "NEW_PAYEE", payee_id=payee)
    ev.add(t, "PAYMENT_ATTEMPT", payee_id=payee, payee_is_new=new, amount_inr=round(amount, 2), payment_type="P2P" if p2p else "P2M")


# Each scenario: (name, group, should_alarm, description, builder(ev, rng, median)).
def s_family_emergency(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    t = r.uniform(120, 600)
    _pay(ev, t, "NEWP", amt("family"), True)
    ev.add(t + 60, "CALL_END")


def s_digital_arrest_video(ev, r, med, amt):
    ev.add(0, "VIDEO_SESSION_START", caller_known=False, app_package="com.whatsapp")
    t = r.uniform(1200, 5000)
    _pay(ev, t, "NEWP", amt("arrest"), True)
    ev.add(t + 120, "VIDEO_SESSION_END", app_package="com.whatsapp")


def s_fake_support_remote_app(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    ev.add(r.uniform(120, 400), "APP_FOREGROUND", app_package=REMOTE_APP)
    _pay(ev, r.uniform(600, 1500), "NEWP", amt("remote"), True)


def s_fake_kyc_apk(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    ev.add(r.uniform(60, 400), "APP_INSTALL", app_package=OTHER_APK, install_source="sideload")
    _pay(ev, r.uniform(700, 1800), "NEWP", amt("apk"), True)


def s_text_led_no_call(ev, r, med, amt):
    # the app turns "a stranger texted" into an instant unknown contact: a CALL_START and a CALL_END a moment later
    ev.add(0, "CALL_START", caller_known=False)
    ev.add(1, "CALL_END")
    ev.add(r.uniform(120, 900), "APP_INSTALL", app_package=OTHER_APK, install_source="sideload")
    _pay(ev, r.uniform(1000, 3000), "NEWP", amt("apk"), True)


def s_split_payments(ev, r, med, amt):
    # a scripted scammer asks for three smaller transfers instead of one large one
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    t = r.uniform(120, 400)
    total = amt("family")
    for i in range(3):
        _pay(ev, t + i * r.uniform(90, 240), "NEWP", total / 3, i == 0)


def s_no_remote_app_large(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    _pay(ev, r.uniform(300, 900), "NEWP", amt("family_high"), True)


# Genuine look-alikes. A good detector leaves these alone.
def c_rent_known_call(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=True, call_direction="incoming")
    _pay(ev, r.uniform(200, 900), "LANDLORD", amt("legit_tail"), True)


def c_bank_support_small(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    _pay(ev, r.uniform(200, 900), "KNOWN1", med * r.uniform(0.5, 2), False)


def c_wedding_no_contact(ev, r, med, amt):
    _pay(ev, r.uniform(60, 600), "CATERER", amt("legit_tail"), True)


def c_delivery_call_merchant(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=False, call_direction="incoming")
    _pay(ev, r.uniform(100, 400), "SHOP1", med * r.uniform(0.5, 2), False, p2p=False)
    ev.add(500, "CALL_END")


def c_play_install_no_payment(ev, r, med, amt):
    ev.add(0, "CALL_START", caller_known=True, call_direction="incoming")
    ev.add(r.uniform(60, 300), "APP_INSTALL", app_package="com.example.maps", install_source="play_store")


SCENARIOS = [
    ("Family emergency from an unknown caller", "scam", True, "Unknown caller (a real or a cloned voice looks the same to Satark), no app, one large payment to a new payee", s_family_emergency),
    ("Digital arrest on a video call", "scam", True, "Unknown video call, a long wait, a very large payment", s_digital_arrest_video),
    ("Fake customer care with screen-sharing", "scam", True, "Unknown call, screen-sharing app opened, large payment to a new payee", s_fake_support_remote_app),
    ("Fake KYC app", "scam", True, "Unknown call, app from outside Google Play, payment to a new payee", s_fake_kyc_apk),
    ("Text-led, no call", "scam", True, "A stranger's text, an unsafe app, payment to a new payee", s_text_led_no_call),
    ("Payment split into three", "scam", True, "Unknown call, three smaller transfers to the same new payee", s_split_payments),
    ("Large payment, no screen-sharing app", "scam", True, "Unknown call, no app at all, very large payment to a new payee", s_no_remote_app_large),
    ("Genuine rent, known caller", "control", False, "Known caller, new payee, large", c_rent_known_call),
    ("Genuine bank-support call, small payment", "control", False, "Unknown caller, known payee, small", c_bank_support_small),
    ("Genuine wedding payment, no call", "control", False, "No contact, new payee, large", c_wedding_no_contact),
    ("Delivery call, shop payment", "control", False, "Unknown caller, merchant already known, small", c_delivery_call_merchant),
    ("Play Store install, no payment", "control", False, "Known caller, install from Google Play", c_play_install_no_payment),
]


def build(per_band: int, med: float, mad: float, ranges: dict, seed: int = 7):
    """All scenario sessions as (events, users, sessions) frames. Deterministic for a given seed."""
    rng = np.random.default_rng(seed)

    def amt(key: str) -> float:
        lo, hi = ranges[key]  # multiples of the user's usual payment, log-uniform between the two
        return med * float(np.exp(rng.uniform(np.log(lo), np.log(hi))))

    rows, sess, users = [], [], []
    n = 0
    for si, (name, group, expect, _desc, fn) in enumerate(SCENARIOS):
        for band in BANDS:
            for i in range(per_band):
                n += 1
                sid, uid = f"V{n:06d}", f"VU{n:06d}"
                ev = Ev(sid, uid)
                fn(ev, rng, med, amt)
                rows += ev.rows
                users.append({"user_id": uid, "hist_median_inr": med, "hist_mad_inr": mad, "n_known_payees": 20, "age_band": band,
                              "activity_tier": "mid", "payments_per_month": 25, "call_state_available": True, "usage_access": True,
                              "split": "validation"})
                sess.append({"session_id": sid, "user_id": uid, "scenario": name, "group": group, "expect_alarm": expect, "age_band": band})
    return pd.DataFrame(rows, columns=COLUMNS), pd.DataFrame(users), pd.DataFrame(sess)


def amount_ranges(data: Path) -> dict:
    """Amount multiples taken from SatarkSim itself, not chosen by hand.

    Scam keys: the 25th to 75th percentile of that playbook's payments, as a multiple of the user's usual payment.
    "family_high": 50th to 90th percentile of the family-emergency playbook. "legit_tail": the 90th to 99th percentile of
    legitimate payments (large but genuine).
    """
    s = pd.read_csv(data / "satarksim_sessions.csv", usecols=["session_id", "user_id", "label", "playbook"])
    u = pd.read_csv(data / "satarksim_users.csv", usecols=["user_id", "hist_median_inr"])
    e = pd.read_csv(data / "satarksim_events.csv", usecols=["session_id", "event_type", "amount_inr"], low_memory=False)
    p = e[e.event_type == "PAYMENT_ATTEMPT"].merge(s, on="session_id").merge(u, on="user_id")
    p["ratio"] = (p.amount_inr / p.hist_median_inr).clip(lower=0.01)

    def q(mask, lo, hi):
        r = p[mask].ratio
        return float(r.quantile(lo)), float(r.quantile(hi))

    scam = p.label == "scam"
    return {
        "family": q(scam & (p.playbook == "family_emergency_scam"), .25, .75),
        "family_high": q(scam & (p.playbook == "family_emergency_scam"), .50, .90),
        "arrest": q(scam & (p.playbook == "digital_arrest"), .25, .75),
        "remote": q(scam & (p.playbook == "remote_access"), .25, .75),
        "apk": q(scam & (p.playbook == "malicious_apk"), .25, .75),
        "legit_tail": q(p.label == "legit", .90, .99),
    }


def run(data: Path, alpha: float, per_band: int) -> tuple[pd.DataFrame, dict]:
    sys.path.insert(0, str(REF))
    import satark_detector as sd

    params = json.loads((REF / "params.json").read_text())
    wl = params["watchlisted_remote_apps"]
    assert REMOTE_APP in wl, "the stand-in remote app must be on the watch-list"
    det, _res, (users, *_r) = sd.evaluate(data, alpha, wl)
    med, mad = float(users.hist_median_inr.median()), float(users.hist_mad_inr.median())
    ranges = amount_ranges(data)
    ev, vu, vs = build(per_band, med, mad, ranges)
    for c in ("caller_known", "payee_is_new"):
        ev[c] = ev[c].map({True: True, False: False, "True": True, "False": False})
    pay, alerts, first_pay = sd.featurize(ev, vu, wl)
    out = sd.decide(det, pay, alerts, first_pay, vs)
    return out, {"median_inr": med, "mad_inr": mad, "thresholds": det.thr, "ranges": ranges}


def summarise(out: pd.DataFrame) -> list[dict]:
    rows = []
    for name, g in out.groupby("scenario", sort=False):
        n, k = len(g), int(g.alarm.sum())
        lo, hi = wilson(k, n)
        by_band = {b: float(gb.alarm.mean()) for b, gb in g.groupby("age_band")}
        mech = g[g.alarm].mechanism.value_counts().to_dict()
        rows.append({"scenario": name, "group": g.group.iloc[0], "expect_alarm": bool(g.expect_alarm.iloc[0]), "n": n, "alarmed": k,
                     "rate": k / n, "ci95": [lo, hi], "by_band": by_band, "mechanisms": mech,
                     "before_first_payment": float(g.interdicted.mean())})
    return rows


def render(rows: list[dict], meta: dict, alpha: float) -> str:
    desc = {s[0]: s[3] for s in SCENARIOS}
    pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    scams = [r for r in rows if r["group"] == "scam"]
    ctrls = [r for r in rows if r["group"] == "control"]

    def line(r):
        b = r["by_band"]
        mech = ", ".join(f"{k} {v}" for k, v in r["mechanisms"].items()) or "none"
        return (f"| {r['scenario']} | {desc[r['scenario']]} | {r['alarmed']}/{r['n']} ({pct(r['rate'])}, {pct(r['ci95'][0])} to {pct(r['ci95'][1])}) "
                f"| {pct(b['18-35'])} / {pct(b['36-59'])} / {pct(b['60+'])} | {mech} |")

    names = {"family": "family emergency", "family_high": "family emergency, upper half", "arrest": "digital arrest", "remote": "remote access",
             "apk": "malicious app", "legit_tail": "genuine large payment"}
    ranges_lines = "\n".join(f"- {names[k]}: {lo:,.0f}x to {hi:,.0f}x" for k, (lo, hi) in meta["ranges"].items())
    s_k, s_n = sum(r["alarmed"] for r in scams), sum(r["n"] for r in scams)
    c_k, c_n = sum(r["alarmed"] for r in ctrls), sum(r["n"] for r in ctrls)
    missed = [r["scenario"] for r in scams if r["rate"] < 0.5]
    return f"""# AI-style scam variants

**Team-written scenarios on the reference detector fitted on SatarkSim. Simulated events, never used to train or calibrate. Not real-world accuracy.**
Calibration alpha {alpha}. Typical user: usual payment about Rs {meta['median_inr']:.0f}. Each scenario is run {rows[0]['n'] // 3} times in each age band.

## Where the amounts come from
Taken from SatarkSim itself, as multiples of the user's usual payment, never hand-picked. Scams: the middle half (25th to 75th
percentile) of the matching playbook. Genuine large payments: the 90th to 99th percentile of legitimate payments.
{ranges_lines}

## Scam workflows (the detector should hold the payment)
| Scenario | What happens | Held | By age band (18-35 / 36-59 / 60+) | Fired by |
|---|---|---|---|---|
{chr(10).join(line(r) for r in scams)}

**Overall: {s_k} of {s_n} scam runs held ({pct(s_k / s_n)}).**

## Genuine look-alikes (the detector should stay quiet)
| Scenario | What happens | Wrongly held | By age band | Fired by |
|---|---|---|---|---|
{chr(10).join(line(r) for r in ctrls)}

**Overall: {c_k} of {c_n} genuine runs wrongly held ({pct(c_k / c_n)}).**

## What this shows
{("- Weak spots (held in fewer than half of runs): " + "; ".join(missed) + ".") if missed else "- Every scam scenario was held in at least half of its runs."}
- "Fired by" says whether the payment score or a rule (such as an unsafe install during contact) raised the alarm.
- The older age band has a higher threshold, so it is the one to watch in the by-band column.
- A scam that leaves no screen-sharing app and no unsafe install rests on the unknown caller, a new payee and the amount alone.
  Whether that holds is shown in the rows above, and any miss is the detector's real limit.

## Limits
- These are our own scenarios. Real scammers will not follow them, and nothing here measures how often real people hit each workflow.
- The detector tested is the Python reference. The on-device version agrees on the 36 shared test vectors, not on every case here.
- Amounts are multiples of a typical user's usual payment, taken from the simulator's own distributions (listed above). A user with a very different baseline would see different results.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--per-band", type=int, default=30)
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    params = json.loads((REF / "params.json").read_text())
    alpha = a.alpha if a.alpha is not None else params["calibration_alpha"]
    out, meta = run(a.data, alpha, a.per_band)
    rows = summarise(out)
    a.out.mkdir(parents=True, exist_ok=True)
    md = render(rows, meta, alpha)
    (a.out / "ai_variants.md").write_text(md, encoding="utf-8", newline="\n")
    (a.out / "ai_variants.json").write_text(json.dumps({"alpha": alpha, "meta": {k: v for k, v in meta.items() if k != "thresholds"},
                                                         "thresholds": {k: float(v) for k, v in meta["thresholds"].items()},
                                                         "scenarios": rows}, indent=2, default=float), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
