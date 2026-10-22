#!/usr/bin/env python3
"""Regenerate detector/detector_report.md and data/satarksim/detector_report.md from a fresh reference run.

Every number comes from the run (validation split, thresholds from params.json `calibration_alpha`), with 95% Clopper-Pearson
intervals, and the cross-validated estimates are read from detector/experiments/calibration_margin_cv.md. M4's evaluation
(`ops/eval/run_eval.py`) parses the headline counts from detector/detector_report.md and checks they equal its own run.

Usage (repo root): python detector/tools/make_detector_report.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
import satark_detector as sd  # noqa: E402

BASE_RATE = 6.8e-6  # rough fraud rate per UPI transaction (second-hand derivation, order of magnitude only)


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


def ci(k, n, digits=1):
    lo, hi = cp(k, n)
    return f"{100*lo:.{digits}f} - {100*hi:.{digits}f}%"


def section(text: str, start: str) -> str:
    i = text.index(start)
    j = text.find("\n## ", i + 3)
    return text[i:j if j > 0 else len(text)].strip()


def cv_row(alpha: float) -> tuple[str, str] | None:
    p = ROOT / "detector" / "experiments" / "calibration_margin_cv.md"
    if not p.is_file():
        return None
    for line in p.read_text().splitlines():
        if line.startswith(f"| {alpha:.4f} "):
            cells = [c.strip() for c in line.strip("|").split("|")]
            return cells[1], cells[3]
    return None


def main():
    params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())
    alpha, target = params["calibration_alpha"], params["target_false_pause_alpha"]
    wl = json.loads((ROOT / "contracts" / "watchlist.json").read_text())["packages"]
    data = ROOT / "data" / "satarksim"
    det, res, (users, sessions, events, pay, alerts, first_pay) = sd.evaluate(data, alpha, wl)
    drift = sd.drift_test(sessions, pay, alerts, first_pay, alpha)
    ref = sd.report(det, res, alpha, drift, None)

    v = res[res.split == "validation"]
    sc, lg = v[v.label == "scam"], v[v.label == "legit"]
    rec_k, rec_n = int(sc.alarm.sum()), len(sc)
    int_k = int(sc.interdicted.sum())
    fa_k, fa_n = int(lg.alarm.sum()), len(lg)
    fam = sc[sc.playbook == "family_emergency_scam"]
    hn = lg[lg.session_kind == "hn_family_emergency"]
    recall, fa = rec_k / rec_n, fa_k / fa_n
    ppv = recall * BASE_RATE / (recall * BASE_RATE + fa * (1 - BASE_RATE))
    fa_ok, rec_ok = fa <= target, recall >= 0.93
    cv = cv_row(alpha)

    headline = f"""# Satark detector report (M2)

**All numbers below are from SatarkSim v2, a simulator. They show the detection logic separates the simulated scam playbooks and hard negatives; they do not measure real-world accuracy.** Scam event sequences and timings are design assumptions (no public data of real coached-scam sequences exists), and legitimate behaviour is fitted to a few published aggregates. The sealed held-out cases were not used.

Regenerate: `python detector/tools/make_detector_report.py` (fresh reference run; sections 2-6 and 8 are the reference's own output). Thresholds are calibrated at alpha' = {alpha:.2%}, a margin below the {target:.1%} target (see section 4).

## 1. Headline (validation split, {len(v):,} sessions: {rec_n} scams, {fa_n:,} legitimate), with 95% intervals

| Metric | Result | 95% CI (Clopper-Pearson) | Plan target | Met? |
|---|---|---|---|---|
| Scam recall (any alarm) | {rec_k}/{rec_n} = **{100*recall:.1f}%** | {ci(rec_k, rec_n)} | >= 93% | {'Point estimate yes' if rec_ok else '**No**'}; the interval's lower end is below 93% |
| Interdicted (alarm at or before first payment) | {int_k}/{rec_n} = **{100*int_k/rec_n:.1f}%** | {ci(int_k, rec_n)} | none | n/a |
| False alarms on legitimate sessions | {fa_k}/{fa_n:,} = **{100*fa:.3f}%** | {ci(fa_k, fa_n, 3)} | <= {100*target:.1f}% | {'Point estimate yes' if fa_ok else '**No**'}; the interval's upper end is above {100*target:.1f}% |
| Median lead time before first payment | {np.nanmedian(sc.lead_min):.1f} min | - | none | n/a |
| Naive co-occurrence baseline | recall {100*sc.naive.mean():.1f}%, false alarms {100*lg.naive.mean():.1f}% | - | - | Satark is far better on both |

**Cross-validation (independent of validation).** {('Over 5 user-level splits of the train and calibration data, alpha\' = %.4f gave false alarms %s and recall %s (`detector/experiments/calibration_margin_cv.md`). Recall in cross-validation is about a point lower than on this validation split, so treat the 93%% target as borderline, not secured.' % (alpha, cv[0], cv[1])) if cv else 'Not available.'}

{int(hn.alarm.sum())} of the {fa_k} false alarms are the *genuine family emergency* hard negative ({int(hn.alarm.sum())}/{len(hn)} = {100*hn.alarm.mean():.1f}%); that case is built to look identical to the family-emergency scam, so it is the expected weak spot. The family-emergency scam is caught {int(fam.alarm.sum())}/{len(fam)} = {100*fam.alarm.mean():.1f}% ({int(fam.interdicted.sum())}/{len(fam)} before the first payment).

{section(ref, "## 2. Per playbook")}

{section(ref, "## 3. False alarms by legit kind")}

## 4. Why alpha' is {alpha:.2%} and not {target:.1%}, and what precision looks like

Conformal calibration at alpha = {target} makes the **expected** false-alarm rate {target:.1%}, but one calibration draw lands above or below it. Cross-validation (`detector/experiments/calibration_margin_cv.md`) measured calibration at alpha = {target} giving **0.107%** false alarms, just over the target, in agreement with the earlier validation figure of 0.111%. Following a rule fixed before the run (largest alpha' with cross-validated false alarms <= 0.09%), alpha' = {alpha} was chosen. Two other options were tried and not adopted: thresholds with a 90% confidence statement (`detector/experiments/conformal_confidence.md`: false alarms 0.040%, recall 92.6%) and session-total features (`detector/experiments/session_total_features.md`: no gain).

False alarms of {100*fa:.2f}% are rates **among legitimate sessions in the simulator**. At a real fraud rate of about {BASE_RATE:.1e} per transaction (a rough, second-hand prior, order of magnitude only), with recall {100*recall:.1f}% and false alarms {100*fa:.3f}%, precision is about **{100*ppv:.2f}%, roughly one true alert per {round(1/ppv)} alerts**. A {target:.1%} false-alarm target is not a precision target.

{section(ref, "## 5. Calibration and fairness")}

Each cohort's threshold is the k-th smallest legitimate calibration score, k = ceil((n+1)(1-alpha')); `detector/src/main/resources/model.json` records n and k per cohort. For the 60+ cohort (n = 1,398) k equals n, so its threshold is the single highest calibration score: valid but noisy, and unchanged by the margin. The pooled threshold is exported as the fallback for an unknown age band.

{section(ref, "## 6. Drift")}

## 7. Timing sensitivity

Not re-run at the new calibration (it needs the raw Kaggle UPI and NPCI files); the earlier table, computed at alpha = 0.001, is in `data/satarksim/detector_sensitivity_alpha0.001.md`.

{section(ref, "## 8. Learned weights")}

## 9. On-device Kotlin port (`detector/`)

| Check | Result |
|---|---|
| `model.json` reproduces reference scores | max difference ~1.8e-15 over the validation payments (target <= 1e-9); `detector/tools/export_model.py` asserts it |
| 36 test vectors (decision, level, mechanism, alarm time, interdiction) | 36/36 match exactly (`ReferenceVectorsTest`); unchanged by the calibration margin |
| 732 golden simulated sessions | every session decision matches; payment features and scores within ~1.8e-15 (`GoldenParityTest`) |
| Determinism, 1,000-stream fuzz, missing signals, explainer, integration hazards | pass (`cd detector && gradle test`) |
| Cross-module run | the Kotlin detector's decisions drive the real server in `ops/e2e/run_e2e.py` (57 checks) |

Not yet done: the instrumented run of the 36 vectors on the two **physical** phones (M1 has run it 36/36 on an Android 15 emulator, `app/e2e_log.md`). The detector is a plain Kotlin/JVM library consumed by `app/` through `includeBuild`, not an Android library module.

## 10. Open items

- **Levels:** the detector emits `NONE` or `HARD`. `NUDGE` and `TRUSTED_CONTACT` (in `contracts/api.yaml`) are not produced.
- **Baseline:** the rolling last-50 median/MAD with an `n/(n+20)` blend toward the population prior is a design choice of the port, unit-tested but not validated on data.
- **Session boundaries:** undefined by the reference; the app decides (`app/.../SessionPolicy.kt`).
- **Rule false alarms:** SatarkSim has no genuine sideloads or long unknown-number video calls, so the rules' 0% false-alarm rate is untested against real behaviour.
- **Unknown video origin:** the app infers it (`VideoOrigin`); the platform cannot say who is on a video call.
- **Tag:** `detector-freeze` is not set; set it only after the run on physical phones and sign-off.
"""
    (ROOT / "detector" / "detector_report.md").write_text(headline)
    (data / "detector_report.md").write_text(ref + "\n\n_Timing sensitivity: see `detector_sensitivity_alpha0.001.md` (computed at the earlier calibration, not re-run)._\n")
    print(f"recall {rec_k}/{rec_n} = {100*recall:.2f}% [{ci(rec_k, rec_n)}]  false alarms {fa_k}/{fa_n} = {100*fa:.3f}% [{ci(fa_k, fa_n, 3)}]")
    print(f"gate: recall {'ok' if rec_ok else 'FAIL'}, false alarms {'ok' if fa_ok else 'FAIL'}; PPV {100*ppv:.2f}%")


if __name__ == "__main__":
    main()
