import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import rising_patterns as rp  # noqa: E402


def counts(rows):
    """rows: {pattern: [n for week 0, 1, 2, ...]}"""
    return pd.DataFrame([{"week": w, "pattern": p, "n": n} for p, ns in rows.items() for w, n in enumerate(ns)])


STEADY = [60, 62, 58, 61, 59, 63, 60]


def test_a_pattern_never_seen_before_is_new():
    t = rp.find_rising(counts({"mechanism:payment_score": STEADY, "app:com.remotehelp.newtool": [0, 0, 0, 0, 0, 0, 40]}), week=6)
    r = t.set_index("pattern")
    assert r.loc["app:com.remotehelp.newtool", "status"] == "NEW" and r.loc["app:com.remotehelp.newtool", "this_week"] == 40
    assert "mechanism:payment_score" not in r.index                                    # a steady pattern is not news


def test_a_big_jump_is_rising_and_a_small_wobble_is_not():
    t = rp.find_rising(counts({"a": [60, 62, 58, 61, 59, 63, 105], "b": [60, 62, 58, 61, 59, 63, 70], "c": STEADY}), week=6).set_index("pattern")
    assert t.loc["a", "status"] == "RISING" and t.loc["a", "ratio"] > 1.5
    assert "b" not in t.index and "c" not in t.index                                   # +16% is within normal weekly noise


def test_tiny_counts_are_never_flagged_however_large_the_ratio():
    t = rp.find_rising(counts({"rare": [0, 0, 0, 0, 0, 0, 3], "steady": STEADY}), week=6)
    assert t.empty                                                                     # 3 sessions is not a pattern (min_count 5)


def test_new_requires_the_whole_baseline_to_be_empty():
    t = rp.find_rising(counts({"x": [0, 0, 0, 0, 1, 0, 30], "y": STEADY}), week=6)
    assert "x" not in t.pattern.values or t.set_index("pattern").loc["x", "status"] == "RISING"     # seen once in the baseline: not NEW


def test_the_baseline_is_only_the_weeks_just_before():
    series = {"z": [200, 200, 200, 5, 5, 5, 5, 60]}                                    # was big long ago, tiny recently, now moderate
    assert rp.find_rising(counts(series), week=7, baseline_weeks=4).set_index("pattern").loc["z", "status"] == "RISING"
    assert rp.find_rising(counts(series), week=7, baseline_weeks=7).empty              # against the whole history it is not a rise


def test_testing_many_patterns_makes_each_test_stricter():
    """Bonferroni: a borderline count is flagged alone but not among 200 other patterns that were also looked at."""
    base = {"borderline": [20, 21, 19, 20, 20, 21, 36]}
    alone = rp.find_rising(counts(base), week=6)
    crowd = {f"p{i}": [30, 31, 29, 30, 30, 31, 30] for i in range(200)}
    crowded = rp.find_rising(counts({**base, **crowd}), week=6)
    assert "borderline" in alone.pattern.values and "borderline" not in crowded.pattern.values


def test_new_patterns_are_listed_before_rising_ones():
    t = rp.find_rising(counts({"r": [60, 62, 58, 61, 59, 63, 120], "n": [0, 0, 0, 0, 0, 0, 12]}), week=6)
    assert list(t.status) == ["NEW", "RISING"]


def test_it_refuses_a_week_it_cannot_compare():
    c = counts({"a": STEADY})
    with pytest.raises(ValueError, match="not in the data"):
        rp.find_rising(c, week=99)
    with pytest.raises(ValueError, match="two earlier weeks"):
        rp.find_rising(c, week=1)


def test_counts_from_alarmed_sessions_only_and_apps_counted_once_per_session():
    res = pd.DataFrame({"session_id": ["s1", "s2", "s3"], "week": [3, 3, 3], "alarm": [True, True, False],
                        "mechanism": ["payment_score", "sideload_during_call", "none"]})
    ev = pd.DataFrame({"session_id": ["s1", "s1", "s2", "s3", "s1"],
                       "app_package": ["com.anydesk", "com.anydesk", "apk.unknown.123456", "com.anydesk", None]})
    c = rp.counts_from(res, ev).set_index("pattern").n
    assert c["mechanism:payment_score"] == 1 and c["mechanism:sideload_during_call"] == 1 and "mechanism:none" not in c.index
    assert c["app:com.anydesk"] == 1                                                   # s1 counted once; s3 was not alarmed
    assert c[rp.UNKNOWN_APK] == 1                                                      # random sideloaded packages are one pattern, not thousands


def test_the_report_labels_the_seed_as_simulated():
    text = rp.report(counts({"a": [60, 62, 58, 61, 59, 63, 105], "n": [0, 0, 0, 0, 0, 0, 12]}), (6,))
    assert "SatarkSim" in text and "not real traffic" in text and "NEW" in text and "never seen before" in text


@pytest.mark.skipif(not rp.SEED.is_file(), reason="seed not built yet")
def test_the_committed_seed_finds_the_app_the_simulator_introduces_in_week_6():
    c = pd.read_csv(rp.SEED)
    t = rp.find_rising(c, 6).set_index("pattern")
    assert "app:com.remotehelp.newtool" in t.index and t.loc["app:com.remotehelp.newtool", "status"] == "NEW"
    assert rp.find_rising(c, 5).pipe(lambda d: "app:com.remotehelp.newtool" not in d.pattern.values)   # and not before
