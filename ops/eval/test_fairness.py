import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import run_eval as ev  # noqa: E402


def _res(rows):
    return pd.DataFrame(rows, columns=["split", "label", "alarm", "age_band", "activity_tier", "call_state_available"])


def test_ratio_cases():
    assert ev.ratio([0.9, 0.9]) == 1.0
    assert math.isclose(ev.ratio([0.6, 0.9]), 1.5)
    assert ev.ratio([0.0, 0.0]) == 1.0
    assert ev.ratio([0.0, 0.001]) == float("inf")


def test_gate_fails_above_the_limit_and_passes_at_it():
    base = {"age band": {"recall_ratio": 1.5, "false_alarm_ratio": 1.0}}
    assert ev.fairness_gate(base) == []
    assert len(ev.fairness_gate({"age band": {"recall_ratio": 1.51, "false_alarm_ratio": 1.0}})) == 1


def test_a_cohort_with_no_false_alarms_fails_the_gate_as_written():
    rows = []
    for band, fa in (("a", 2), ("b", 0)):
        rows += [("validation", "legit", i < fa, band, "x", True) for i in range(1000)]
        rows += [("validation", "scam", True, band, "x", True) for _ in range(50)]
    f = ev.fairness(_res(rows))
    assert f["age band"]["false_alarm_ratio"] == float("inf")
    assert any("false-alarm" in x for x in ev.fairness_gate(f))


def test_only_the_validation_split_counts_and_equal_cohorts_pass():
    rows = []
    for band in ("a", "b"):
        rows += [("validation", "scam", True, band, "x", True) for _ in range(20)]
        rows += [("validation", "legit", False, band, "x", True) for _ in range(20)]
        rows += [("train", "legit", True, band, "x", True) for _ in range(20)]   # ignored
    f = ev.fairness(_res(rows))
    assert ev.fairness_gate(f) == []
    assert all(r["false_alarms"] == 0 for r in f["age band"]["rows"])
