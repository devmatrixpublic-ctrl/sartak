#!/usr/bin/env python3
"""Export the trained reference detector to detector/src/main/resources/model.json (plan 2.2).

Trains exactly as satark_detector.py does (train split, label_observed; conformal thresholds per age cohort on the
legit calibration split), writes the model, then RELOADS model.json and re-scores the validation payments from the
JSON alone to prove the export is lossless (<= 1e-9). Also writes golden files for the Kotlin parity tests:

  detector/src/test/resources/golden/golden_events.csv     raw events (duplicates kept: the detector must dedupe)
  detector/src/test/resources/golden/golden_users.csv      per-user baseline + age band
  detector/src/test/resources/golden/golden_payments.csv   reference features + score at every payment
  detector/src/test/resources/golden/golden_sessions.csv   reference session decision (alarm, mechanism, alarm_t)

Usage (from repo root):  python detector/tools/export_model.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
import satark_detector as sd  # noqa: E402

N_GOLDEN_VALIDATION = 700
GOLDEN_SEED = 7
DEDUPE_WINDOW_S = 3
BASELINE_WINDOW_N = 50  # design choice, see Baseline.kt: last-N payments for the on-device baseline
BASELINE_BLEND_K = 20   # design choice: weight of own history = n / (n + K), K ~ "under ~20 observed payments" (exec summary v3)


def load(data: Path):
    users = pd.read_csv(data / "satarksim_users.csv")
    sessions = pd.read_csv(data / "satarksim_sessions.csv")
    events = pd.read_csv(data / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    return users, sessions, events


def build_model(users, sessions, pay, alerts, first_pay, alpha, params):
    by = sessions.groupby("split").session_id.apply(set)
    det = sd.Detector().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], alpha)

    # Pooled fallback threshold for an unknown/missing age band (conservative: calibrated on all cohorts together).
    s = pay.assign(score=det.score(pay)).groupby("session_id").score.max()
    cal = sessions[sessions.session_id.isin(by["calibration"]) & (sessions.label == "legit")]
    cal = cal.assign(score=cal.session_id.map(s).fillna(-np.inf))
    pooled = sd.conformal_threshold(cal.score.to_numpy(), alpha)
    cohorts = {}
    for b, g in cal.groupby("age_band"):
        n = len(g)
        k = int(np.ceil((n + 1) * (1 - alpha)))
        cohorts[b] = {"threshold": det.thr[b], "n_cal": n, "k": k, "method": "split_conformal" if k <= n else "pooled_fallback"}
        if k > n:  # cannot certify alpha with so few points: use pooled
            cohorts[b]["threshold"] = pooled

    tr_users = users[users.split == "train"]
    model = {
        "model_version": "satark-detector-1",
        "provenance": "Trained on SatarkSim v2 (simulated data) by detector/tools/export_model.py; not real-world accuracy.",
        "alpha": alpha,
        "features": sd.FEATURES,
        "scaler": {"mean": det.scaler.mean_.tolist(), "scale": det.scaler.scale_.tolist()},
        "logistic": {"coef": det.lr.coef_[0].tolist(), "intercept": float(det.lr.intercept_[0])},
        "cohort_thresholds": cohorts,
        "pooled_threshold": pooled,
        "constants": {
            "LONG_SESSION_H": sd.LONG_SESSION_H,
            "CONTACT_WINDOW_S": sd.CONTACT_WINDOW_S,
            "OCSS_WINDOW_S": sd.OCSS_WINDOW_S,
            "DEDUPE_WINDOW_S": DEDUPE_WINDOW_S,
            "AMOUNT_RATIO_CLIP": [-5.0, 8.0],
            "ROBUST_Z_MAD_SCALE": 1.4826,
            "ROBUST_Z_MAD_FLOOR": 1.0,
            "ROBUST_Z_CAP": 1e4,
            "REPEAT_CAP": 10,
        },
        "watchlist": params["watchlisted_remote_apps"],
        "baseline": {
            "window_n": BASELINE_WINDOW_N,
            "blend_k": BASELINE_BLEND_K,
            "prior_median_inr": float(tr_users.hist_median_inr.median()),
            "prior_mad_inr": float(tr_users.hist_mad_inr.median()),
            "note": "Prior = median of train-user history stats. window_n and blend_k are design choices, not fitted by the reference.",
        },
    }
    return det, model


def rescore_from_json(model: dict, pay: pd.DataFrame) -> np.ndarray:
    """Re-implements scoring from model.json only (what the Kotlin Scorer does)."""
    x = pay[model["features"]].to_numpy(dtype=np.float64)
    z = (x - np.array(model["scaler"]["mean"])) / np.array(model["scaler"]["scale"])
    s = np.zeros(len(x))
    for j, w in enumerate(model["logistic"]["coef"]):  # sequential, feature order: same as the Kotlin loop
        s += z[:, j] * w
    return s + model["logistic"]["intercept"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--params", type=Path, default=ROOT / "detector" / "reference" / "params.json")
    ap.add_argument("--alpha", type=float, default=0.001)
    ap.add_argument("--model-out", type=Path, default=ROOT / "detector" / "src" / "main" / "resources" / "model.json")
    ap.add_argument("--golden-out", type=Path, default=ROOT / "detector" / "src" / "test" / "resources" / "golden")
    a = ap.parse_args()

    params = json.loads(a.params.read_text())
    users, sessions, events = load(a.data)
    pay, alerts, first_pay = sd.featurize(events, users, params["watchlisted_remote_apps"])
    det, model = build_model(users, sessions, pay, alerts, first_pay, a.alpha, params)

    a.model_out.parent.mkdir(parents=True, exist_ok=True)
    a.model_out.write_text(json.dumps(model, indent=2) + "\n")  # json.dumps = shortest round-trip repr of float64

    # 1) lossless export: reload and re-score the validation payments from the JSON alone
    reloaded = json.loads(a.model_out.read_text())
    val_ids = set(sessions[sessions.split == "validation"].session_id)
    pv = pay[pay.session_id.isin(val_ids)]
    ref = det.score(pv)
    got = rescore_from_json(reloaded, pv)
    err = float(np.max(np.abs(ref - got)))
    print(f"export check: max |reference - model.json| over {len(pv):,} validation payments = {err:.3e}")
    assert err <= 1e-9, "model.json does not reproduce satark_detector.py scores"
    for b, c in model["cohort_thresholds"].items():
        assert reloaded["cohort_thresholds"][b]["threshold"] == det.thr[b] or c["method"] == "pooled_fallback"

    # 2) golden files for the Kotlin port
    res = sd.decide(det, pay, alerts, first_pay, sessions)
    allscores = pd.Series(det.score(pay), index=pay.index)
    pay_g = pay.assign(score=allscores)
    a.golden_out.mkdir(parents=True, exist_ok=True)
    v_ids = set(pd.read_csv(a.data / "detector_test_vectors_events.csv").session_id)
    val = sessions[sessions.split == "validation"]
    rng = np.random.default_rng(GOLDEN_SEED)
    pick = set()
    for _, g in val.groupby(["label", "playbook", "session_kind"]):
        take = min(len(g), 30 if g.label.iloc[0] == "scam" else 25)
        pick |= set(rng.choice(g.session_id.to_numpy(), take, replace=False))
    extra = [s for s in val.session_id if s not in pick]
    rng.shuffle(extra)
    pick |= set(extra[: max(0, N_GOLDEN_VALIDATION - len(pick))])
    ids = pick | v_ids

    ev = events[events.session_id.isin(ids)]
    ev.to_csv(a.golden_out / "golden_events.csv", index=False)
    users[users.user_id.isin(ev.user_id)][["user_id", "age_band", "hist_median_inr", "hist_mad_inr"]].to_csv(
        a.golden_out / "golden_users.csv", index=False)
    pay_g[pay_g.session_id.isin(ids)].to_csv(a.golden_out / "golden_payments.csv", index=False, float_format="%.17g")
    cols = ["session_id", "user_id", "age_band", "label", "session_kind", "playbook", "alarm", "mechanism", "interdicted",
            "alarm_t", "first_pay_t"]
    res[res.session_id.isin(ids)][cols].to_csv(a.golden_out / "golden_sessions.csv", index=False, float_format="%.17g")
    print(f"golden: {len(ids)} sessions ({len(v_ids)} test vectors) -> {a.golden_out}")

    # 3) the 36 vectors: add the baseline inputs + level, and check they equal the provided expected file
    vec_dir = a.data
    vec_ev = pd.read_csv(vec_dir / "detector_test_vectors_events.csv")
    vec_users = users[users.user_id.isin(vec_ev.user_id)][["user_id", "age_band", "hist_median_inr", "hist_mad_inr"]]
    vec_users.to_csv(vec_dir / "detector_test_vectors_users.csv", index=False)
    exp = pd.read_csv(vec_dir / "detector_test_vectors_expected.csv")
    mine = res[res.session_id.isin(exp.session_id)].set_index("session_id").loc[exp.session_id]
    same = (mine.alarm.to_numpy() == exp.alarm.to_numpy()).all() and (mine.mechanism.to_numpy() == exp.mechanism.to_numpy()).all()
    print(f"36 vectors: retrained reference reproduces the provided expected file: {same}")
    assert same, "retrained model disagrees with the shipped expected vectors"
    exp["level"] = np.where(exp.alarm, "HARD", "NONE")
    exp.to_csv(vec_dir / "detector_test_vectors_expected.csv", index=False)

    print(json.dumps({k: model[k] for k in ("alpha", "cohort_thresholds", "pooled_threshold")}, indent=2))


if __name__ == "__main__":
    main()
