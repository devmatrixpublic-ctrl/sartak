#!/usr/bin/env python3
"""Build SatarkSim: one event table that merges Satark's data sources.

What goes in, and how:
  * NPCI statistics          -> calibrate legitimate payment amounts and P2P/P2M mix (params.json)
  * Kaggle UPI Transactions  -> optional --kaggle-upi CSV; if given, legit amounts and hours are
                                resampled from it (its fraud flag is never read)
  * ICFD-31k                 -> scam-type taxonomy only (umbrella names); no transcript content
  * Generated signals        -> call / app-install / video / payee / payment events per session
  * Held-out real cases      -> copied untouched into data/heldout/ with a SHA-256 fingerprint;
                                NEVER mixed into train/calibration/validation

Usage:
  python build_satarksim.py --params params.json --heldout ../../satark-heldout-events.csv \
      [--kaggle-upi upi_transactions_2024.csv] --out data
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
from scipy.stats import norm

EVENT_COLUMNS = [
    "session_id", "user_id", "split", "t_sec", "event_type", "caller_known", "call_direction",
    "app_package", "install_source", "payee_id", "payee_is_new", "amount_inr", "payment_type",
    "merchant_category", "channel", "initiator",
]


# --------------------------------------------------------------------------- amount calibration
def capped_lognormal_mean(mu: float, sigma: float, cap: float) -> float:
    """E[min(X, cap)] for X ~ LogNormal(mu, sigma)."""
    lc = math.log(cap)
    body = math.exp(mu + sigma**2 / 2) * norm.cdf((lc - mu - sigma**2) / sigma)
    tail = cap * (1 - norm.cdf((lc - mu) / sigma))
    return body + tail


def npci_avg_ticket(xlsx: Path) -> tuple[float, str]:
    """Average ticket (value / volume) over all months in the official NPCI product-statistics workbook."""
    n = pd.read_excel(xlsx, header=0)
    n.columns = ["month", "banks", "vol_mn", "val_cr"][: len(n.columns)]
    for c in ("vol_mn", "val_cr"):
        n[c] = n[c].astype(str).str.replace(r"[,\s]", "", regex=True).astype(float)
    n = n.dropna(subset=["vol_mn", "val_cr"])
    return float(n.val_cr.sum() * 1e7 / (n.vol_mn.sum() * 1e6)), f"{n.month.iloc[-1]} to {n.month.iloc[0]}"


def fit_amount_model(p: dict, target_mean: float | None = None) -> dict:
    """Solve lognormal parameters so quantile shares and the NPCI average ticket are matched."""
    npci, am = p["npci"], p["amount_model"]
    if target_mean is None:
        target_mean = npci["monthly_value_inr"] / npci["monthly_volume_txns"]
    w_p2m = npci["p2m_share_of_volume"]
    cap = am["upi_p2p_cap_inr"]

    s_m = am["p2m_sigma"]
    mu_m = math.log(500) - norm.ppf(npci["p2m_share_below_500"]) * s_m
    mean_m = math.exp(mu_m + s_m**2 / 2)

    z_p = norm.ppf(npci["p2p_share_below_500"])

    def gap(s_p: float) -> float:
        mu_p = math.log(500) - z_p * s_p
        return w_p2m * mean_m + (1 - w_p2m) * capped_lognormal_mean(mu_p, s_p, cap) - target_mean

    s_p = brentq(gap, 0.3, 5.0)
    mu_p = math.log(500) - z_p * s_p
    return {"target_mean": target_mean, "p2m": (mu_m, s_m), "p2p": (mu_p, s_p), "cap": cap, "w_p2m": w_p2m}


# --------------------------------------------------------------------------- optional Kaggle input
def load_kaggle(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    amount = next((cols[c] for c in cols if c.startswith("amount")), None)
    if amount is None:
        raise SystemExit(f"No amount column found in {path}; columns: {list(df.columns)}")
    ttype = next((cols[c] for c in cols if "type" in c and "transaction" in c), None)
    hour = next((cols[c] for c in cols if c in ("hour_of_day", "hour")), None)
    out = pd.DataFrame({"amount": pd.to_numeric(df[amount], errors="coerce")})
    out["payment_type"] = (
        df[ttype].astype(str).str.upper().map(lambda v: "P2P" if "P2P" in v else "P2M") if ttype else "P2M"
    )
    out["hour"] = pd.to_numeric(df[hour], errors="coerce") if hour else np.nan
    mc = cols.get("merchant_category")
    out["merchant_category"] = df[mc].astype(str) if mc else None
    # The dataset's fraud flag is deliberately ignored: it comes from the generator's own rules.
    return out.dropna(subset=["amount"]).query("amount > 0")


# --------------------------------------------------------------------------- generator
class Builder:
    def __init__(self, p: dict, amount_model: dict, kaggle: pd.DataFrame | None, kaggle_amounts: bool = False):
        self.p = p
        self.am = amount_model
        self.kaggle = kaggle
        self.kaggle_amounts = kaggle_amounts
        self.merchant_cats = None
        if kaggle is not None and kaggle["merchant_category"].notna().any():
            vc = kaggle.loc[kaggle.payment_type == "P2M", "merchant_category"].value_counts(normalize=True)
            self.merchant_cats = (vc.index.to_numpy(), vc.to_numpy())
        self.rng = np.random.default_rng(p["seed"])
        hp = np.array(p["hour_profile_assumption"], dtype=float)
        self.hour_p = hp / hp.sum()
        self.events: list[dict] = []
        self.sessions: list[dict] = []
        self.umbrella_by_playbook: dict[str, list[str]] = {}
        for umb, pb in p["icfd_umbrellas"].items():
            if not umb.startswith("_"):
                self.umbrella_by_playbook.setdefault(pb, []).append(umb)

    # ---- users
    def make_users(self) -> pd.DataFrame:
        c, n = self.p["cohorts"], self.p["n_users"]
        tiers = self.rng.choice(len(c["activity_tiers"]), size=n)
        rows = []
        for i in range(n):
            amounts = [self.legit_amount()[0] for _ in range(40)]
            med = float(np.median(amounts))
            mad = float(np.median(np.abs(np.array(amounts) - med))) or 1.0
            rows.append({
                "user_id": f"U{i:05d}",
                "activity_tier": c["activity_tiers"][tiers[i]],
                "payments_per_month": c["activity_payments_per_month"][tiers[i]],
                "hist_median_inr": round(med, 2),
                "hist_mad_inr": round(mad, 2),
                "n_known_payees": int(self.rng.integers(3, 40)),
            })
        users = pd.DataFrame(rows)
        # split by user so no user appears in two splits
        order = self.rng.permutation(n)
        s = self.p["splits"]
        n_tr, n_ca = int(n * s["train"]), int(n * s["calibration"])
        split = np.empty(n, dtype=object)
        split[order[:n_tr]] = "train"
        split[order[n_tr:n_tr + n_ca]] = "calibration"
        split[order[n_tr + n_ca:]] = "validation"
        users["split"] = split
        return users

    # ---- amounts and hours
    def legit_amount(self) -> tuple[float, str]:
        if self.kaggle is not None and self.kaggle_amounts:
            row = self.kaggle.iloc[int(self.rng.integers(len(self.kaggle)))]
            return float(row["amount"]), str(row["payment_type"])
        if self.rng.random() < self.am["w_p2m"]:
            mu, s = self.am["p2m"]
            return float(self.rng.lognormal(mu, s)), "P2M"
        mu, s = self.am["p2p"]
        return float(min(self.rng.lognormal(mu, s), self.am["cap"])), "P2P"

    def start_hour(self) -> int:
        if self.kaggle is not None and self.kaggle["hour"].notna().any():
            if not hasattr(self, "_hours"):
                self._hours = self.kaggle["hour"].dropna().astype(int).to_numpy()
            return int(self._hours[int(self.rng.integers(len(self._hours)))])
        return int(self.rng.choice(24, p=self.hour_p))

    def u(self, lo_hi) -> float:
        lo, hi = lo_hi
        return float(self.rng.uniform(lo, hi))

    # ---- event helpers
    def ev(self, sid, uid, t, etype, **kw):
        row = {k: None for k in EVENT_COLUMNS}
        row.update(session_id=sid, user_id=uid, t_sec=int(round(t)), event_type=etype, **kw)
        self.events.append(row)

    def pay(self, sid, uid, t, amount, ptype, payee, new, channel="upi", initiator="user"):
        mcat = None
        if ptype == "P2M" and self.merchant_cats is not None:
            mcat = str(self.rng.choice(self.merchant_cats[0], p=self.merchant_cats[1]))
        self.ev(sid, uid, t, "PAYMENT_ATTEMPT", payee_id=payee, payee_is_new=new, amount_inr=round(amount, 2),
                payment_type=ptype, merchant_category=mcat, channel=channel, initiator=initiator)

    # ---- legitimate sessions
    def legit_session(self, sid: str, uid: str, kind: str):
        known = f"{uid}-P{int(self.rng.integers(1, 30))}"
        newp = f"NEW-{sid}"
        amt, ptype = self.legit_amount()
        if kind == "plain_payment":
            is_new = self.rng.random() < (0.35 if ptype == "P2M" else 0.10)  # new merchants are normal
            if is_new:
                self.ev(sid, uid, 0, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, self.u([5, 60]), amt, ptype, newp if is_new else known, is_new)
        elif kind == "call_then_known_payment":
            self.ev(sid, uid, 0, "CALL_START", caller_known=True, call_direction="incoming")
            t = self.u([60, 900])
            self.pay(sid, uid, t, amt, ptype, known, False)
            self.ev(sid, uid, t + self.u([10, 300]), "CALL_END")
        elif kind == "hn_out_of_order":  # payment first, then unknown call, then new payee
            self.pay(sid, uid, 0, amt, ptype, known, False)
            t = self.u([600, 3000])
            self.ev(sid, uid, t, "CALL_START", caller_known=False, call_direction="incoming")
            self.ev(sid, uid, t + self.u([60, 600]), "CALL_END")
            self.ev(sid, uid, t + self.u([700, 2400]), "NEW_PAYEE", payee_id=newp, payee_is_new=True)
        elif kind == "hn_long_gap":  # unknown call, new payee + payment much later (>60 min)
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="incoming")
            self.ev(sid, uid, self.u([60, 600]), "CALL_END")
            t = self.u([4200, 10800])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, t + self.u([20, 300]), amt, ptype, newp, True)
        elif kind == "hn_legit_remote":  # genuine IT support: unknown call + Play-store remote app, no payment
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="outgoing")
            t = self.u([60, 600])
            app = str(self.rng.choice(self.p["watchlisted_remote_apps"]))
            self.ev(sid, uid, t, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t + self.u([5, 60]), "APP_FOREGROUND", app_package=app)
            self.ev(sid, uid, t + self.u([300, 2400]), "CALL_END")
        elif kind == "hn_family_video":  # long video call with known contact + small known payment
            app = str(self.rng.choice(self.p["video_apps"]))
            self.ev(sid, uid, 0, "VIDEO_SESSION_START", caller_known=True, app_package=app)
            t = self.u([600, 3600])
            self.pay(sid, uid, t, min(amt, 2000), ptype, known, False)
            self.ev(sid, uid, t + self.u([600, 7200]), "VIDEO_SESSION_END", app_package=app)
        elif kind == "hn_new_merchant_during_call":  # delivery agent (unknown number) + pay a new merchant (COD)
            self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction="incoming")
            t = self.u([60, 600])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=newp, payee_is_new=True)
            self.pay(sid, uid, t + self.u([10, 120]), min(amt, 1500), "P2M", newp, True)
            self.ev(sid, uid, t + self.u([150, 900]), "CALL_END")
        else:
            raise ValueError(kind)

    # ---- scam sessions
    def scam_session(self, sid: str, uid: str, playbook: str):
        tm = self.p["timing_seconds"][playbook]
        sa = self.p["scam_amounts_inr"][playbook]
        payee = f"MULE-{sid}"
        direction = "outgoing" if (playbook == "remote_access" and self.rng.random() < 0.3) else "incoming"
        self.ev(sid, uid, 0, "CALL_START", caller_known=False, call_direction=direction)
        n_pay = int(self.rng.integers(tm["n_payments"][0], tm["n_payments"][1] + 1))
        amounts = self.rng.lognormal(math.log(sa["median"]), sa["sigma"], size=n_pay)

        if playbook == "remote_access":
            t = self.u(tm["call_to_install"])
            app = str(self.rng.choice(self.p["watchlisted_remote_apps"]))
            self.ev(sid, uid, t, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t + self.u([5, 60]), "APP_FOREGROUND", app_package=app)
            t += self.u(tm["install_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.u(tm["payee_to_payment"])
            for a in amounts:
                self.pay(sid, uid, t, min(a, self.am["cap"]), "P2P", payee, True)
                t += self.u([15, 180])
            self.ev(sid, uid, t + self.u([30, 600]), "CALL_END")

        elif playbook == "malicious_apk":
            t = self.u(tm["call_to_install"])
            app = f"apk.unknown.{int(self.rng.integers(1e6))}"
            self.ev(sid, uid, t, "APP_INSTALL", app_package=app, install_source="sideload")
            self.ev(sid, uid, t + self.u([60, 600]), "CALL_END")
            t += self.u(tm["install_to_payee"])
            self.ev(sid, uid, t, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            t += self.u(tm["payee_to_payment"])
            for a in amounts:  # fraudster-driven debits; victim not in a UPI app
                ch = "upi" if a <= self.am["cap"] else "bank_transfer"
                self.pay(sid, uid, t, a, "P2P", payee, True, channel=ch, initiator="remote")
                t += self.u([30, 900])

        elif playbook == "digital_arrest":
            t = self.u(tm["call_to_video"])
            app = str(self.rng.choice(self.p["video_apps"]))
            if self.rng.random() < 0.6:  # often told to install a video app during the call
                self.ev(sid, uid, t - 30, "APP_INSTALL", app_package=app, install_source="play_store")
            self.ev(sid, uid, t, "CALL_END")
            self.ev(sid, uid, t + 5, "VIDEO_SESSION_START", caller_known=False, app_package=app)
            video_end = t + self.u(tm["video_hours"]) * 3600
            tp = t + self.u(tm["video_to_payee_hours"]) * 3600
            tp = min(tp, video_end - 600)
            self.ev(sid, uid, tp, "NEW_PAYEE", payee_id=payee, payee_is_new=True)
            for a in amounts:
                tp += self.u([300, 6 * 3600])
                ch = "upi" if a <= self.am["cap"] else "bank_transfer"
                self.pay(sid, uid, tp, a, "P2P", payee, True, channel=ch)
            self.ev(sid, uid, max(video_end, tp + 60), "VIDEO_SESSION_END", app_package=app)

    # ---- orchestration
    def build(self, users: pd.DataFrame):
        p, c = self.p, self.p["cohorts"]
        uids = users["user_id"].to_numpy()
        n_legit, n_scam = p["n_legit_sessions"], p["n_scam_sessions"]
        n_hn = int(n_legit * p["hard_negative_fraction_of_legit"])
        hn_kinds = ["hn_out_of_order", "hn_long_gap", "hn_legit_remote", "hn_family_video", "hn_new_merchant_during_call"]
        legit_kinds = (["plain_payment"] * int((n_legit - n_hn) * 0.7)
                       + ["call_then_known_payment"] * ((n_legit - n_hn) - int((n_legit - n_hn) * 0.7))
                       + [hn_kinds[i % len(hn_kinds)] for i in range(n_hn)])
        mix = {k: v for k, v in p["playbook_mix"].items() if not k.startswith("_")}
        playbooks = self.rng.choice(list(mix), size=n_scam, p=np.array(list(mix.values())) / sum(mix.values()))

        jobs = [("legit", k) for k in legit_kinds] + [("scam", pb) for pb in playbooks]
        for i, (label, kind) in enumerate(jobs):
            sid = f"S{i:06d}"
            uid = str(self.rng.choice(uids))
            age_w = c["age_weights_scam"] if label == "scam" else c["age_weights_legit"]
            age = str(self.rng.choice(c["age_bands"], p=age_w))
            if label == "legit":
                self.legit_session(sid, uid, kind)
                umb = "none"
            else:
                self.scam_session(sid, uid, kind)
                umb = str(self.rng.choice(self.umbrella_by_playbook[kind]))
            self.sessions.append({
                "session_id": sid, "user_id": uid, "label": label,
                "session_kind": kind if label == "legit" else "scam",
                "playbook": kind if label == "scam" else "none",
                "scam_type_icfd": umb, "age_band": age,
                "start_hour": self.start_hour(),
                "source": ("generated" if self.kaggle is None
                           else "generated+kaggle_amounts" if self.kaggle_amounts else "generated+kaggle_hours_merchants"),
                "linkage": "synthetic",
            })

        sessions = pd.DataFrame(self.sessions).merge(users[["user_id", "activity_tier", "split"]], on="user_id")
        events = pd.DataFrame(self.events, columns=EVENT_COLUMNS).drop(columns="split")
        events = events.merge(sessions[["session_id", "split"]], on="session_id")
        events = events.sort_values(["session_id", "t_sec"], kind="stable")[EVENT_COLUMNS]
        return sessions, events


# --------------------------------------------------------------------------- validation report
def naive_rule(events: pd.DataFrame) -> pd.Series:
    """Unknown call + new payee + payment within 60 min of the call, before or after (order ignored).
    This is the co-occurrence baseline that order-aware scoring (OCSS) must beat; difficulty probe only."""
    def f(g):
        unk = g[(g.event_type.isin(["CALL_START", "VIDEO_SESSION_START"])) & (g.caller_known == False)]  # noqa: E712
        if unk.empty:
            return False
        t0 = unk.t_sec.min()
        w = g[(g.t_sec >= t0 - 3600) & (g.t_sec <= t0 + 3600)]
        return bool((w.event_type == "NEW_PAYEE").any() and (w.event_type == "PAYMENT_ATTEMPT").any())
    return events.groupby("session_id").apply(f, include_groups=False)


def report(out: Path, p, am, users, sessions, events, heldout_hash, kaggle, npci_note, kaggle_amounts) -> str:
    lines = ["# SatarkSim build report", "", f"Average-ticket source: {npci_note}", ""]
    legit_pay = events.merge(sessions[["session_id", "label", "session_kind"]], on="session_id")
    lp = legit_pay[(legit_pay.label == "legit") & (legit_pay.event_type == "PAYMENT_ATTEMPT")
                   & (legit_pay.session_kind.isin(["plain_payment", "call_then_known_payment"]))]
    p2m, p2p = lp[lp.payment_type == "P2M"].amount_inr, lp[lp.payment_type == "P2P"].amount_inr
    lines += ["## 1. Calibration against NPCI targets", "",
              "| Quantity | Target | SatarkSim |", "|---|---|---|",
              f"| P2M share of volume | {p['npci']['p2m_share_of_volume']:.2f} | {len(p2m) / max(len(lp), 1):.2f} |",
              f"| P2M payments < ₹500 | {p['npci']['p2m_share_below_500']:.2f} | {(p2m < 500).mean():.2f} |",
              f"| P2P payments < ₹500 | {p['npci']['p2p_share_below_500']:.2f} | {(p2p < 500).mean():.2f} |",
              f"| Average ticket (₹) | {am['target_mean']:.0f} | {lp.amount_inr.mean():.0f} (sample) |", "",
              "The fitted model's mean equals the target exactly; the sample mean of ~10k heavy-tailed P2P draws "
              "varies by several percent between seeds. Median and quantile shares are the stable checks.", ""]
    if kaggle is not None:
        kp = kaggle[kaggle.payment_type == "P2M"].amount
        kq = kaggle[kaggle.payment_type == "P2P"].amount
        lines += ["### Kaggle UPI 2024 vs NPCI (why Kaggle amounts are not used by default)", "",
                  "| Quantity | NPCI | Kaggle file |", "|---|---|---|",
                  f"| P2M share of volume | {p['npci']['p2m_share_of_volume']:.2f} | {(kaggle.payment_type == 'P2M').mean():.2f} |",
                  f"| P2M payments < ₹500 | {p['npci']['p2m_share_below_500']:.2f} | {(kp < 500).mean():.2f} |",
                  f"| P2P payments < ₹500 | {p['npci']['p2p_share_below_500']:.2f} | {(kq < 500).mean():.2f} |",
                  f"| Average ticket (₹) | {am['target_mean']:.0f} | {kaggle.amount.mean():.0f} |", "",
                  "Kaggle amounts follow one distribution for every transaction type and do not match NPCI, so amounts come from the "
                  "NPCI-calibrated model" + (" — **overridden: Kaggle amounts used (--kaggle-amounts)**." if kaggle_amounts else
                  ". Kaggle supplies hour-of-day and the P2M merchant-category mix."), ""]

    alpha = p.get("target_false_pause_alpha", 0.001)
    need = int(math.ceil(1 / alpha - 1))
    cal = sessions[(sessions.split == "calibration") & (sessions.label == "legit")].groupby("age_band").size()
    lines += ["## 1b. Can the false-pause target be certified per cohort?", "",
              f"Split-conformal needs at least 1/α − 1 = **{need}** legit calibration sessions per cohort for α = {alpha:.1%}.", "",
              "| Age band | Legit calibration sessions | Enough? |", "|---|---|---|"]
    lines += [f"| {g} | {n} | {'yes' if n >= need else '**no**'} |" for g, n in cal.items()] + [""]

    leak = users.groupby("user_id").split.nunique().max()
    lines += ["## 2. Split integrity", "",
              f"- Users appearing in more than one split: **{int(leak > 1)}** (must be 0)", ""]
    tab = sessions.groupby(["split", "label"]).size().unstack(fill_value=0)
    lines += ["| Split | Legit | Scam |", "|---|---|---|"]
    lines += [f"| {s} | {r.get('legit', 0)} | {r.get('scam', 0)} |" for s, r in tab.iterrows()] + [""]

    # Artefact probe: features that should carry no signal must not predict the label.
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    x = pd.get_dummies(sessions[["start_hour", "activity_tier"]].astype(str))
    y = (sessions.label == "scam").astype(int)
    tr, va = sessions.split == "train", sessions.split == "validation"
    auc = roc_auc_score(y[va], LogisticRegression(max_iter=1000).fit(x[tr], y[tr]).predict_proba(x[va])[:, 1])
    lines += ["## 3. Artefact probe", "",
              f"- AUC predicting scam from start hour + activity tier only: **{auc:.3f}** (should be ≈ 0.5; >0.6 means a generator artefact). "
              f"Both features are drawn independently of the label, so deviation from 0.5 here is sampling noise "
              f"({int(((sessions.split == 'validation') & (sessions.label == 'scam')).sum())} validation scams).",
              "- Age band is deliberately skewed for scams (assumption) and must not be used as a scoring feature.", ""]

    flags = naive_rule(events).rename("naive_flag").reset_index()
    s = sessions.merge(flags, on="session_id")
    v = s[s.split == "validation"]
    tpr = v[v.label == "scam"].naive_flag.mean()
    fpr = v[v.label == "legit"].naive_flag.mean()
    by_pb = v[v.label == "scam"].groupby("playbook").naive_flag.mean()
    by_hn = v[v.label == "legit"].groupby("session_kind").naive_flag.mean()
    lines += ["## 4. Difficulty probe (naive rule, validation split)", "",
              "Rule: unknown call + new payee + payment within 60 minutes of the call, before or after (order ignored). "
              "This is the co-occurrence baseline that order-aware scoring must beat.", "",
              f"- Recall: **{tpr:.2f}** · False-flag rate on legit sessions: **{fpr:.3f}**",
              "- Recall by playbook: " + ", ".join(f"{k} {val:.2f}" for k, val in by_pb.items()),
              "- False flags by legit kind: " + ", ".join(f"{k} {val:.2f}" for k, val in by_hn.items()), "",
              "If the naive rule were perfect, the data would be too easy to prove anything. "
              "It should miss digital-arrest sessions (multi-hour) and false-flag some hard negatives.", ""]

    lines += ["## 5. Held-out set", "",
              f"- Copied untouched to `heldout/`. SHA-256: `{heldout_hash}`",
              "- Not used anywhere in this build. Re-check the hash before the final run.", ""]
    lines += ["## 6. Provenance", "",
              "- Every row is `linkage=synthetic`. Results on SatarkSim show the logic works on simulated data, not real-world accuracy.",
              "- ICFD-31k contributes umbrella names only (licence: defensive research; no scam-script generation; commercial use needs permission).",
              "- Kaggle UPI file: " + ("used for hour-of-day and merchant mix" + (" and amounts" if kaggle_amounts else "")
               + ". Its `fraud_flag` is ignored: a gradient-boosted model on every column predicts it at AUC ≈ 0.48 (no signal)."
               if kaggle is not None else "**not supplied** — rerun with `--kaggle-upi`."), ""]
    text = "\n".join(lines)
    (out / "validation_report.md").write_text(text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--params", type=Path, default=Path(__file__).with_name("params.json"))
    ap.add_argument("--heldout", type=Path, required=True)
    ap.add_argument("--kaggle-upi", type=Path, default=None)
    ap.add_argument("--kaggle-amounts", action="store_true", help="resample legit amounts from Kaggle (off: NPCI model)")
    ap.add_argument("--npci-xlsx", type=Path, default=None, help="official NPCI product-statistics workbook")
    ap.add_argument("--out", type=Path, default=Path("data"))
    a = ap.parse_args()

    p = json.loads(a.params.read_text())
    npci_note = "secondary reports in params.json"
    target = None
    if a.npci_xlsx:
        target, span = npci_avg_ticket(a.npci_xlsx)
        npci_note = f"official NPCI workbook ({span}): ₹{target:,.0f}"
    am = fit_amount_model(p, target)
    kaggle = load_kaggle(a.kaggle_upi)
    b = Builder(p, am, kaggle, a.kaggle_amounts)
    users = b.make_users()
    sessions, events = b.build(users)

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "heldout").mkdir(exist_ok=True)
    users.to_csv(a.out / "satarksim_users.csv", index=False)
    sessions.to_csv(a.out / "satarksim_sessions.csv", index=False)
    events.to_csv(a.out / "satarksim_events.csv", index=False)
    shutil.copyfile(a.heldout, a.out / "heldout" / "heldout_events.csv")
    h = hashlib.sha256((a.out / "heldout" / "heldout_events.csv").read_bytes()).hexdigest()
    (a.out / "heldout" / "SHA256").write_text(h + "\n")
    (a.out / "amount_model.json").write_text(json.dumps(am, indent=2))
    print(report(a.out, p, am, users, sessions, events, h, kaggle, npci_note, a.kaggle_amounts))


if __name__ == "__main__":
    main()
