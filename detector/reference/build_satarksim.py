#!/usr/bin/env python3
"""Build SatarkSim v2: one event table that merges Satark's data sources, with real-world imperfections.

Sources:
  * NPCI statistics          -> legit amount model (official workbook via --npci-xlsx sets the average ticket)
  * Kaggle UPI Transactions  -> hour-of-day and P2M merchant mix (--kaggle-upi); its amounts and fraud flag are not used
  * ICFD-31k                 -> scam-type taxonomy only (umbrella names)
  * Generated signals        -> call / app install / video / payee / payment events
  * Held-out real cases      -> copied untouched with a SHA-256 fingerprint; never used in the build

v2 realism features:
  1. Per-user consistency: stable spending scale, known-payee list, history stats from the user's own distribution
  2. Hard negatives that look like scams: genuine family emergency, rent/salary day, festival spikes, COD calls, IT support
  3. Device noise: OEMs without call state, revoked usage access, timestamp jitter, duplicate events, 2% label noise
  4. 12-week calendar with drift: a new remote-access app (not on the watch-list) and more malicious APKs from week 6
  5. Five scam playbooks: remote access, malicious APK, digital arrest, family-emergency scam, screen share
  6. --timing-scale for sensitivity analysis of timing assumptions

Usage:
  python build_satarksim.py --heldout heldout_events.csv --kaggle-upi upi_transactions_2024.csv \
      --npci-xlsx Product-Statistics-UPI-2024-25-Monthly.xlsx --out data [--timing-scale 1.0]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm, spearmanr

EVENT_COLUMNS = [
    "session_id", "user_id", "split", "day", "t_sec", "ts_abs", "event_type", "caller_known", "call_direction",
    "app_package", "install_source", "payee_id", "payee_is_new", "amount_inr", "payment_type",
    "merchant_category", "channel", "initiator", "is_duplicate",
]


# --------------------------------------------------------------------------- amount calibration
def capped_lognormal_mean(mu: float, sigma: float, cap: float) -> float:
    lc = math.log(cap)
    return (math.exp(mu + sigma**2 / 2) * norm.cdf((lc - mu - sigma**2) / sigma)
            + cap * (1 - norm.cdf((lc - mu) / sigma)))


def npci_avg_ticket(xlsx: Path) -> tuple[float, str]:
    n = pd.read_excel(xlsx, header=0)
    n.columns = ["month", "banks", "vol_mn", "val_cr"][: len(n.columns)]
    for c in ("vol_mn", "val_cr"):
        n[c] = n[c].astype(str).str.replace(r"[,\s]", "", regex=True).astype(float)
    n = n.dropna(subset=["vol_mn", "val_cr"])
    return float(n.val_cr.sum() * 1e7 / (n.vol_mn.sum() * 1e6)), f"{n.month.iloc[-1]} to {n.month.iloc[0]}"


def fit_amount_model(p: dict, target_mean: float | None = None) -> dict:
    """Population lognormals matching NPCI shares + average ticket, split into user and within-user parts."""
    npci, am = p["npci"], p["amount_model"]
    if target_mean is None:
        target_mean = npci["monthly_value_inr"] / npci["monthly_volume_txns"]
    w_p2m, cap, su = npci["p2m_share_of_volume"], am["upi_p2p_cap_inr"], p["user_scale_sigma"]
    s_m = am["p2m_sigma"]
    mu_m = math.log(500) - norm.ppf(npci["p2m_share_below_500"]) * s_m
    mean_m = math.exp(mu_m + s_m**2 / 2)
    z_p = norm.ppf(npci["p2p_share_below_500"])

    def gap(s_p):
        return w_p2m * mean_m + (1 - w_p2m) * capped_lognormal_mean(math.log(500) - z_p * s_p, s_p, cap) - target_mean

    s_p = brentq(gap, 0.3, 5.0)
    mu_p = math.log(500) - z_p * s_p
    within = lambda s: math.sqrt(max(s**2 - su**2, 0.05))  # noqa: E731
    return {"target_mean": target_mean, "w_p2m": w_p2m, "cap": cap, "user_sigma": su,
            "p2m": (mu_m, s_m), "p2p": (mu_p, s_p), "p2m_within": within(s_m), "p2p_within": within(s_p)}


# --------------------------------------------------------------------------- Kaggle input
def load_kaggle(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    amount = next((cols[c] for c in cols if c.startswith("amount")), None)
    ttype = next((cols[c] for c in cols if "type" in c and "transaction" in c), None)
    hour = next((cols[c] for c in cols if c in ("hour_of_day", "hour")), None)
    out = pd.DataFrame({"amount": pd.to_numeric(df[amount], errors="coerce") if amount else np.nan})
    out["payment_type"] = df[ttype].astype(str).str.upper().map(lambda v: "P2P" if "P2P" in v else "P2M") if ttype else "P2M"
    out["hour"] = pd.to_numeric(df[hour], errors="coerce") if hour else np.nan
    mc = cols.get("merchant_category")
    out["merchant_category"] = df[mc].astype(str) if mc else None
    return out  # fraud flag deliberately not loaded


def clean_mix(d: dict) -> tuple[list[str], np.ndarray]:
    items = [(k, v) for k, v in d.items() if not k.startswith("_")]
    w = np.array([v for _, v in items], dtype=float)
    return [k for k, _ in items], w / w.sum()


# --------------------------------------------------------------------------- generator
class Builder:
    def __init__(self, p: dict, am: dict, kaggle: pd.DataFrame | None, timing_scale: float = 1.0):
        self.p, self.am, self.kaggle, self.ts = p, am, kaggle, timing_scale
        self.rng = np.random.default_rng(p["seed"])
        hp = np.array(p["hour_profile_assumption"], dtype=float)
        self.hour_p = hp / hp.sum()
        self.hours = None
        self.merchant_cats = None
        if kaggle is not None:
            if kaggle["hour"].notna().any():
                self.hours = kaggle["hour"].dropna().astype(int).to_numpy()
            if kaggle["merchant_category"].notna().any():
                vc = kaggle.loc[kaggle.payment_type == "P2M", "merchant_category"].value_counts(normalize=True)
                self.merchant_cats = (vc.index.to_numpy(), vc.to_numpy())
        self.events: list[dict] = []
        self.sessions: list[dict] = []
        self.umbrellas: dict[str, list[str]] = {}
        for umb, pb in p["icfd_umbrellas"].items():
            if not umb.startswith("_"):
                self.umbrellas.setdefault(pb, []).append(umb)

    # ---- helpers
    def u(self, lo_hi, scale: float = 1.0) -> float:
        lo, hi = lo_hi
        return float(self.rng.uniform(lo * scale, hi * scale))

    def t(self, lo_hi) -> float:  # scam timing, subject to --timing-scale
        return self.u(lo_hi, self.ts)

    def start_hour(self) -> int:
        if self.hours is not None:
            return int(self.hours[int(self.rng.integers(len(self.hours)))])
        return int(self.rng.choice(24, p=self.hour_p))

    def user_amount(self, user: dict, ptype: str | None = None) -> tuple[float, str]:
        """Legit amount from this user's own distribution (population marginal still matches NPCI)."""
        if ptype is None:
            ptype = "P2M" if self.rng.random() < self.am["w_p2m"] else "P2P"
        mu, _ = self.am["p2m" if ptype == "P2M" else "p2p"]
        s_w = self.am["p2m_within" if ptype == "P2M" else "p2p_within"]
        a = float(self.rng.lognormal(mu + user["log_scale"], s_w))
        return (min(a, self.am["cap"]) if ptype == "P2P" else a), ptype

    def ev(self, sid, uid, t, etype, **kw):
        row = {k: None for k in EVENT_COLUMNS}
        row.update(session_id=sid, user_id=uid, t_sec=float(t), event_type=etype, is_duplicate=False, **kw)
        self.events.append(row)

    def pay(self, sid, uid, t, amount, ptype, payee, new, channel="upi", initiator="user"):
        mcat = None
        if ptype == "P2M" and self.merchant_cats is not None:
            mcat = str(self.rng.choice(self.merchant_cats[0], p=self.merchant_cats[1]))
        self.ev(sid, uid, t, "PAYMENT_ATTEMPT", payee_id=payee, payee_is_new=new, amount_inr=round(amount, 2),
                payment_type=ptype, merchant_category=mcat, channel=channel, initiator=initiator)

    def known_payee(self, user):
        return f"{user['user_id']}-P{int(self.rng.integers(1, user['n_known_payees'] + 1))}"

    # ---- users
    def make_users(self) -> pd.DataFrame:
        c, n, nz = self.p["cohorts"], self.p["n_users"], self.p["noise"]
        tiers = self.rng.choice(len(c["activity_tiers"]), size=n)
        ages = self.rng.choice(c["age_bands"], size=n, p=c["age_weights_legit"])
        log_scale = self.rng.normal(0, self.am["user_sigma"], size=n)
        rows = []
        for i in range(n):
            u = {"user_id": f"U{i:05d}", "log_scale": float(log_scale[i]), "n_known_payees": int(self.rng.integers(3, 40))}
            hist = [self.user_amount(u)[0] for _ in range(40)]  # pre-period history from the SAME distribution
            med = float(np.median(hist))
            u.update({
                "age_band": str(ages[i]),
                "activity_tier": c["activity_tiers"][tiers[i]],
                "payments_per_month": c["activity_payments_per_month"][tiers[i]],
                "hist_median_inr": round(med, 2),
                "hist_mad_inr": round(float(np.median(np.abs(np.array(hist) - med))) or 1.0, 2),
                "call_state_available": bool(self.rng.random() >= nz["oem_no_call_state"]),
                "usage_access": bool(self.rng.random() >= nz["no_usage_access"]),
            })
            rows.append(u)
        users = pd.DataFrame(rows)
        order = self.rng.permutation(n)
        s = self.p["splits"]
        n_tr, n_ca = int(n * s["train"]), int(n * s["calibration"])
        split = np.empty(n, dtype=object)
        split[order[:n_tr]], split[order[n_tr:n_tr + n_ca]], split[order[n_tr + n_ca:]] = "train", "calibration", "validation"
        users["split"] = split
        return users

    # ---- legitimate sessions
    def legit_session(self, sid, user, kind):
        uid = user["user_id"]
        known, newp = self.known_payee(user), f"NEW-{sid}"
        amt, ptype = self.user_amount(user)
        if kind == "plain_payment":
            is_new = self.rng.random() < (0.35 if ptype == "P2M" else 0.10)
            if is_new:
                self.ev(sid, uid, 0, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, self.u([5, 60]), amt, ptype, newp if is_new else known, is_new)
        elif kind == "call_then_known_payment":
            self.ev(sid, uid, 0, "CALL_START", caller_known=True, call_direction=str(self.rng.choice(["incoming", "outgoing"])))
            t = self.u([30, 1200])
            self.pay(sid, uid, t, amt, ptype, known, False)
            self.ev(sid, uid, t + self.u([10, 600]), "CALL_END")
        elif kind == "hn_out_of_order":  # payment first, unknown call later, new payee after
            self.pay(sid, uid, 0, amt, ptype, known, False)
            t = self.u([120, 3300])
            self.ev(sid, uid, t, "CALL_START", caller_known=False, call_direction="incoming")
            self.ev(sid, uid, t + self.u([30, 900]), "CALL_END")
            if self.rng.random() < 0.7:
                self.ev(sid, uid, t + self.u([300, 3000]), "NEW_PAYEE", payee_id=newp, payee_is_new=True)
        elif kind == "hn_long_gap":  # unknown call, new payee + payment 61-240 min later
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="incoming")
            self.ev(sid, uid, self.u([30, 900]), "CALL_END")
            t = self.u([3660, 14400])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, t + self.u([20, 600]), amt, ptype, newp, True)
        elif kind == "hn_legit_remote":  # genuine IT support via Play-store remote app
            self.ev(sid, uid, 0, "CALL_START", caller_known=bool(self.rng.random() < 0.3), call_direction="outgoing")
            t = self.u([60, 900])
            app = str(self.rng.choice(self.p["watchlisted_remote_apps"]))
            self.ev(sid, uid, t, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t + self.u([5, 120]), "APP_FOREGROUND", app_package=app)
            end = t + self.u([300, 3600])
            if self.rng.random() < 0.2:  # sometimes pays a known merchant later (e.g. service fee)
                self.pay(sid, uid, end - self.u([10, 200]), min(amt, 3000), "P2M", known, False)
            self.ev(sid, uid, end, "CALL_END")
        elif kind == "hn_family_video":  # long video call with known contact + known payment
            app = str(self.rng.choice(self.p["video_apps"]))
            self.ev(sid, uid, 0, "VIDEO_SESSION_START", caller_known=True, app_package=app)
            dur = self.u([600, 4 * 3600])
            self.pay(sid, uid, self.u([60, dur - 30]), amt, ptype, known, False)
            self.ev(sid, uid, dur, "VIDEO_SESSION_END", app_package=app)
        elif kind == "hn_cod_delivery":  # delivery agent (unknown number) + pay a new merchant
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="incoming")
            t = self.u([20, 900])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, t + self.u([10, 300]), self.user_amount(user, "P2M")[0] * self.u([1, 3]), "P2M", newp, True)
            self.ev(sid, uid, t + self.u([60, 900]), "CALL_END")
        elif kind == "hn_family_emergency":  # GENUINE: relative calls from a new number, money to a new payee
            fe = self.p["legit_special_amounts_inr"]["family_emergency"]
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="incoming")
            t = self.u([60, 1200])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            a = float(self.rng.lognormal(math.log(fe["median"]), fe["sigma"]))
            self.pay(sid, uid, t + self.u([20, 900]), min(a, self.am["cap"]), "P2P", newp, True)
            self.ev(sid, uid, t + self.u([60, 1800]), "CALL_END")
        elif kind == "hn_rent_salary_day":  # large but known payee, no call
            m = self.u(self.p["legit_special_amounts_inr"]["rent_multiple_of_user_median"])
            self.pay(sid, uid, self.u([5, 120]), min(user["hist_median_inr"] * m, self.am["cap"]), "P2P", known, False)
        elif kind == "hn_festival_spike":  # several larger merchant payments, some new merchants
            t = 0.0
            for _ in range(int(self.rng.integers(2, 6))):
                t += self.u([60, 1800])
                new = bool(self.rng.random() < 0.5)
                pid = f"NEW-{sid}-{int(t)}" if new else known
                if new:
                    self.ev(sid, uid, t - 5, "NEW_PAYEE", payee_id=pid, payee_is_new=True)
                a = self.user_amount(user, "P2M")[0] * self.u(self.p["legit_special_amounts_inr"]["festival_multiple"])
                self.pay(sid, uid, t, a, "P2M", pid, new)
        else:
            raise ValueError(kind)

    # ---- scam sessions
    def scam_session(self, sid, user, playbook, day):
        uid = user["user_id"]
        tm, sa = self.p["timing_seconds"][playbook], self.p["scam_amounts_inr"][playbook]
        dr = self.p["drift"]
        payee = f"MULE-{sid}"
        direction = "outgoing" if (playbook == "remote_access" and self.rng.random() < 0.3) else "incoming"
        self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction=direction)
        n_pay = int(self.rng.integers(tm["n_payments"][0], tm["n_payments"][1] + 1))
        amounts = self.rng.lognormal(math.log(sa["median"]), sa["sigma"], size=n_pay)
        cap = self.am["cap"]

        if playbook == "remote_access":
            t = self.t(tm["call_to_install"])
            app = (dr["new_remote_app"] if (day >= dr["from_day"] and self.rng.random() < dr["new_app_share"])
                   else str(self.rng.choice(self.p["watchlisted_remote_apps"])))
            self.ev(sid, uid, t, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t + self.u([5, 60]), "APP_FOREGROUND", app_package=app)
            t += self.t(tm["install_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.t(tm["payee_to_payment"])
            for a in amounts:
                self.pay(sid, uid, t, min(a, cap), "P2P", payee, True)
                t += self.u([15, 180])
            self.ev(sid, uid, t + self.u([30, 600]), "CALL_END")

        elif playbook == "malicious_apk":
            t = self.t(tm["call_to_install"])
            self.ev(sid, uid, t, "APP_INSTALL", app_package=f"apk.unknown.{int(self.rng.integers(1e6))}", install_source="sideload")
            self.ev(sid, uid, t + self.u([60, 600]), "CALL_END")
            t += self.t(tm["install_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.t(tm["payee_to_payment"])
            for a in amounts:
                self.pay(sid, uid, t, a, "P2P", payee, True, channel="upi" if a <= cap else "bank_transfer", initiator="remote")
                t += self.u([30, 900])

        elif playbook == "digital_arrest":
            t = self.t(tm["call_to_video"])
            app = str(self.rng.choice(self.p["video_apps"]))
            if self.rng.random() < 0.6:
                self.ev(sid, uid, t - 30, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t, "CALL_END")
            self.ev(sid, uid, t + 5, "VIDEO_SESSION_START", caller_known=False, app_package=app)
            video_end = t + self.t(tm["video_hours"]) * 3600
            tp = min(t + self.t(tm["video_to_payee_hours"]) * 3600, video_end - 600)
            self.ev(sid, uid, tp, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            for a in amounts:
                tp += self.u([300, 6 * 3600])
                self.pay(sid, uid, tp, a, "P2P", payee, True, channel="upi" if a <= cap else "bank_transfer")
            self.ev(sid, uid, max(video_end, tp + 60), "VIDEO_SESSION_END", app_package=app)

        elif playbook == "family_emergency_scam":  # evil twin of hn_family_emergency
            t = self.t(tm["call_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.t(tm["payee_to_payment"])
            for a in amounts:
                self.pay(sid, uid, t, min(a, cap), "P2P", payee, True)
                t += self.u([60, 900])
            self.ev(sid, uid, t + self.u([30, 900]), "CALL_END")

        elif playbook == "screen_share":  # screen shared over a video app already installed; no install event
            t = self.t(tm["call_to_share"])
            app = "com.whatsapp"
            self.ev(sid, uid, t, "VIDEO_SESSION_START", caller_known=False, app_package=app)
            share_end = t + self.t(tm["share_minutes"]) * 60
            t += self.t(tm["share_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.t(tm["payee_to_payment"])
            for a in amounts:
                self.pay(sid, uid, t, min(a, cap), "P2P", payee, True)
                t += self.u([30, 600])
            self.ev(sid, uid, max(share_end, t), "VIDEO_SESSION_END", app_package=app)
            self.ev(sid, uid, max(share_end, t) + self.u([10, 600]), "CALL_END")

    # ---- calendar
    def legit_day(self, kind) -> int:
        cal = self.p["calendar"]
        if kind == "hn_rent_salary_day":
            return int(np.clip(int(self.rng.choice(cal["month_start_days"])) + int(self.rng.integers(-2, 3)), 0, cal["days"] - 1))
        if kind == "hn_festival_spike":
            return int(self.rng.integers(cal["festival_days"][0], cal["festival_days"][1] + 1))
        return int(self.rng.integers(0, cal["days"]))

    # ---- orchestration
    def build(self, users: pd.DataFrame):
        p, c = self.p, self.p["cohorts"]
        recs = users.to_dict("records")
        act = np.array(users.payments_per_month, dtype=float)
        legit_w = act / act.sum()
        ratio = {b: s / l for b, s, l in zip(c["age_bands"], c["age_weights_scam"], c["age_weights_legit"])}
        scam_w = np.array(users.age_band.map(ratio), dtype=float)
        scam_w = scam_w / scam_w.sum()

        kinds, kw = clean_mix(p["legit_kinds"])
        legit_kinds = self.rng.choice(kinds, size=p["n_legit_sessions"], p=kw)
        pb0, pw0 = clean_mix(p["playbook_mix"])
        pb1, pw1 = clean_mix(p["drift"]["playbook_mix_after"])

        jobs = [("legit", k) for k in legit_kinds] + [("scam", None)] * p["n_scam_sessions"]
        src = "generated" if self.kaggle is None else "generated+kaggle_hours_merchants"
        for i, (label, kind) in enumerate(jobs):
            sid = f"S{i:06d}"
            if label == "legit":
                user = recs[int(self.rng.choice(len(recs), p=legit_w))]
                day = self.legit_day(kind)
                self.legit_session(sid, user, kind)
                playbook, umb = "none", "none"
            else:
                user = recs[int(self.rng.choice(len(recs), p=scam_w))]
                day = int(self.rng.integers(0, p["calendar"]["days"]))
                names, w = (pb1, pw1) if day >= p["drift"]["from_day"] else (pb0, pw0)
                playbook = str(self.rng.choice(names, p=w))
                self.scam_session(sid, user, playbook, day)
                kind, umb = "scam", str(self.rng.choice(self.umbrellas[playbook]))
            self.sessions.append({
                "session_id": sid, "user_id": user["user_id"], "label": label, "session_kind": kind,
                "playbook": playbook, "scam_type_icfd": umb, "age_band": user["age_band"],
                "activity_tier": user["activity_tier"], "day": day, "week": day // 7, "start_hour": self.start_hour(),
                "split": user["split"], "call_state_available": user["call_state_available"],
                "usage_access": user["usage_access"], "source": src, "linkage": "synthetic",
            })

        sessions = pd.DataFrame(self.sessions)
        events = pd.DataFrame(self.events, columns=EVENT_COLUMNS).drop(columns=["split", "day"])
        events = events.merge(sessions[["session_id", "split", "day", "start_hour", "call_state_available", "usage_access"]],
                              on="session_id")
        events = self.apply_noise(events)
        events["ts_abs"] = (events.day * 86400 + events.start_hour * 3600 + events.t_sec).round().astype("int64")
        events["t_sec"] = events.t_sec.round().astype("int64")
        events = events.sort_values(["session_id", "t_sec"], kind="stable")[EVENT_COLUMNS]
        sessions["label_observed"] = sessions.label
        flip = self.rng.random(len(sessions)) < p["noise"]["label_flip"]
        sessions.loc[flip, "label_observed"] = np.where(sessions.loc[flip, "label"] == "scam", "legit", "scam")
        return sessions, events

    # ---- device noise
    def apply_noise(self, ev: pd.DataFrame) -> pd.DataFrame:
        nz = self.p["noise"]
        drop = (~ev.call_state_available & ev.event_type.isin(["CALL_START", "CALL_END"])) | (
            ~ev.usage_access & ev.event_type.isin(["APP_FOREGROUND", "VIDEO_SESSION_START", "VIDEO_SESSION_END"]))
        ev = ev[~drop].copy()
        jit = self.rng.random(len(ev)) < nz["jitter_prob"]
        ev.loc[jit, "t_sec"] += self.rng.uniform(0, nz["jitter_max_s"], jit.sum())
        dup = ev[self.rng.random(len(ev)) < nz["duplicate_prob"]].copy()
        dup["t_sec"] += self.rng.uniform(0, 2, len(dup))
        dup["is_duplicate"] = True
        return pd.concat([ev, dup], ignore_index=True).drop(columns=["call_state_available", "usage_access"])


# --------------------------------------------------------------------------- probes
def naive_rule(events: pd.DataFrame) -> pd.Series:
    """Unknown call + new payee + payment within 60 min of the call, before or after (order ignored)."""
    e = events[~events.is_duplicate]
    unk = e[e.event_type.isin(["CALL_START", "VIDEO_SESSION_START"]) & (e.caller_known == False)]  # noqa: E712
    t0 = unk.groupby("session_id").t_sec.min().rename("t0")
    w = e.merge(t0, left_on="session_id", right_index=True)
    w = w[(w.t_sec >= w.t0 - 3600) & (w.t_sec <= w.t0 + 3600)]
    has_payee = w[w.event_type == "NEW_PAYEE"].session_id.unique()
    has_pay = w[w.event_type == "PAYMENT_ATTEMPT"].session_id.unique()
    flagged = set(has_payee) & set(has_pay)
    return pd.Series({s: (s in flagged) for s in events.session_id.unique()})


def watchlist_rule(events: pd.DataFrame, watchlist: list[str]) -> pd.Series:
    """Unknown call + install of a watch-listed remote-access app (drift probe)."""
    e = events[~events.is_duplicate]
    hit = set(e[(e.event_type == "APP_INSTALL") & e.app_package.isin(watchlist)].session_id)
    return pd.Series({s: (s in hit) for s in events.session_id.unique()})


def realism_check(sessions, events, kaggle) -> list[str]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    if kaggle is None or kaggle.merchant_category.isna().all():
        return ["Not run (needs --kaggle-upi)."]
    sim = events[(events.event_type == "PAYMENT_ATTEMPT") & (events.payment_type == "P2M") & events.merchant_category.notna()]
    sim = sim.merge(sessions[["session_id", "label", "start_hour"]], on="session_id")
    sim = sim[sim.label == "legit"][["start_hour", "merchant_category"]].rename(columns={"start_hour": "hour"})
    ref = kaggle[kaggle.payment_type == "P2M"][["hour", "merchant_category"]].dropna()
    n = min(len(sim), len(ref), 30000)
    df = pd.concat([sim.sample(n, random_state=0).assign(y=1), ref.sample(n, random_state=0).assign(y=0)])
    X = pd.get_dummies(df[["hour", "merchant_category"]].astype(str), dtype=float)
    a, b, ya, yb = train_test_split(X, df.y, test_size=0.3, random_state=0, stratify=df.y)
    auc = roc_auc_score(yb, HistGradientBoostingClassifier(max_iter=100).fit(a, ya).predict_proba(b)[:, 1])
    return [f"- Classifier separating SatarkSim P2M rows from Kaggle P2M rows on hour + merchant category: "
            f"**AUC {auc:.3f}** (≈0.5 = indistinguishable).",
            "- Amounts are checked against NPCI quantiles in §1 instead: no row-level real UPI data exists to compare against."]


# --------------------------------------------------------------------------- report
def report(out, p, am, users, sessions, events, heldout_hash, kaggle, npci_note, timing_scale) -> str:
    L = ["# SatarkSim v2 build report", "", f"Average-ticket source: {npci_note}. Timing scale: {timing_scale}×.", ""]
    ev = events[~events.is_duplicate].merge(sessions[["session_id", "label", "session_kind"]], on="session_id")
    lp = ev[(ev.label == "legit") & (ev.event_type == "PAYMENT_ATTEMPT") & ev.session_kind.isin(["plain_payment", "call_then_known_payment"])]
    p2m, p2p = lp[lp.payment_type == "P2M"].amount_inr, lp[lp.payment_type == "P2P"].amount_inr
    L += ["## 1. Calibration against NPCI targets (regular legit payments)", "",
          "| Quantity | Target | SatarkSim |", "|---|---|---|",
          f"| P2M share of volume | {p['npci']['p2m_share_of_volume']:.2f} | {len(p2m) / max(len(lp), 1):.2f} |",
          f"| P2M payments < ₹500 | {p['npci']['p2m_share_below_500']:.2f} | {(p2m < 500).mean():.2f} |",
          f"| P2P payments < ₹500 | {p['npci']['p2p_share_below_500']:.2f} | {(p2p < 500).mean():.2f} |",
          f"| Average ticket (₹) | {am['target_mean']:.0f} | {lp.amount_inr.mean():.0f} (sample; heavy tail varies by seed) |", ""]

    # per-user consistency
    pu = lp.merge(users[["user_id", "hist_median_inr"]], on="user_id").groupby("user_id").agg(
        n=("amount_inr", "size"), sess_median=("amount_inr", "median"), hist_med=("hist_median_inr", "first"))
    pu = pu[pu.n >= 5]
    rho = spearmanr(pu["sess_median"], pu["hist_med"]).statistic
    L += ["## 1a. Per-user consistency (v1 bug fixed)", "",
          f"- Spearman correlation between each user's history median and the median of their session payments "
          f"({len(pu):,} users with ≥5 payments): **{rho:.2f}**. In v1 this was ≈0 because amounts ignored the user.", ""]

    alpha = p.get("target_false_pause_alpha", 0.001)
    need = int(math.ceil(1 / alpha - 1))
    cal = sessions[(sessions.split == "calibration") & (sessions.label == "legit")].groupby("age_band").size()
    L += ["## 1b. Can the false-pause target be certified per cohort?", "",
          f"Split-conformal needs ≥ 1/α − 1 = **{need}** legit calibration sessions per cohort (α = {alpha:.1%}).", "",
          "| Age band | Legit calibration sessions | Enough? |", "|---|---|---|"]
    L += [f"| {g} | {n} | {'yes' if n >= need else '**no**'} |" for g, n in cal.items()] + [""]

    leak = users.groupby("user_id").split.nunique().max()
    tab = sessions.groupby(["split", "label"]).size().unstack(fill_value=0)
    L += ["## 2. Split integrity", "", f"- Users in more than one split: **{int(leak > 1)}** (must be 0)", "",
          "| Split | Legit | Scam |", "|---|---|---|"]
    L += [f"| {s} | {r.get('legit', 0)} | {r.get('scam', 0)} |" for s, r in tab.iterrows()] + [""]

    nz = p["noise"]
    L += ["## 2a. Device noise applied", "",
          f"- Users without call state (OEM): {(~users.call_state_available).mean():.1%} · without usage access: {(~users.usage_access).mean():.1%}",
          f"- Duplicate events: {events.is_duplicate.mean():.1%} · timestamp jitter on {nz['jitter_prob']:.0%} of events (≤{nz['jitter_max_s']} s)",
          f"- Observed labels flipped: {(sessions.label != sessions.label_observed).mean():.1%}. **Train on `label_observed`; evaluate on `label`.**", ""]

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    x = pd.get_dummies(sessions[["start_hour"]].astype(str))
    y = (sessions.label == "scam").astype(int)
    tr, va = sessions.split == "train", sessions.split == "validation"
    auc = roc_auc_score(y[va], LogisticRegression(max_iter=1000).fit(x[tr], y[tr]).predict_proba(x[va])[:, 1])
    L += ["## 3. Artefact probe", "",
          f"- AUC predicting scam from start hour alone: **{auc:.3f}** (≈0.5 expected; hour is drawn independently of the label).",
          "- Not probed, because they carry signal by design: age band (scams target older users), activity tier (scams are a "
          "larger share of low-activity users' sessions), and week (scam mix drifts after week 6). Never use age band as a feature.", ""]

    L += ["## 3a. Realism check against Kaggle UPI 2024", ""] + realism_check(sessions, events, kaggle) + [""]

    flags = naive_rule(events).rename("naive").rename_axis("session_id").reset_index()
    s = sessions.merge(flags, on="session_id")
    v = s[s.split == "validation"]
    L += ["## 4. Difficulty probe (naive rule, validation split)", "",
          "Rule: unknown call + new payee + payment within 60 min of the call, order ignored. This is the baseline to beat.", "",
          f"- Recall: **{v[v.label == 'scam'].naive.mean():.2f}** · False-flag rate on legit: **{v[v.label == 'legit'].naive.mean():.3f}**", "",
          "| Scam playbook | Naive recall |", "|---|---|"]
    L += [f"| {k} | {val:.2f} |" for k, val in v[v.label == "scam"].groupby("playbook").naive.mean().items()]
    L += ["", "| Legit kind | Naive false-flag rate |", "|---|---|"]
    L += [f"| {k} | {val:.2f} |" for k, val in v[v.label == "legit"].groupby("session_kind").naive.mean().items()] + [""]
    L += ["`hn_family_emergency` vs `family_emergency_scam` is the hardest pair by design: same event sequence, "
          "differing only in amounts relative to the user and number of payments.", ""]

    wl = watchlist_rule(events, p["watchlisted_remote_apps"]).rename("wl").rename_axis("session_id").reset_index()
    ra = sessions[(sessions.playbook == "remote_access")].merge(wl, on="session_id")
    before, after = ra[ra.day < p["drift"]["from_day"]].wl.mean(), ra[ra.day >= p["drift"]["from_day"]].wl.mean()
    L += ["## 4a. Drift probe", "",
          f"Watch-list rule (unknown call + install of a named remote-access app) on remote-access scams: "
          f"**{before:.2f}** recall before day {p['drift']['from_day']}, **{after:.2f}** after (a new app appears). "
          "A static watch-list decays; this is what the install-during-call signal and rolling recalibration are for. "
          "For drift tests, calibrate on weeks 0–5 and test on weeks 6–11.", ""]

    L += ["## 5. Held-out set", "", f"- Copied untouched to `heldout/`. SHA-256: `{heldout_hash}`. Not used in this build.", ""]
    L += ["## 6. Provenance", "",
          "- Every row is `linkage=synthetic`: SatarkSim shows the logic works on simulated data, not real-world accuracy.",
          "- Scam timings and amounts are labelled assumptions in `params.json`; see `sensitivity_report.md`. "
          "They were deliberately NOT fitted to the held-out cases.",
          "- ICFD-31k: umbrella names only. Kaggle UPI: hour-of-day and merchant mix only (amounts and fraud flag unused).", ""]
    text = "\n".join(L)
    (out / "validation_report.md").write_text(text)
    return text


def build_all(p, am, kaggle, timing_scale):
    b = Builder(p, am, kaggle, timing_scale)
    users = b.make_users()
    sessions, events = b.build(users)
    return users, sessions, events


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--params", type=Path, default=Path(__file__).with_name("params.json"))
    ap.add_argument("--heldout", type=Path, required=True)
    ap.add_argument("--kaggle-upi", type=Path, default=None)
    ap.add_argument("--npci-xlsx", type=Path, default=None)
    ap.add_argument("--timing-scale", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=Path("data"))
    a = ap.parse_args()

    p = json.loads(a.params.read_text())
    npci_note, target = "secondary reports in params.json", None
    if a.npci_xlsx:
        target, span = npci_avg_ticket(a.npci_xlsx)
        npci_note = f"official NPCI workbook ({span}): ₹{target:,.0f}"
    am = fit_amount_model(p, target)
    kaggle = load_kaggle(a.kaggle_upi)
    users, sessions, events = build_all(p, am, kaggle, a.timing_scale)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "heldout").mkdir(exist_ok=True)
    users.drop(columns=["log_scale"]).to_csv(a.out / "satarksim_users.csv", index=False)
    sessions.to_csv(a.out / "satarksim_sessions.csv", index=False)
    events.to_csv(a.out / "satarksim_events.csv", index=False)
    shutil.copyfile(a.heldout, a.out / "heldout" / "heldout_events.csv")
    h = hashlib.sha256((a.out / "heldout" / "heldout_events.csv").read_bytes()).hexdigest()
    (a.out / "heldout" / "SHA256").write_text(h + "\n")
    (a.out / "amount_model.json").write_text(json.dumps(am, indent=2))
    print(report(a.out, p, am, users, sessions, events, h, kaggle, npci_note, a.timing_scale))


if __name__ == "__main__":
    main()
