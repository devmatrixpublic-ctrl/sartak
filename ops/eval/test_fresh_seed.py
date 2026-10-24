import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import fresh_seed_eval as fs  # noqa: E402


def row(**kw):
    base = dict(n_pay=1, call_state_available=True, usage_access=True, playbook="screen_share", week=3, thr=2.0, max_score=1.0)
    base.update(kw)
    return pd.Series(base)


def test_causes_are_tagged_in_a_fixed_order():
    assert "no payment screen" in fs.classify_miss(row(n_pay=0, call_state_available=False))          # earliest rule wins
    assert "call state" in fs.classify_miss(row(call_state_available=False, usage_access=False))
    assert "usage access" in fs.classify_miss(row(usage_access=False, playbook="remote_access", week=9))
    assert "watch-list" in fs.classify_miss(row(playbook="remote_access", week=6))
    assert fs.classify_miss(row(playbook="remote_access", week=5)) == fs.BELOW_THRESHOLD              # before the new app appears
    assert fs.classify_miss(row()) == fs.BELOW_THRESHOLD


def frame(labels, alarms, kinds=None, playbooks=None):
    n = len(labels)
    return pd.DataFrame({"label": labels, "alarm": alarms, "interdicted": alarms, "lead_min": [5.0] * n,
                         "session_kind": kinds or ["plain_payment"] * n, "playbook": playbooks or ["none"] * n})


def test_rates_count_scams_and_legit_separately():
    r = fs.rates(frame(["scam", "scam", "scam", "legit", "legit"], [True, True, False, False, True]))
    assert (r["scam_n"], r["scam_hit"], r["legit_n"], r["legit_fa"]) == (3, 2, 2, 1)


def test_pooling_adds_counts_and_does_not_average_rates():
    a = {"scam_n": 10, "scam_hit": 9, "legit_n": 100, "legit_fa": 1, "interdicted": 8, "median_lead_min": 4.0}
    b = {"scam_n": 30, "scam_hit": 15, "legit_n": 100, "legit_fa": 3, "interdicted": 10, "median_lead_min": 6.0}
    p = fs.pooled([a, b])
    assert (p["scam_n"], p["scam_hit"], p["legit_fa"]) == (40, 24, 4) and p["median_lead_min"] == 5.0


def test_precision_collapses_as_scams_get_rarer_and_matches_bayes():
    assert fs.precision(0.9, 0.001, 0.5) == pytest.approx(0.9 / (0.9 + 0.001))
    assert fs.precision(0.9, 0.001, 1e-4) < 0.1 < fs.precision(0.9, 0.001, 1e-2)
    assert np.isnan(fs.precision(0.0, 0.0, 0.1))


def test_playbook_and_false_alarm_breakdowns():
    res = frame(["scam", "scam", "legit", "legit", "legit"], [True, False, True, False, False],
                kinds=["scam", "scam", "hn_family_emergency", "hn_family_emergency", "plain_payment"],
                playbooks=["remote_access", "remote_access", "none", "none", "none"])
    b = fs.by_playbook(res).set_index("playbook")
    assert (int(b.loc["remote_access", "n"]), int(b.loc["remote_access", "hit"])) == (2, 1)
    k = fs.fa_by_kind(res).set_index("session_kind")
    assert (int(k.loc["hn_family_emergency", "n"]), int(k.loc["hn_family_emergency", "fa"])) == (2, 1)
    assert "scam" not in k.index                                   # only legitimate sessions count towards false alarms


def test_missed_lists_only_unalarmed_scams_with_a_gap_only_for_score_misses():
    res = frame(["scam", "scam", "legit"], [False, False, False], playbooks=["screen_share", "remote_access", "none"])
    res["session_id"] = ["a", "b", "c"]
    res["n_pay"] = [1, 0]  + [1]
    res["call_state_available"] = True
    res["usage_access"] = True
    res["week"] = 3
    res["age_band"] = "18-35"
    res["thr"] = 2.0
    res["max_score"] = [1.5, np.nan, 0.0]
    m = fs.missed(res, "t")
    assert list(m.session_id) == ["a", "b"]
    assert m.loc[m.session_id == "a", "gap"].iloc[0] == pytest.approx(0.5)
    assert np.isnan(m.loc[m.session_id == "b", "gap"].iloc[0])


def test_the_report_is_labelled_simulated_and_never_touches_the_sealed_set():
    text = fs.render([1], {1: {"scam_n": 10, "scam_hit": 9, "legit_n": 1000, "legit_fa": 1, "interdicted": 8, "median_lead_min": 5.0}},
                     {"scam_n": 10, "scam_hit": 9, "legit_n": 1000, "legit_fa": 1, "interdicted": 8, "median_lead_min": 5.0},
                     pd.DataFrame({"playbook": ["remote_access"], "n": [10], "hit": [9]}),
                     pd.DataFrame({"session_kind": ["plain_payment"], "n": [1000], "fa": [1]}),
                     fs.missed(frame(["legit"], [False]).assign(session_id="x"), "t"), pd.Series(dtype=int), 1.0)
    assert "Simulated data throughout" in text and "not the sealed held-out run" in text and "No scam was missed" in text
    source = Path(fs.__file__).read_text(encoding="utf-8")
    assert "heldout_events" not in source.replace("placeholder_heldout", "")             # the sealed events file is never opened
    assert '"heldout"' not in source
