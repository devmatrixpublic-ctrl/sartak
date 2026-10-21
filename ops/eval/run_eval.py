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

Usage (repo root):  python ops/eval/run_eval.py [--data data/satarksim] [--alpha 0.001]
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
        f"**Gate: {status}** (recall >= {RECALL_MIN:.0%} and false alarms <= {FALSE_ALARM_MAX:.1%}, point estimates, alpha = {alpha:.1%})", "",
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
    shipped = parse_shipped_report(shipped_report)
    matches = all(h[k] == shipped[k] for k in shipped)
    failures = gate(h)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval_report.md").write_text(
        render_report(h, failures, matches, shipped, input_hashes(data), alpha), encoding="utf-8", newline="\n")
    (out_dir / "eval_result.json").write_text(json.dumps(
        {"gate": "pass" if not failures else "fail", "failures": failures, "matches_shipped_report": matches,
         "metrics": h, "alpha": alpha, "seconds": round(time.time() - t0, 1)}, indent=2), encoding="utf-8")
    return h, failures, matches


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--alpha", type=float, default=0.001)
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
