"""Rising-pattern detection: notice a scam workflow that is suddenly becoming common (problem statement: "emerging").

The phones send anonymised signatures (no device id, no personal data): which mechanism fired and which of the detector's
numbers were high. A new scam shows up as one pattern climbing faster than its normal level. This watches each
pattern's daily count with a CUSUM and flags the day it climbs. Offline, free, standard library plus numpy.

Two ways to use it (repo root):
  python ops/eval/rising_patterns.py --signatures signatures.csv   # a CSV with columns: day,pattern  (one row per signature)
  python ops/eval/rising_patterns.py --demo                        # measured on a simulated new scam, many seeds

What the demo is, and is not: it injects a brand-new pattern into simulated daily counts built from SatarkSim's real scam
mix. It shows how quickly the detector notices a rise, and how often it cries wolf on normal days. It is not evidence about
real scams, whose growth and noise nobody has measured yet.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

K_DEFAULT = 0.5     # slack: ignore rises smaller than half a standard deviation
H_DEFAULT = 5.0     # alarm threshold on the cumulative sum
MU_FLOOR = 1.0      # a pattern that is almost never seen is treated as averaging one a day, so one stray sighting is not a rise


def pattern_key(mechanism: str, features: dict[str, float], top: int = 3) -> str:
    """The key a signature is counted under: its mechanism plus its `top` highest features, by name, order-free."""
    ranked = sorted(features.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return mechanism + "|" + ",".join(sorted(name for name, v in ranked if v > 0))


def cusum_first_alarm(counts, baseline_days: int, k: float = K_DEFAULT, h: float = H_DEFAULT):
    """Index of the first day the CUSUM crosses h, judged against the first `baseline_days`; None if it never does."""
    x = np.asarray(counts, dtype=float)
    if baseline_days < 2 or len(x) <= baseline_days:
        return None
    mu = max(float(x[:baseline_days].mean()), MU_FLOOR)
    sd = math.sqrt(mu)  # counts are close to Poisson: variance is about the mean
    s = 0.0
    for i in range(baseline_days, len(x)):
        s = max(0.0, s + (x[i] - mu) / sd - k)
        if s > h:
            return i
    return None


def scan(daily: dict[str, list[int]], baseline_days: int, k: float = K_DEFAULT, h: float = H_DEFAULT) -> dict[str, int]:
    """Day index of the first alarm for every pattern that raised one."""
    out = {}
    for name, counts in daily.items():
        i = cusum_first_alarm(counts, baseline_days, k, h)
        if i is not None:
            out[name] = i
    return out


def daily_counts(rows, days: int) -> dict[str, list[int]]:
    """rows: iterable of (day, pattern). Returns pattern -> list of counts for day 0..days-1."""
    out: dict[str, list[int]] = {}
    for day, pat in rows:
        d = int(day)
        if 0 <= d < days:
            out.setdefault(pat, [0] * days)[d] += 1
    return out


# ---- the simulated experiment -------------------------------------------------------------------------------------

def scam_mix(sessions_csv: Path) -> dict[str, float]:
    """Share of each scam playbook in SatarkSim, used as the normal mix of patterns."""
    import pandas as pd

    s = pd.read_csv(sessions_csv, usecols=["label", "playbook"])
    s = s[s.label == "scam"]
    return (s.playbook.value_counts(normalize=True)).to_dict()


def simulate(mix: dict[str, float], per_day_total: float, days: int, new_start: int, new_level: float,
             ramp_days: int, rng: np.random.Generator):
    """Daily Poisson counts for the normal patterns, plus 'NEW' appearing at `new_start` and ramping to `new_level` a day."""
    daily = {name: rng.poisson(per_day_total * share, size=days).tolist() for name, share in mix.items()}
    ramp = np.clip((np.arange(days) - new_start + 1) / max(ramp_days, 1), 0, 1) * new_level
    ramp[:new_start] = 0
    daily["NEW"] = rng.poisson(ramp).tolist()
    return daily


def experiment(mix, per_day_total=60.0, days=84, baseline=28, new_start=56, new_level=8.0, ramp_days=7,
               seeds=300, k=K_DEFAULT, h=H_DEFAULT) -> dict:
    delays, missed, false_flags, normal_pattern_days = [], 0, 0, 0
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        flags = scan(simulate(mix, per_day_total, days, new_start, new_level, ramp_days, rng), baseline, k, h)
        if "NEW" in flags and flags["NEW"] >= new_start:
            delays.append(flags["NEW"] - new_start)
        else:
            missed += 1
        false_flags += sum(1 for n in flags if n != "NEW")
        normal_pattern_days += len(mix) * (days - baseline)
    d = np.array(delays) if delays else np.array([np.nan])
    return {
        "seeds": seeds, "days": days, "baseline_days": baseline, "new_pattern_starts_day": new_start,
        "new_pattern_final_per_day": new_level, "ramp_days": ramp_days, "normal_total_per_day": per_day_total,
        "k": k, "h": h, "patterns_in_normal_mix": len(mix),
        "detected": len(delays), "missed": missed, "missed_rate": missed / seeds,
        "delay_days_median": float(np.nanmedian(d)), "delay_days_p90": float(np.nanpercentile(d, 90)),
        "false_flags_total": false_flags,
        "false_flags_per_pattern_year": false_flags / (normal_pattern_days / 365.0),
    }


def render(e: dict, mix: dict[str, float], sweep: list[dict] | None = None) -> str:
    sweep_table = ""
    if sweep:
        rows = "\n".join(
            f"| {r['new_pattern_final_per_day']:.0f} a day | {100 * (1 - r['missed_rate']):.1f}% | {r['delay_days_median']:.0f} "
            f"| {r['delay_days_p90']:.0f} | {r['false_flags_per_pattern_year']:.2f} |" for r in sweep)
        sweep_table = f"""
## How small a new scam can it catch?
(same method, only the size of the new pattern changes; the number is where it levels off)

| New pattern size | Noticed | Median days | 90th percentile days | False flags per pattern per year |
|---|---|---|---|---|
{rows}
"""
    mix_lines = "\n".join(f"| {k} | {100 * v:.1f}% |" for k, v in sorted(mix.items(), key=lambda kv: -kv[1]))
    return f"""# Rising-pattern detection

**Simulated experiment. A new scam pattern is injected into counts built from SatarkSim's scam mix. This says how the
detector behaves, not how real scams grow.**

## Method
Each pattern's daily count is watched with a CUSUM (slack k = {e['k']}, alarm at h = {e['h']}), judged against its own first
{e['baseline_days']} days. A new pattern appears on day {e['new_pattern_starts_day']} and ramps over {e['ramp_days']} days to
{e['new_pattern_final_per_day']:.0f} signatures a day, on top of about {e['normal_total_per_day']:.0f} a day across the normal
patterns. {e['seeds']} random runs of {e['days']} days.

## Result
| | |
|---|---|
| New pattern noticed | {e['detected']} of {e['seeds']} runs ({100 * (1 - e['missed_rate']):.1f}%) |
| Days from its first appearance to the flag | median {e['delay_days_median']:.0f}, 90th percentile {e['delay_days_p90']:.0f} |
| False flags on the normal patterns | {e['false_flags_total']} in total, {e['false_flags_per_pattern_year']:.2f} per pattern per year |

{sweep_table}
## The normal mix used (SatarkSim scam playbooks)
| Pattern | Share |
|---|---|
{mix_lines}

## Limits
- Counts are assumed to be roughly Poisson. Real signature counts are likely burstier, which would raise false flags.
- The thresholds (k, h) were set once and not tuned to this experiment.
- A very slow rise is caught late; a pattern that is already common at the start is treated as normal.
- The pattern key (mechanism plus the three highest features) is a design choice. Different keys group scams differently.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signatures", type=Path, help="CSV with columns day,pattern")
    ap.add_argument("--baseline", type=int, default=28)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "eval" / "reports")
    a = ap.parse_args(argv)
    if a.signatures:
        import csv

        with a.signatures.open(newline="", encoding="utf-8") as f:
            rows = [(r["day"], r["pattern"]) for r in csv.DictReader(f)]
        days = max(int(d) for d, _ in rows) + 1
        flags = scan(daily_counts(rows, days), a.baseline)
        print(json.dumps({"rising": {k: int(v) for k, v in flags.items()}}, indent=2))
        return 0
    mix = scam_mix(a.data / "satarksim_sessions.csv")
    e = experiment(mix)
    sweep = [experiment(mix, new_level=lv, seeds=200) for lv in (2.0, 4.0, 8.0, 16.0)]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "rising_patterns.md").write_text(render(e, mix, sweep), encoding="utf-8", newline="\n")
    (a.out / "rising_patterns.json").write_text(json.dumps({"headline": e, "sweep": sweep}, indent=2), encoding="utf-8")
    print(render(e, mix, sweep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
