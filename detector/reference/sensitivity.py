#!/usr/bin/env python3
"""Sensitivity of SatarkSim results to the scam-timing assumptions (#6).

Rebuilds SatarkSim with every scam timing range multiplied by 0.5x, 1x and 2x and reports the naive-baseline
metrics per playbook. If conclusions flip between scales, they depend on assumptions, not on the design.
The naive rule is a stand-in until the Satark detector exists; rerun this with the real detector later.

Usage: python sensitivity.py --kaggle-upi ... --npci-xlsx ... --out data/sensitivity_report.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_satarksim import build_all, fit_amount_model, load_kaggle, naive_rule, npci_avg_ticket


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--params", type=Path, default=Path(__file__).with_name("params.json"))
    ap.add_argument("--kaggle-upi", type=Path, default=None)
    ap.add_argument("--npci-xlsx", type=Path, default=None)
    ap.add_argument("--scales", type=float, nargs="+", default=[0.5, 1.0, 2.0])
    ap.add_argument("--out", type=Path, default=Path("data/sensitivity_report.md"))
    a = ap.parse_args()

    p = json.loads(a.params.read_text())
    target = npci_avg_ticket(a.npci_xlsx)[0] if a.npci_xlsx else None
    am = fit_amount_model(p, target)
    kaggle = load_kaggle(a.kaggle_upi)

    rows = []
    for sc in a.scales:
        _, sessions, events = build_all(p, am, kaggle, sc)
        s = sessions.merge(naive_rule(events).rename("naive").rename_axis("session_id").reset_index(), on="session_id")
        v = s[s.split == "validation"]
        r = {"timing scale": f"{sc}×",
             "overall recall": v[v.label == "scam"].naive.mean(),
             "false-flag rate": v[v.label == "legit"].naive.mean()}
        r.update({pb: val for pb, val in v[v.label == "scam"].groupby("playbook").naive.mean().items()})
        rows.append(r)
        print(f"scale {sc}: done")

    df = pd.DataFrame(rows).set_index("timing scale")
    spread = (df.max() - df.min()).rename("max − min")
    cols = list(df.columns)
    L = ["# Timing-assumption sensitivity", "",
         "Every scam timing range in `params.json` was multiplied by the scale below; everything else was held fixed "
         "(same seed). Metric: naive co-occurrence baseline on the validation split (a stand-in until the detector exists).", "",
         "| Timing scale | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for idx, r in df.iterrows():
        L.append(f"| {idx} | " + " | ".join(f"{r[c]:.2f}" for c in cols) + " |")
    L.append("| **max − min** | " + " | ".join(f"**{spread[c]:.2f}**" for c in cols) + " |")
    sensitive = [c for c in cols if spread[c] > 0.15]
    L += ["", "## Reading it", "",
          ("- Sensitive to timing assumptions (spread > 0.15): **" + ", ".join(sensitive) + "**. Results for these playbooks "
           "depend on how fast scams unfold, so report them with this caveat." if sensitive else
           "- No metric moves by more than 0.15 across a 4× change in timing: conclusions are robust to the timing assumptions."),
          "- The false-flag rate does not depend on scam timings (legit sessions are unchanged); it is shown as a control.",
          "- Rerun with the real Satark detector once it exists; the naive rule only shows how much the data itself shifts.", ""]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
