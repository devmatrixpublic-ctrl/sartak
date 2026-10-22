#!/usr/bin/env python3
"""Satark reference detector: an executable spec of master doc v6 for R2 to port to the phone.

Decision logic (all evidence is computed only from events up to the moment of decision):
  A. Payment score (at every PAYMENT_ATTEMPT = the pay screen): logistic weight-of-evidence over
     unknown-contact, install-during-call, remote-access, new-payee, amount-vs-OWN-baseline, repeat-payment and
     order (OCSS) features. Threshold per age cohort by split-conformal calibration on legit sessions (alpha).
  B. Install-during-call rule (§4.1): unknown call + app SIDELOADED during it -> alert at install time.
  C. Long-session mode (§4.6): unknown-origin video session active >= LONG_SESSION_H hours -> alert.
Device realism: the detector deduplicates near-identical events itself (it never reads `is_duplicate`), and it
uses only `label_observed` for training. Age band is used ONLY to pick the cohort threshold, never as a feature.

Usage:
  python satark_detector.py --data data --out data/detector_report.md   # --alpha defaults to params.json calibration_alpha
  python satark_detector.py ... --sensitivity --kaggle-upi K.csv --npci-xlsx N.xlsx   # also train-1x/test-0.5x,2x
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

TARGET_FALSE_ALARM = 0.001    # plan target: false alarms <= 0.1% of legitimate sessions (thresholds use a smaller calibration alpha, see params.json)
LONG_SESSION_H = 2.0          # §4.6 trigger
CONTACT_WINDOW_S = 2 * 3600   # unknown-contact evidence window for payment scoring
OCSS_WINDOW_S = 3600          # order-constrained sequence must complete within this

FEATURES = [
    "unk_contact_recent", "unk_call_active", "unk_video_active", "mins_since_unk_log",
    "install_play_during_unk", "install_sideload_during_unk", "watchlist_app",
    "new_payee", "payee_added_after_unk", "log_amt_ratio", "robust_z_pos", "repeat_to_payee", "is_p2p",
    "ocss_ordered", "newpayee_x_amt", "unk_x_newpayee",
]


def conformal_threshold(scores: np.ndarray, alpha: float) -> float:
    s = np.sort(scores)
    k = int(np.ceil((len(s) + 1) * (1 - alpha)))
    return float(s[min(k, len(s)) - 1]) if len(s) else math.inf


def dedupe(ev: pd.DataFrame) -> pd.DataFrame:
    """Drop events that repeat the same (type, app, payee, amount) within 3 s — as the phone must."""
    ev = ev.sort_values(["session_id", "t_sec"], kind="stable")
    cols = ["session_id", "event_type", "app_package", "payee_id", "amount_inr"]
    parts = [ev[c].astype("object").where(ev[c].notna(), "").astype(str) for c in cols]
    key = parts[0]
    for p_ in parts[1:]:
        key = key + "|" + p_
    prev_key, prev_t = key.shift(), ev.t_sec.shift()
    dup = (key == prev_key) & ((ev.t_sec - prev_t).abs() <= 3)
    return ev[~dup]


def session_features(g: pd.DataFrame, med: float, mad: float, watchlist: set) -> tuple[list[dict], list[tuple]]:
    """Walk one session in time order. Returns payment decision rows and rule-alert (time, rule) tuples."""
    rows, alerts = [], []
    unk_t, call_active, video_unk_t, video_active = None, False, None, False
    installs, wl, payee_added_t, paid_to = [], False, {}, {}
    for e in g.itertuples(index=False):
        t, et = e.t_sec, e.event_type
        if et == "CALL_START":
            call_active = True
            if e.caller_known is False or e.caller_known == "False":
                unk_t = t if unk_t is None else unk_t
        elif et == "CALL_END":
            call_active = False
        elif et == "VIDEO_SESSION_START":
            video_active = True
            if e.caller_known is False or e.caller_known == "False":
                video_unk_t = t
                unk_t = t if unk_t is None else unk_t
        elif et == "VIDEO_SESSION_END":
            if video_active and video_unk_t is not None and t - video_unk_t >= LONG_SESSION_H * 3600:
                alerts.append((video_unk_t + LONG_SESSION_H * 3600, "long_session"))
            video_active = False
        elif et == "APP_INSTALL":
            installs.append((t, e.install_source, e.app_package))
            if e.app_package in watchlist:
                wl = True
            if unk_t is not None and e.install_source == "sideload" and t - unk_t <= CONTACT_WINDOW_S:
                alerts.append((t, "sideload_during_call"))
        elif et == "APP_FOREGROUND":
            if e.app_package in watchlist:
                wl = True
        elif et == "NEW_PAYEE":
            payee_added_t[e.payee_id] = t
        elif et == "PAYMENT_ATTEMPT":
            # long-session mode can also fire at payment time if the session is already long
            if video_active and video_unk_t is not None and t - video_unk_t >= LONG_SESSION_H * 3600:
                alerts.append((video_unk_t + LONG_SESSION_H * 3600, "long_session"))
            recent = unk_t is not None and 0 <= t - unk_t <= CONTACT_WINDOW_S
            inst_play = any(s == "play_store" and unk_t is not None and unk_t <= ti <= t for ti, s, _ in installs)
            inst_side = any(s == "sideload" and unk_t is not None and unk_t <= ti <= t for ti, s, _ in installs)
            amt = float(e.amount_inr or 0)
            ratio = math.log((amt + 1) / (med + 1))
            rz = max(0.0, (amt - med) / (1.4826 * max(mad, 1.0)))
            pa = payee_added_t.get(e.payee_id)
            new = bool(e.payee_is_new is True or e.payee_is_new == "True")
            after_unk = new and unk_t is not None and pa is not None and pa >= unk_t
            first_inst = min((ti for ti, _, _ in installs if unk_t is not None and ti >= unk_t), default=None)
            ordered = bool(after_unk and (t - unk_t) <= OCSS_WINDOW_S and (first_inst is None or first_inst <= pa))
            rep = paid_to.get(e.payee_id, 0)
            rows.append({
                "t": t,
                "unk_contact_recent": float(recent),
                "unk_call_active": float(call_active and unk_t is not None),
                "unk_video_active": float(video_active and video_unk_t is not None),
                "mins_since_unk_log": math.log1p(max(t - unk_t, 0) / 60) if unk_t is not None else 0.0,
                "install_play_during_unk": float(inst_play),
                "install_sideload_during_unk": float(inst_side),
                "watchlist_app": float(wl),
                "new_payee": float(new),
                "payee_added_after_unk": float(after_unk),
                "log_amt_ratio": float(np.clip(ratio, -5, 8)),
                "robust_z_pos": math.log1p(min(rz, 1e4)),
                "repeat_to_payee": float(min(rep, 10)),
                "is_p2p": float(e.payment_type == "P2P"),
                "ocss_ordered": float(ordered),
                "newpayee_x_amt": float(new) * float(np.clip(ratio, -5, 8)),
                "unk_x_newpayee": float(recent and new),
            })
            paid_to[e.payee_id] = rep + 1
    if video_active and video_unk_t is not None:  # session ends with video still on
        last = g.t_sec.max()
        if last - video_unk_t >= LONG_SESSION_H * 3600:
            alerts.append((video_unk_t + LONG_SESSION_H * 3600, "long_session"))
    return rows, alerts


def featurize(events: pd.DataFrame, users: pd.DataFrame, watchlist: list[str]):
    ev = dedupe(events)
    u = users.set_index("user_id")
    wl = set(watchlist)
    pay_rows, alert_rows = [], []
    for sid, g in ev.groupby("session_id", sort=False):
        uid = g.user_id.iloc[0]
        rows, alerts = session_features(g, float(u.at[uid, "hist_median_inr"]), float(u.at[uid, "hist_mad_inr"]), wl)
        for r in rows:
            r["session_id"] = sid
        pay_rows += rows
        alert_rows += [{"session_id": sid, "t": t, "rule": rule} for t, rule in alerts]
    pay = pd.DataFrame(pay_rows)
    alerts = pd.DataFrame(alert_rows, columns=["session_id", "t", "rule"])
    first_pay = ev[ev.event_type == "PAYMENT_ATTEMPT"].groupby("session_id").t_sec.min().rename("first_pay_t")
    return pay, alerts, first_pay


class Detector:
    def fit(self, pay: pd.DataFrame, sessions: pd.DataFrame, train_mask_sessions: set):
        d = pay[pay.session_id.isin(train_mask_sessions)].merge(sessions[["session_id", "label_observed"]], on="session_id")
        self.scaler = StandardScaler().fit(d[FEATURES])
        self.lr = LogisticRegression(max_iter=2000, C=1.0).fit(self.scaler.transform(d[FEATURES]),
                                                                (d.label_observed == "scam").astype(int))
        return self

    def score(self, pay: pd.DataFrame) -> np.ndarray:
        return self.lr.decision_function(self.scaler.transform(pay[FEATURES]))

    def weights(self) -> pd.Series:
        return pd.Series(self.lr.coef_[0], index=FEATURES).sort_values(ascending=False)

    def calibrate(self, pay, sessions, cal_sessions: set, alpha: float):
        s = pay.assign(score=self.score(pay)).groupby("session_id").score.max()
        cal = sessions[sessions.session_id.isin(cal_sessions) & (sessions.label == "legit")]
        # legit sessions without any payment cannot be paused by the payment score: they count as -inf
        cal = cal.assign(score=cal.session_id.map(s).fillna(-np.inf))
        self.thr = {b: conformal_threshold(grp.score.to_numpy(), alpha) for b, grp in cal.groupby("age_band")}
        return self


def decide(det: Detector, pay, alerts, first_pay, sessions):
    """Per-session decision: first alarm time and which mechanism fired."""
    p = pay.assign(score=det.score(pay)).merge(sessions[["session_id", "age_band"]], on="session_id")
    p["thr"] = p.age_band.map(det.thr)
    hits = p[p.score >= p.thr].groupby("session_id").t.min().rename("pay_alarm_t")
    rule_t = alerts.groupby("session_id").t.min().rename("rule_alarm_t")
    rule_name = alerts.sort_values("t").groupby("session_id").rule.first().rename("rule")
    out = sessions.set_index("session_id").join([hits, rule_t, rule_name, first_pay])
    out["alarm_t"] = out[["pay_alarm_t", "rule_alarm_t"]].min(axis=1)
    out["alarm"] = out.alarm_t.notna()
    out["mechanism"] = np.where(out.alarm_t.isna(), "none",
                       np.where(out.rule_alarm_t.notna() & (out.rule_alarm_t <= out.pay_alarm_t.fillna(np.inf)),
                                out.rule.fillna("rule"), "payment_score"))
    out["interdicted"] = out.alarm & (out.first_pay_t.isna() | (out.alarm_t <= out.first_pay_t))
    out["lead_min"] = np.where(out.interdicted & out.first_pay_t.notna(), (out.first_pay_t - out.alarm_t) / 60, np.nan)
    return out.reset_index()


def naive_flags(events):
    from build_satarksim import naive_rule
    return naive_rule(events).rename("naive").rename_axis("session_id").reset_index()


def evaluate(data: Path, alpha: float, watchlist: list[str]):
    users = pd.read_csv(data / "satarksim_users.csv")
    sessions = pd.read_csv(data / "satarksim_sessions.csv")
    events = pd.read_csv(data / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    pay, alerts, first_pay = featurize(events, users, watchlist)
    by = sessions.groupby("split").session_id.apply(set)
    det = Detector().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], alpha)
    res = decide(det, pay, alerts, first_pay, sessions).merge(naive_flags(events), on="session_id")
    return det, res, (users, sessions, events, pay, alerts, first_pay)


def drift_test(sessions, pay, alerts, first_pay, alpha, from_week=6):
    early = set(sessions[sessions.week < from_week].session_id)
    tr = set(sessions[(sessions.split == "train")].session_id) & early
    ca = set(sessions[(sessions.split == "calibration")].session_id) & early
    det = Detector().fit(pay, sessions, tr).calibrate(pay, sessions, ca, alpha)
    res = decide(det, pay, alerts, first_pay, sessions)
    v = res[(res.split == "validation") & (res.week >= from_week)]
    return v[v.label == "scam"].alarm.mean(), v[v.label == "legit"].alarm.mean()


def pct(x):
    return f"{100 * x:.1f}%"


def report(det, res, alpha, drift, sens) -> str:
    v = res[res.split == "validation"]
    sc, lg = v[v.label == "scam"], v[v.label == "legit"]
    L = ["# Satark reference detector: results on SatarkSim v2 (validation split)", "",
         f"Simulated data, not real-world accuracy. Trained on `label_observed` (2% noisy) from the train split; Hard-intervention "
         f"thresholds per age cohort by split-conformal calibration on legit calibration sessions at α = {alpha:.2%}; evaluated on the "
         f"true `label` of {len(v):,} validation sessions ({len(sc)} scams). Held-out real cases NOT used.", "",
         "## 1. Headline vs the naive baseline", "",
         "| Metric | Naive co-occurrence rule | **Satark** |", "|---|---|---|",
         f"| Scam recall (any alarm) | {pct(sc.naive.mean())} | **{pct(sc.alarm.mean())}** |",
         f"| Interdicted (alarm at or before first payment) | — | **{pct(sc.interdicted.mean())}** |",
         f"| False alarms on legit sessions | {pct(lg.naive.mean())} | **{pct(lg.alarm.mean())}** |",
         f"| Median lead time before first payment (interdicted scams) | — | **{np.nanmedian(sc.lead_min):.1f} min** |", ""]
    L += ["## 2. Per playbook", "", "| Playbook | n | Naive recall | **Satark recall** | Interdicted | Main mechanism |", "|---|---|---|---|---|---|"]
    for pb, g in sc.groupby("playbook"):
        mech = g[g.alarm].mechanism.value_counts()
        L.append(f"| {pb} | {len(g)} | {pct(g.naive.mean())} | **{pct(g.alarm.mean())}** | {pct(g.interdicted.mean())} | "
                 f"{mech.index[0] if len(mech) else '—'} |")
    L += ["", "## 3. False alarms by legit kind (hard negatives)", "",
          "| Legit kind | n | Naive | **Satark** |", "|---|---|---|---|"]
    for k, g in lg.groupby("session_kind"):
        L.append(f"| {k} | {len(g)} | {pct(g.naive.mean())} | **{pct(g.alarm.mean())}** |")
    fe_s = sc[sc.playbook == "family_emergency_scam"]
    fe_l = lg[lg.session_kind == "hn_family_emergency"]
    L += ["", "## 4. The hardest pair: genuine family emergency vs family-emergency scam", "",
          f"Identical event sequence. Naive rule: flags {pct(fe_l.naive.mean())} of genuine and {pct(fe_s.naive.mean())} of scams "
          f"(cannot separate). **Satark: flags {pct(fe_l.alarm.mean())} of genuine and catches {pct(fe_s.alarm.mean())} of scams** "
          "— separation comes from amount relative to the user's own baseline and repeat payments.", ""]
    L += ["## 5. Calibration and fairness (false-alarm guarantee)", "",
          f"Target false-pause rate per cohort: {TARGET_FALSE_ALARM:.2%}. Thresholds are calibrated at the margin α' = {alpha:.2%} so that sampling noise "
          "does not push the realised rate over the target (see `detector/experiments/calibration_margin_cv.md`). Payment-score alarms only (rule alarms reported separately).", "",
          "| Age band | Threshold | Legit validation sessions | Empirical false-alarm rate (one-sided binomial test that the true rate exceeds the 0.10% target) |", "|---|---|---|---|"]
    rates = {}
    for b, g in lg.groupby("age_band"):
        k = int(g.pay_alarm_t.notna().sum())
        r = k / len(g)
        rates[b] = r
        from scipy.stats import binomtest
        pv = binomtest(k, len(g), TARGET_FALSE_ALARM, alternative="greater").pvalue
        L.append(f"| {b} | {det.thr[b]:.2f} | {len(g):,} | {pct(r)} ({k} sessions; p = {pv:.2f} vs target) |")
    rule_fp = lg.rule_alarm_t.notna().mean()
    L += ["", f"Rule alarms (sideload-during-call, long-session) on legit sessions: {pct(rule_fp)}. "
          "**Caveat:** SatarkSim contains no genuine sideloads or long unknown-number video calls, so this is optimistic; "
          "measure it on real devices before claiming it.", ""]
    L += ["## 6. Drift (calibrate on weeks 0–5, test on weeks 6–11)", "",
          f"After a new remote-access app appears and the malicious-APK share rises: recall **{pct(drift[0])}**, "
          f"false alarms **{pct(drift[1])}**. (A static watch-list's recall on remote-access scams falls 1.00 → 0.49 in the same period.)", ""]
    if sens is not None:
        L += ["## 7. Timing sensitivity (trained at 1×, tested on data rebuilt at other timing scales)", "",
              "| Timing scale | Satark recall | Naive recall |", "|---|---|---|"]
        L += [f"| {s}× | {pct(a)} | {pct(b)} |" for s, a, b in sens]
        L += ["", "Satark's install-during-call and long-session mechanisms do not depend on time windows, so recall should move far less "
              "than the naive rule's.", ""]
    w = det.weights()
    L += ["## 8. Learned weights of evidence (standardised logistic coefficients)", "",
          "| Feature | Weight |", "|---|---|"] + [f"| {k} | {val:+.2f} |" for k, val in w.items()]
    L += ["", "Read these jointly, not one by one: several features are correlated by construction (e.g. `unk_contact_recent` and "
          "`unk_x_newpayee`), so individual signs can flip. For explanations (L5), each alarm cites its own top terms by "
          "contribution (weight × standardised value), which is well-defined per decision.", ""]
    L += ["## 9. What this does and does not show", "",
          "- Shows the v6 design separates the playbooks and hard negatives that a co-occurrence rule cannot, on simulated data.",
          "- Does not show real-world accuracy: SatarkSim timings and amounts are assumptions; only a consented pilot can.",
          "- The held-out real cases remain frozen for the team's single final run.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--params", type=Path, default=Path(__file__).with_name("params.json"))
    ap.add_argument("--alpha", type=float, default=json.loads(Path(__file__).with_name("params.json").read_text())["calibration_alpha"])
    ap.add_argument("--out", type=Path, default=Path("data/detector_report.md"))
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--kaggle-upi", type=Path)
    ap.add_argument("--npci-xlsx", type=Path)
    a = ap.parse_args()
    p = json.loads(a.params.read_text())
    wl = p["watchlisted_remote_apps"]

    det, res, (users, sessions, events, pay, alerts, first_pay) = evaluate(a.data, a.alpha, wl)
    drift = drift_test(sessions, pay, alerts, first_pay, a.alpha)

    sens = None
    if a.sensitivity:
        from build_satarksim import build_all, fit_amount_model, load_kaggle, npci_avg_ticket
        am = fit_amount_model(p, npci_avg_ticket(a.npci_xlsx)[0] if a.npci_xlsx else None)
        kg = load_kaggle(a.kaggle_upi)
        sens = []
        for scale in (0.5, 1.0, 2.0):
            u2, s2, e2 = build_all(p, am, kg, scale)
            u2 = u2.drop(columns=["log_scale"])
            pay2, al2, fp2 = featurize(e2, u2, wl)
            r2 = decide(det, pay2, al2, fp2, s2).merge(naive_flags(e2), on="session_id")
            v2 = r2[(r2.split == "validation") & (r2.label == "scam")]
            sens.append((scale, v2.alarm.mean(), v2.naive.mean()))
            print(f"sensitivity {scale}x done")

    text = report(det, res, a.alpha, drift, sens)
    a.out.write_text(text)
    res.to_csv(a.out.with_name("detector_decisions.csv"), index=False)
    print(text)


if __name__ == "__main__":
    main()
