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


def _two_cohorts(fa_a, fa_b):
    rows = []
    for band, fa in (("a", fa_a), ("b", fa_b)):
        rows += [("validation", "legit", i < fa, band, "x", True) for i in range(1000)]
        rows += [("validation", "scam", True, band, "x", True) for _ in range(50)]
    return ev.fairness(_res(rows))


def test_false_alarm_ratio_is_na_and_not_a_failure_when_a_cohort_has_fewer_than_five():
    f = _two_cohorts(2, 0)
    assert f["age band"]["false_alarm_ratio"] is None
    assert ev.fairness_gate(f) == []
    assert _two_cohorts(4, 40)["age band"]["false_alarm_ratio"] is None   # 4 < 5 in one cohort: still n/a


def test_false_alarm_ratio_counts_and_can_fail_once_every_cohort_has_five():
    ok = _two_cohorts(5, 7)
    assert math.isclose(ok["age band"]["false_alarm_ratio"], 1.4) and ev.fairness_gate(ok) == []
    bad = _two_cohorts(5, 8)
    assert math.isclose(bad["age band"]["false_alarm_ratio"], 1.6)
    assert any("false-alarm" in x for x in ev.fairness_gate(bad))


def test_the_recall_ratio_gate_stays_strict():
    rows = [("validation", "scam", i < 10, "a", "x", True) for i in range(20)] + [("validation", "scam", i < 5, "b", "x", True) for i in range(20)]
    rows += [("validation", "legit", False, c, "x", True) for c in ("a", "b") for _ in range(10)]
    f = ev.fairness(_res(rows))
    assert f["age band"]["recall_ratio"] == 2.0
    assert any("recall" in x for x in ev.fairness_gate(f))


def test_only_the_validation_split_counts_and_equal_cohorts_pass():
    rows = []
    for band in ("a", "b"):
        rows += [("validation", "scam", True, band, "x", True) for _ in range(20)]
        rows += [("validation", "legit", False, band, "x", True) for _ in range(20)]
        rows += [("train", "legit", True, band, "x", True) for _ in range(20)]   # ignored
    f = ev.fairness(_res(rows))
    assert ev.fairness_gate(f) == []
    assert all(r["false_alarms"] == 0 for r in f["age band"]["rows"])
