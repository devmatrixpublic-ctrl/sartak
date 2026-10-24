import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import split_guard as sg  # noqa: E402


def events(rows):
    """rows: (session, t, type, payee, amount)"""
    return pd.DataFrame([{"session_id": s, "t_sec": t, "ts_abs": 1000 + t, "event_type": et, "payee_id": p, "amount_inr": a}
                         for s, t, et, p, a in rows])


PAY = "PAYMENT_ATTEMPT"


def test_k_equal_one_changes_nothing():
    ev = events([("S1", 0, PAY, "P", 1000.0)])
    assert sg.split_payments(ev, 1, 30, {"S1"}).equals(ev)


def test_splitting_keeps_the_total_the_payee_and_spaces_the_pieces():
    ev = events([("S1", 100, "CALL_START", None, None), ("S1", 200, PAY, "P", 1000.0), ("S2", 200, PAY, "Q", 500.0)])
    out = sg.split_payments(ev, 4, 30, {"S1"})
    p = out[(out.session_id == "S1") & (out.event_type == PAY)]
    assert len(p) == 4 and p.amount_inr.sum() == pytest.approx(1000.0) and set(p.payee_id) == {"P"}
    assert list(p.t_sec) == [200, 230, 260, 290]
    assert len(out[out.event_type == "CALL_START"]) == 1                                   # other events untouched
    other = out[out.session_id == "S2"]
    assert len(other) == 1 and other.amount_inr.iloc[0] == 500.0                           # sessions not attacked are left alone


def test_guard_sums_per_payee_inside_the_window_only():
    ev = events([("S1", 0, PAY, "P", 100.0), ("S1", 30, PAY, "P", 100.0), ("S1", 40, PAY, "Q", 50.0),
                 ("S1", 5000, PAY, "P", 100.0)])
    g = sg.apply_guard(ev, 1800).set_index("t_sec").amount_inr
    assert g[0] == 100.0 and g[30] == 200.0                                                # a running total to the same payee
    assert g[40] == 50.0                                                                   # another payee is separate
    assert g[5000] == 100.0                                                                # outside the window: the history has expired


def test_guard_never_touches_other_event_types_or_other_sessions():
    ev = events([("S1", 0, "CALL_START", None, np.nan), ("S1", 10, PAY, "P", 100.0), ("S2", 11, PAY, "P", 100.0)])
    g = sg.apply_guard(ev, 1800)
    assert g[g.event_type == "CALL_START"].amount_inr.isna().all()
    assert sorted(g[g.event_type == PAY].amount_inr) == [100.0, 100.0]                    # S2 does not inherit S1's history


def test_guard_makes_a_split_payment_look_like_the_original_at_its_last_piece():
    whole = events([("S1", 0, PAY, "P", 1000.0)])
    split = sg.split_payments(whole, 5, 30, {"S1"})
    g = sg.apply_guard(split, 1800)
    assert g[g.event_type == PAY].amount_inr.max() == pytest.approx(1000.0)               # the detector sees the real size again


def test_exposure_counts_only_what_was_sent_before_the_alarm():
    ev = events([("S1", 0, PAY, "P", 100.0), ("S1", 30, PAY, "P", 100.0), ("S1", 60, PAY, "P", 100.0),
                 ("S2", 0, PAY, "P", 100.0)])
    dec = pd.DataFrame({"session_id": ["S1", "S2"], "alarm_t": [60.0, np.nan]})
    e = sg.exposure(ev, dec).set_index("session_id")
    assert e.loc["S1", "total"] == 300.0 and e.loc["S1", "sent"] == 200.0                  # the attempt the alarm fires on is held
    assert e.loc["S2", "sent"] == 100.0                                                    # never alarmed: everything went out


def test_alarm_on_the_first_attempt_protects_everything():
    ev = events([("S1", 0, PAY, "P", 100.0), ("S1", 30, PAY, "P", 100.0)])
    e = sg.exposure(ev, pd.DataFrame({"session_id": ["S1"], "alarm_t": [0.0]}))
    assert e.sent.iloc[0] == 0.0


def test_measure_counts_evasion_only_among_scams_caught_unattacked():
    dec = pd.DataFrame({"session_id": ["a", "b", "c"], "label": ["scam"] * 3, "alarm": [True, False, False],
                        "interdicted": [True, False, False], "alarm_t": [0.0, np.nan, np.nan], "mechanism": ["payment_score", "none", "none"]})
    ev = events([("a", 0, PAY, "P", 10.0), ("b", 0, PAY, "P", 10.0), ("c", 0, PAY, "P", 10.0)])
    m = sg.measure(dec, ev, baseline_caught={"a", "b"}, payscore_only={"a", "b"})
    assert (m["n"], m["hit"], m["evaded"], m["baseline_caught"]) == (3, 1, 1, 2)         # b was caught before and is evaded now; c never was
    assert m["total"] == 30.0 and m["sent"] == 20.0 and (m["ps_n"], m["ps_hit"]) == (2, 1)


def test_the_report_states_what_it_is_and_what_it_cannot_show():
    rows = {(k, g): {"n": 10, "hit": 9, "interdicted": 8, "total": 100.0, "sent": 10.0, "evaded": 0, "baseline_caught": 9, "ps_n": 4, "ps_hit": 3}
            for k in sg.ROWS for g in (False, True)}
    text = sg.render(rows, {"guard off (shipped)": (7, 9887), "guard on, shipped thresholds": (7, 9887), "guard on, thresholds re-calibrated": (7, 9887)}, (538, 578), 1800, 30)
    assert "Simulated data" in text and "not the sealed held-out set" in text.replace("Not the", "not the")
    assert "mule" in text and "needs a new freeze" in text


def test_adaptive_split_cuts_each_payment_to_pieces_no_larger_than_the_users_median():
    ev = events([("S1", 100, PAY, "P", 10_000.0), ("S1", 500, PAY, "Q", 300.0), ("S2", 100, PAY, "R", 10_000.0)])
    ev["user_id"] = ["U1", "U1", "U2"]
    users = pd.DataFrame({"user_id": ["U1", "U2"], "hist_median_inr": [1000.0, 1000.0]})
    out = sg.split_below_baseline(ev, users, 30, {"S1"})
    big = out[(out.session_id == "S1") & (out.payee_id == "P")]
    assert len(big) == 10 and big.amount_inr.max() <= 1000.0 and big.amount_inr.sum() == pytest.approx(10_000.0)
    assert list(big.t_sec)[:3] == [100, 130, 160]
    small = out[(out.session_id == "S1") & (out.payee_id == "Q")]
    assert len(small) == 1 and small.amount_inr.iloc[0] == 300.0                       # already under the median: left alone
    assert len(out[out.session_id == "S2"]) == 1                                       # other sessions are not attacked


def test_adaptive_split_is_capped_so_a_huge_payment_is_not_exploded_into_thousands():
    ev = events([("S1", 0, PAY, "P", 1_000_000.0)])
    ev["user_id"] = "U1"
    users = pd.DataFrame({"user_id": ["U1"], "hist_median_inr": [100.0]})
    out = sg.split_below_baseline(ev, users, 30, {"S1"}, max_pieces=20)
    assert len(out) == 20 and out.amount_inr.sum() == pytest.approx(1_000_000.0)


def _rows(adaptive_interdicted=5, guard_interdicted=5):
    rows = {(k, g): {"n": 10, "hit": 10, "interdicted": 8, "total": 100.0, "sent": 1.0, "evaded": 0, "baseline_caught": 9, "ps_n": 4, "ps_hit": 4}
            for k in sg.ROWS for g in (False, True)}
    rows[(sg.ADAPTIVE, False)] = dict(rows[(sg.ADAPTIVE, False)], interdicted=adaptive_interdicted)
    rows[(sg.ADAPTIVE, True)] = dict(rows[(sg.ADAPTIVE, True)], interdicted=guard_interdicted)
    return rows


def test_the_reading_is_computed_from_the_numbers_not_written_in_advance():
    fa = {"guard off (shipped)": (7, 9887), "guard on, shipped thresholds": (7, 9887)}
    text = "\n".join(sg.reading(_rows(5, 5), fa))
    assert "did not evade" in text and "80.0% unattacked to 50.0%" in text and "unchanged" in text
    worse = "\n".join(sg.reading(_rows(5, 5), fa))
    better = "\n".join(sg.reading(_rows(5, 9), fa))
    assert "changed by 4 sessions" in better and worse != better


def test_a_split_that_does_hide_scams_is_reported_as_evasion():
    rows = _rows()
    rows[(5, False)] = dict(rows[(5, False)], hit=6, evaded=3)
    text = "\n".join(sg.reading(rows, {"guard off (shipped)": (7, 9887), "guard on, shipped thresholds": (7, 9887)}))
    assert "worst case is 6/10" in text and "3 scams caught unattacked were missed" in text


def test_rerender_rebuilds_the_same_report_from_the_saved_json(tmp_path):
    import json
    rows, fa = _rows(), {"guard off (shipped)": (7, 9887), "guard on, shipped thresholds": (7, 9887), "guard on, thresholds re-calibrated": (7, 9887)}
    saved = {"window_s": 1800, "gap_s": 30, "rows": {f"k={k},guard={g}": v for (k, g), v in rows.items()},
             "false_alarms": {k: list(v) for k, v in fa.items()}, "recalibrated_recall": [550, 578]}
    (tmp_path / "r.json").write_text(json.dumps(saved))
    sg.rerender(tmp_path / "r.json", tmp_path / "r.md")
    assert (tmp_path / "r.md").read_text(encoding="utf-8") == sg.render(rows, fa, (550, 578), 1800, 30)
