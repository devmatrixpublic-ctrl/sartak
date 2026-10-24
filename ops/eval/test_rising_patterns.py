import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import rising_patterns as rp  # noqa: E402


def test_pattern_key_is_stable_and_order_free():
    a = rp.pattern_key("payment_score", {"new_payee": 3.0, "unk_call_active": 2.0, "watchlist_app": 1.0, "is_p2p": 0.5})
    b = rp.pattern_key("payment_score", {"is_p2p": 0.5, "watchlist_app": 1.0, "unk_call_active": 2.0, "new_payee": 3.0})
    assert a == b == "payment_score|new_payee,unk_call_active,watchlist_app"
    assert rp.pattern_key("rule", {"a": 0.0}) == "rule|"  # nothing high: just the mechanism


def test_steady_counts_rarely_raise_a_flag():
    flags = 0
    for seed in range(200):
        counts = np.random.default_rng(seed).poisson(12, size=84)
        flags += rp.cusum_first_alarm(counts, 28) is not None
    assert flags / 200 < 0.25  # 84-day series; the report quotes the exact false-flag rate


def test_a_clear_rise_is_flagged_within_days():
    rng = np.random.default_rng(1)
    counts = np.concatenate([rng.poisson(10, 40), rng.poisson(30, 14)])
    day = rp.cusum_first_alarm(counts, 28)
    assert day is not None and 40 <= day <= 44


def test_one_stray_sighting_of_a_rare_pattern_is_not_a_rise():
    counts = [0] * 28 + [1] + [0] * 20
    assert rp.cusum_first_alarm(counts, 28) is None


def test_short_or_missing_baseline_never_flags():
    assert rp.cusum_first_alarm([5, 5, 5], 28) is None
    assert rp.cusum_first_alarm(list(range(30)), 1) is None
    assert rp.cusum_first_alarm([], 28) is None


def test_scan_returns_only_the_patterns_that_rose():
    rng = np.random.default_rng(3)
    daily = {"steady": rng.poisson(10, 60).tolist(), "new": (rng.poisson(1, 40).tolist() + rng.poisson(20, 20).tolist())}
    assert "new" in rp.scan(daily, 28)


def test_daily_counts_builds_a_series_per_pattern_and_ignores_out_of_range_days():
    rows = [(0, "a"), (0, "a"), (2, "a"), (1, "b"), (9, "a"), (-1, "a")]
    out = rp.daily_counts(rows, 3)
    assert out == {"a": [2, 0, 1], "b": [0, 1, 0]}


def test_the_experiment_is_repeatable_and_finds_a_big_new_pattern():
    mix = {"p1": 0.5, "p2": 0.3, "p3": 0.2}
    a = rp.experiment(mix, seeds=40, new_level=8.0)
    b = rp.experiment(mix, seeds=40, new_level=8.0)
    assert a == b
    assert a["detected"] >= 38 and a["delay_days_median"] <= 5
