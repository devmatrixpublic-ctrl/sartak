#!/usr/bin/env python3
"""New and rising scam patterns this week (plan "Person B", phase 3: the adaptation a judge can see).

A "pattern" is something the server can observe about an alarmed session without knowing the true label: the rule that fired
(`mechanism:payment_score`, `mechanism:sideload_during_call`, ...) or an app seen in the session (`app:com.remotehelp.newtool`). Each week the
server counts how many alarmed sessions showed each pattern. A pattern is flagged when this week's count is
  * NEW: it was never seen in the baseline weeks (and shows up in at least `min_count` sessions now), or
  * RISING: this week's count is far above the baseline mean: a Poisson upper-tail probability below alpha, Bonferroni-corrected over
    every pattern tested, and at least `min_ratio` times the baseline mean.
This is a deliberately plain statistical test, not CUSUM and not a learned model.

SEED DATA: there is no real traffic. `--make-seed` builds ops/dashboard/seed_pattern_counts.csv from the SatarkSim alarms of the shipped
detector. SatarkSim deliberately introduces one new remote-access app and a rising share of malicious APKs from week 6, so the seed has
something real to find. Everything the page shows from it is labelled simulated; it demonstrates that the mechanism works, not how often
real scams change.

Usage (repo root):
  python ops/dashboard/rising_patterns.py --week 6            # print the table for a week of the seed
  python ops/dashboard/rising_patterns.py --make-seed         # rebuild the seed from the SatarkSim alarms (about a minute)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SEED = Path(__file__).with_name("seed_pattern_counts.csv")
SEED_LABEL = ("Seed data: counts of ALARMED sessions per week from the SatarkSim simulator (12 weeks, 53,000 sessions), not real traffic. "
              "The simulator introduces a new remote-access app and more malicious APKs from week 6; this view shows that the mechanism finds them.")
UNKNOWN_APK = "app:(random sideloaded apk)"


def find_rising(counts: pd.DataFrame, week: int, baseline_weeks: int = 4, min_count: int = 5, alpha: float = 0.01,
                min_ratio: float = 1.5) -> pd.DataFrame:
    """counts: columns week, pattern, n. Returns the flagged patterns for `week`: pattern, this_week, baseline_mean, ratio, p_value, status."""
    from scipy.stats import poisson

    pivot = counts.pivot_table(index="pattern", columns="week", values="n", aggfunc="sum", fill_value=0)
    if week not in pivot.columns:
        raise ValueError(f"week {week} is not in the data (weeks {int(pivot.columns.min())}-{int(pivot.columns.max())})")
    prior = [w for w in sorted(pivot.columns) if w < week][-baseline_weeks:]
    if len(prior) < 2:
        raise ValueError("need at least two earlier weeks to compare against")
    tested = pivot[pivot[week] >= min_count]
    m = max(len(tested), 1)                                                # Bonferroni: the more patterns we look at, the stricter each test
    rows = []
    for pattern, r in tested.iterrows():
        this, base = int(r[week]), r[prior]
        mean = float(base.mean())
        if base.sum() == 0:
            rows.append({"pattern": pattern, "this_week": this, "baseline_mean": 0.0, "ratio": float("inf"), "p_value": 0.0, "status": "NEW"})
            continue
        p = float(poisson.sf(this - 1, max(mean, 0.5)))
        if p < alpha / m and this / mean >= min_ratio:
            rows.append({"pattern": pattern, "this_week": this, "baseline_mean": mean, "ratio": this / mean, "p_value": p, "status": "RISING"})
    out = pd.DataFrame(rows, columns=["pattern", "this_week", "baseline_mean", "ratio", "p_value", "status"])
    out["order"] = out.status.map({"NEW": 0, "RISING": 1})
    return out.sort_values(["order", "p_value", "this_week"], ascending=[True, True, False]).drop(columns="order").reset_index(drop=True)


def render_markdown(table: pd.DataFrame, week: int, baseline_weeks: int = 4) -> str:
    L = [f"### Week {week} compared with the previous {baseline_weeks} weeks", ""]
    if table.empty:
        L += ["Nothing new or rising this week.", ""]
        return "\n".join(L)
    L += ["| Pattern | Status | Alarmed sessions this week | Baseline weekly mean | Times the baseline |", "|---|---|---|---|---|"]
    for _, r in table.iterrows():
        ratio = "never seen before" if r.status == "NEW" else f"{r.ratio:.1f}x"
        L.append(f"| `{r.pattern}` | {r.status} | {int(r.this_week)} | {r.baseline_mean:.1f} | {ratio} |")
    return "\n".join(L) + "\n"


def report(counts: pd.DataFrame, weeks: tuple[int, ...], with_heading: bool = True) -> str:
    L = (["## New patterns this week", ""] if with_heading else []) + [f"**{SEED_LABEL}**", "",
         "A pattern is NEW if it never appeared in the baseline weeks and now shows up in at least 5 alarmed sessions; RISING if its count is far above "
         "the baseline mean by a Poisson test (Bonferroni-corrected, alpha 1%, at least 1.5x).", ""]
    for w in weeks:
        L.append(render_markdown(find_rising(counts, w), w))
    return "\n".join(L)


# ---- building the seed from the simulator --------------------------------------------------------------------------------------
def counts_from(res: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Weekly counts of observable patterns over ALARMED sessions. res: session_id, week, alarm, mechanism. events: session_id, app_package."""
    alarmed = res[res.alarm][["session_id", "week", "mechanism"]]
    mech = alarmed.assign(pattern="mechanism:" + alarmed.mechanism).groupby(["week", "pattern"]).size().rename("n")
    apps = events[events.session_id.isin(alarmed.session_id) & events.app_package.notna()][["session_id", "app_package"]].drop_duplicates()
    apps = apps.assign(pattern=apps.app_package.map(lambda a: UNKNOWN_APK if str(a).startswith("apk.unknown.") else f"app:{a}"))
    apps = apps.drop_duplicates(["session_id", "pattern"]).merge(alarmed[["session_id", "week"]], on="session_id")
    app_counts = apps.groupby(["week", "pattern"]).size().rename("n")
    return pd.concat([mech, app_counts]).reset_index().sort_values(["week", "pattern"]).reset_index(drop=True)


def make_seed(out: Path = SEED) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "ops" / "eval"))
    sys.path.insert(0, str(ROOT / "detector" / "reference"))
    from fresh_seed_eval import load_detector

    params = json.loads((ROOT / "detector" / "reference" / "params.json").read_text(encoding="utf-8"))
    _, det, res = load_detector(params["calibration_alpha"], params["watchlisted_remote_apps"])
    events = pd.read_csv(ROOT / "data" / "satarksim" / "satarksim_events.csv", usecols=["session_id", "app_package"], low_memory=False)
    counts = counts_from(res, events)
    out.write_text(counts.to_csv(index=False), encoding="utf-8", newline="\n")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", type=int, action="append", help="week to analyse (repeatable); default 6 and the last week")
    ap.add_argument("--seed", type=Path, default=SEED)
    ap.add_argument("--make-seed", action="store_true")
    a = ap.parse_args(argv)
    if a.make_seed:
        c = make_seed(a.seed)
        print(f"wrote {a.seed} ({len(c)} rows)")
    counts = pd.read_csv(a.seed)
    weeks = tuple(a.week) if a.week else (6, int(counts.week.max()))
    print(report(counts, weeks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
