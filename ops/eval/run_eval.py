"""Evaluation pipeline (plan 4.3).

Runs M2's reference detector on SatarkSim, recomputes the headline numbers with 95% intervals,
checks they match the counts in M2's committed detector/detector_report.md, records SHA-256 hashes of every input, and
FAILS (exit 1) if scam recall < 93% or the false-alarm rate on legitimate sessions > 0.1%.

The gate is the plan's, applied to the point estimates exactly as written. It is deliberately not
tuned: if the detector misses the target the pipeline says so (M2's own report notes the false-alarm
estimate is slightly above 0.1% with an interval that contains both sides).

Not run here, by design (plan 4.3): BAF and IEEE-CIS need raw Kaggle files that are too large and
licence-restricted for CI. Their reports are committed under data/satarksim/; record the hashes of the
raw files you ran them on with ops/eval/record_local_hashes.py.

Usage (repo root):  python ops/eval/run_eval.py [--data data/satarksim] [--alpha 0.0008]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
SHIPPED_REPORT = ROOT / "detector" / "detector_report.md"   # has counts; data/satarksim/ copy is rounded
RECALL_MIN = 0.93
FAIRNESS_RATIO_MAX = 1.5   # max/min of a rate across the cohorts of one dimension; applied to point estimates as written
FALSE_ALARM_MAX = 0.001


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    from scipy.stats import beta

    a = (1 - conf) / 2
    lo = 0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))
    return lo, hi


def headline(res) -> dict:
    v = res[res.split == "validation"]
    scam, legit = v[v.label == "scam"], v[v.label == "legit"]
    s_n, s_k = len(scam), int(scam.alarm.sum())
    l_n, l_k = len(legit), int(legit.alarm.sum())
    i_k = int(scam.interdicted.sum())
    return {
        "scam_sessions": s_n, "scam_alarmed": s_k, "recall": s_k / s_n,
        "recall_ci95": clopper_pearson(s_k, s_n),
        "interdicted": i_k, "interdicted_rate": i_k / s_n,
        "legit_sessions": l_n, "legit_false_alarms": l_k, "false_alarm_rate": l_k / l_n,
        "false_alarm_ci95": clopper_pearson(l_k, l_n),
        "median_lead_min": float(scam.lead_min.median()),
        "naive_recall": float(scam.naive.mean()), "naive_false_alarm": float(legit.naive.mean()),
    }


def parse_shipped_report(path: Path) -> dict:
    """Pull the headline counts out of M2's committed detector_report.md."""
    text = path.read_text(encoding="utf-8")
    rec = re.search(r"Scam recall \(any alarm\) \| (\d+)/(\d+)", text)
    fa = re.search(r"False alarms on legitimate sessions \| ([\d,]+)/([\d,]+)", text)
    if not rec or not fa:
        raise ValueError(f"cannot find the headline table in {path}")
    num = lambda s: int(s.replace(",", ""))
    return {"scam_alarmed": num(rec.group(1)), "scam_sessions": num(rec.group(2)),
            "legit_false_alarms": num(fa.group(1)), "legit_sessions": num(fa.group(2))}


# Cohort dimensions that exist as columns in SatarkSim. No device-tier column exists, so call-state availability (a
# device-capability flag) stands in for it. Language is skipped: SatarkSim has no language field.
COHORT_DIMENSIONS = {
    "age band": "age_band",
    "activity tier": "activity_tier",
    "call-state availability": "call_state_available",
}


def ratio(values: list[float]) -> float:
    """max/min. All zero means the cohorts are equal (1.0); a zero minimum under a non-zero maximum is infinite."""
    mx, mn = max(values), min(values)
    if mx == 0:
        return 1.0
    return float("inf") if mn == 0 else mx / mn


def fairness(res) -> dict:
    """Recall and false-alarm rate on the validation split for every cohort, and the max/min ratio per dimension."""
    v = res[res.split == "validation"]
    out = {}
    for name, col in COHORT_DIMENSIONS.items():
        if col not in v.columns:
            continue
        rows = []
        for g, d in v.groupby(col):
            scam, legit = d[d.label == "scam"], d[d.label == "legit"]
            s_n, s_k, l_n, l_k = len(scam), int(scam.alarm.sum()), len(legit), int(legit.alarm.sum())
            rows.append({"cohort": str(g), "scam_n": s_n, "scam_alarmed": s_k, "recall": s_k / s_n if s_n else float("nan"),
                         "recall_ci95": clopper_pearson(s_k, s_n) if s_n else (0.0, 1.0),
                         "legit_n": l_n, "false_alarms": l_k, "false_alarm_rate": l_k / l_n if l_n else float("nan"),
                         "false_alarm_ci95": clopper_pearson(l_k, l_n) if l_n else (0.0, 1.0)})
        out[name] = {"rows": rows, "recall_ratio": ratio([r["recall"] for r in rows]),
                     "false_alarm_ratio": ratio([r["false_alarm_rate"] for r in rows])}
    return out


def fairness_gate(f: dict, limit: float = FAIRNESS_RATIO_MAX) -> list[str]:
    fails = []
    for name, d in f.items():
        for key, label in (("recall_ratio", "recall"), ("false_alarm_ratio", "false-alarm rate")):
            if d[key] > limit:
                shown = "undefined (a cohort has none)" if d[key] == float("inf") else f"{d[key]:.2f}"
                fails.append(f"fairness: {label} max/min across {name} is {shown} (limit {limit})")
    return fails


def render_fairness(f: dict, failures: list[str]) -> str:
    L = ["# Fairness report (simulated data)", "",
         "Validation split of SatarkSim, per cohort. **All numbers are from a simulator, not real users.** Language is skipped "
         "(SatarkSim has no language field) and there is no device-tier column, so call-state availability, a device-capability "
         "flag, is shown instead. The gate is the ratio max/min of a rate across the cohorts of one dimension, on point "
         f"estimates, and fails above {FAIRNESS_RATIO_MAX}. A cohort with zero false alarms makes the false-alarm ratio "
         "undefined (infinite), which fails the gate as written. Per-cohort false-alarm counts are 0 to 5, so these ratios are noisy.", "",
         f"**Gate: {'PASS' if not failures else 'FAIL'}**", ""]
    for name, d in f.items():
        L += [f"## {name}", "", "| cohort | scam sessions | recall (95% CI) | legit sessions | false alarms | false-alarm rate (95% CI) |", "|---|---|---|---|---|---|"]
        for r in d["rows"]:
            L.append(f"| {r['cohort']} | {r['scam_n']} | {r['recall']:.1%} ({r['recall_ci95'][0]:.1%}-{r['recall_ci95'][1]:.1%}) | {r['legit_n']} | "
                     f"{r['false_alarms']} | {r['false_alarm_rate']:.3%} ({r['false_alarm_ci95'][0]:.3%}-{r['false_alarm_ci95'][1]:.3%}) |")
        far = d["false_alarm_ratio"]
        L += ["", f"Recall max/min: **{d['recall_ratio']:.2f}**. False-alarm max/min: **{'undefined (a cohort has zero)' if far == float('inf') else f'{far:.2f}'}**.", ""]
    if failures:
        L += ["## Gate failures", ""] + [f"- {x}" for x in failures] + [""]
    return "\n".join(L) + "\n"


def gate(h: dict, recall_min: float = RECALL_MIN, fa_max: float = FALSE_ALARM_MAX) -> list[str]:
    failures = []
    if h["recall"] < recall_min:
        failures.append(f"scam recall {h['recall']:.2%} is below the {recall_min:.0%} target")
    if h["false_alarm_rate"] > fa_max:
        failures.append(f"false-alarm rate {h['false_alarm_rate']:.3%} is above the {fa_max:.1%} target")
    return failures


def input_hashes(data: Path) -> dict[str, str]:
    files = sorted(data.glob("*.csv")) + [data / "params.json", REF / "params.json",
                                          REF / "satark_detector.py"]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256_file(p) for p in files if p.is_file()}


def render_report(h: dict, failures: list[str], matches: bool, shipped: dict, hashes: dict, alpha: float) -> str:
    lo, hi = h["recall_ci95"]
    flo, fhi = h["false_alarm_ci95"]
    status = "PASS" if not failures else "FAIL"
    lines = [
        "# M4 evaluation run (SatarkSim v2, validation split)", "",
        "Simulated data: this shows the logic separates the simulated playbooks, not real-world accuracy.", "",
        f"**Gate: {status}** (recall >= {RECALL_MIN:.0%} and false alarms <= {FALSE_ALARM_MAX:.1%}, point estimates; thresholds calibrated at alpha = {alpha:.2%})", "",
    ]
    lines += [f"- FAIL: {f}" for f in failures] or ["- both targets met"]
    lines += ["", "| Metric | Result | 95% CI |", "|---|---|---|",
              f"| Scam recall | {h['scam_alarmed']}/{h['scam_sessions']} = {h['recall']:.1%} | {lo:.1%} - {hi:.1%} |",
              f"| Interdicted before first payment | {h['interdicted']}/{h['scam_sessions']} = {h['interdicted_rate']:.1%} | |",
              f"| False alarms (legit) | {h['legit_false_alarms']}/{h['legit_sessions']} = {h['false_alarm_rate']:.3%} | {flo:.3%} - {fhi:.3%} |",
              f"| Median lead time | {h['median_lead_min']:.1f} min | |",
              f"| Naive baseline | recall {h['naive_recall']:.1%}, false alarms {h['naive_false_alarm']:.1%} | |", "",
              f"Matches committed `detector/detector_report.md`: **{'yes' if matches else 'NO'}** "
              f"(shipped: {shipped['scam_alarmed']}/{shipped['scam_sessions']} scams, "
              f"{shipped['legit_false_alarms']}/{shipped['legit_sessions']} false alarms).", "",
              "## Input hashes (SHA-256)", ""]
    lines += [f"- `{k}`: `{v}`" for k, v in hashes.items()]
    lines += ["", "BAF and IEEE-CIS are run locally only; see `ops/eval/input_hashes.json` for their recorded hashes.", ""]
    return "\n".join(lines)


def run(data: Path, alpha: float, out_dir: Path, shipped_report: Path = SHIPPED_REPORT) -> tuple[dict, list[str], bool]:
    sys.path.insert(0, str(REF))
    import satark_detector as sd

    wl = json.loads((REF / "params.json").read_text())["watchlisted_remote_apps"]
    t0 = time.time()
    _, res, _ = sd.evaluate(data, alpha, wl)
    h = headline(res)
    fair = fairness(res)
    shipped = parse_shipped_report(shipped_report)
    matches = all(h[k] == shipped[k] for k in shipped)
    failures = gate(h) + fairness_gate(fair)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / "fairness_report.md").write_text(render_fairness(fair, fairness_gate(fair)), encoding="utf-8", newline="\n")
    (out_dir / "eval_report.md").write_text(
        render_report(h, failures, matches, shipped, input_hashes(data), alpha), encoding="utf-8", newline="\n")
    (out_dir / "eval_result.json").write_text(json.dumps(
        {"gate": "pass" if not failures else "fail", "failures": failures, "matches_shipped_report": matches,
         "metrics": h, "alpha": alpha, "seconds": round(time.time() - t0, 1)}, indent=2), encoding="utf-8")
    return h, failures, matches


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--alpha", type=float, default=json.loads((ROOT / "detector" / "reference" / "params.json").read_text())["calibration_alpha"],
                    help="calibration alpha (params.json); the 0.1%% false-alarm TARGET is a separate constant")
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    h, failures, matches = run(a.data, a.alpha, a.out)
    print((a.out / "eval_report.md").read_text(encoding="utf-8"))
    if not matches:
        print("FAIL: recomputed numbers differ from the committed detector_report.md")
    for f in failures:
        print("GATE FAIL:", f)
    return 1 if (failures or not matches) else 0


if __name__ == "__main__":
    sys.exit(main())
