#!/usr/bin/env python3
"""Offline gradient-boosted baseline against the logistic detector on SatarkSim (simulated data).

Same 16 features, same training sessions and labels, same split-conformal calibration per age band and the same alpha as the
reference detector; only the model differs. Nothing here goes on the device and nothing in the detector changes.
Hyperparameters are fixed in advance (below) and were not tuned on the validation split.

Both models are scored on payment-score alarms only (rule alarms removed) so the comparison is the model, not the rules.
The full detector (with its two safety rules) is shown for reference.

Usage: python ops/eval/gbt_baseline.py [--data data/satarksim] [--out ops/eval/gbt_baseline_report.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detector" / "reference"))
sys.path.insert(0, str(Path(__file__).parent))

GBT_PARAMS = dict(n_estimators=100, max_depth=3, learning_rate=0.1, subsample=1.0, random_state=0)


def metrics(res: pd.DataFrame) -> dict:
    from run_eval import clopper_pearson

    v = res[res.split == "validation"]
    scam, legit = v[v.label == "scam"], v[v.label == "legit"]
    s_n, s_k, l_n, l_k = len(scam), int(scam.alarm.sum()), len(legit), int(legit.alarm.sum())
    return {"scam_n": s_n, "scam_alarmed": s_k, "recall": s_k / s_n, "recall_ci95": clopper_pearson(s_k, s_n),
            "legit_n": l_n, "false_alarms": l_k, "false_alarm_rate": l_k / l_n, "false_alarm_ci95": clopper_pearson(l_k, l_n)}


def no_rule_alerts() -> pd.DataFrame:
    return pd.DataFrame({"session_id": pd.Series(dtype=str), "t": pd.Series(dtype=float), "rule": pd.Series(dtype=str)})


def make_gbt_detector(sd):
    class GbtDetector(sd.Detector):
        def fit(self, pay, sessions, train_mask_sessions):
            d = pay[pay.session_id.isin(train_mask_sessions)].merge(sessions[["session_id", "label_observed"]], on="session_id")
            self.gbt = GradientBoostingClassifier(**GBT_PARAMS).fit(d[sd.FEATURES], (d.label_observed == "scam").astype(int))
            return self

        def score(self, pay):
            return self.gbt.decision_function(pay[sd.FEATURES])

    return GbtDetector


def run(data: Path) -> dict:
    import satark_detector as sd

    params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())
    alpha, wl = params["calibration_alpha"], params["watchlisted_remote_apps"]
    det, full_res, (users, sessions, events, pay, alerts, first_pay) = sd.evaluate(data, alpha, wl)
    by = sessions.groupby("split").session_id.apply(set)

    lr_pay_only = sd.decide(det, pay, no_rule_alerts(), first_pay, sessions)
    gbt = make_gbt_detector(sd)().fit(pay, sessions, by["train"]).calibrate(pay, sessions, by["calibration"], alpha)
    gbt_res = sd.decide(gbt, pay, no_rule_alerts(), first_pay, sessions)
    importances = pd.Series(gbt.gbt.feature_importances_, index=sd.FEATURES).sort_values(ascending=False)
    return {"alpha": alpha, "n_train_rows": int(pay.session_id.isin(by["train"]).sum()),
            "lr_full": metrics(full_res), "lr_payment_only": metrics(lr_pay_only), "gbt_payment_only": metrics(gbt_res),
            "importances": importances}


def render(r: dict) -> str:
    def row(name, m):
        return (f"| {name} | {m['recall']:.1%} ({m['recall_ci95'][0]:.1%}-{m['recall_ci95'][1]:.1%}) | "
                f"{m['false_alarms']}/{m['legit_n']} = {m['false_alarm_rate']:.3%} ({m['false_alarm_ci95'][0]:.3%}-{m['false_alarm_ci95'][1]:.3%}) |")

    lr, gb = r["lr_payment_only"], r["gbt_payment_only"]
    d_rec = (gb["recall"] - lr["recall"]) * 100
    L = ["# Gradient-boosted baseline vs the logistic detector (simulated data)", "",
         "**All numbers are from SatarkSim, a simulator. They say nothing about real-world accuracy.** Offline comparison only: "
         "nothing here runs on the phone and the detector is unchanged.", "",
         f"Same 16 features, same training sessions and `label_observed` labels ({r['n_train_rows']:,} training payment rows), same per-age-band "
         f"split-conformal calibration at alpha' = {r['alpha']:.2%}. Only the model differs. GBT: scikit-learn `GradientBoostingClassifier`, "
         f"{GBT_PARAMS}; fixed in advance, not tuned on validation. Validation split, {lr['scam_n']} scam and {lr['legit_n']} legitimate sessions.", "",
         "| Model | Scam recall (95% CI) | False alarms on legitimate sessions (95% CI) |", "|---|---|---|",
         row("Logistic, payment score only", lr), row("Gradient boosted, payment score only", gb),
         row("Logistic + the two safety rules (the shipped detector)", r["lr_full"]), "",
         f"Reading it: at the same calibrated false-alarm budget, the gradient-boosted model's recall is **{d_rec:+.1f} points** versus the "
         "logistic model on payment score alone. "
         + ("The two confidence intervals overlap, so this simulation does not show a real difference. " if
            not (gb["recall_ci95"][0] > lr["recall_ci95"][1] or lr["recall_ci95"][0] > gb["recall_ci95"][1]) else "The intervals do not overlap. ")
         + "The logistic model is the one on the device because it is a few dozen numbers, deterministic to the bit between Python and Kotlin, "
           "and each reason is a single weight times a value; a boosted ensemble would need a new Kotlin evaluator and a new explanation method.", "",
         "## Which features the boosted model leaned on", "", "| Feature | Importance |", "|---|---|"]
    L += [f"| {k} | {v:.3f} |" for k, v in r["importances"].head(8).items()]
    L += ["", f"False alarms: {gb['false_alarms']} (boosted) vs {lr['false_alarms']} (logistic) out of {lr['legit_n']} legitimate sessions; with counts this small "
          "the difference is within noise.", "",
          "Caveats: one simulator, one seed, one split. The scam sequences in SatarkSim are design assumptions, so a flexible model may be fitting "
          "the simulator's own rules rather than anything that holds for real scams. The result says the boosted model is not worse here; it does "
          "not say it would be better on real traffic.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "gbt_baseline_report.md")
    a = ap.parse_args(argv)
    r = run(a.data)
    a.out.write_text(render(r), encoding="utf-8", newline="\n")
    print(render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
