import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

pd = pytest.importorskip("pandas")

import alert_budget as ab  # noqa: E402


def ev(sid, uid, etype, t, **kw):
    base = dict(session_id=sid, user_id=uid, event_type=etype, t_sec=t, caller_known=None, payee_is_new=None, amount_inr=None)
    base.update(kw)
    return base


def test_wilson_interval_brackets_the_rate_and_handles_zero():
    lo, hi = ab.wilson(7, 9887)
    assert lo < 7 / 9887 < hi
    assert ab.wilson(0, 100)[0] == 0.0 and ab.wilson(0, 0) == (0.0, 1.0)


def test_expected_alerts_is_rate_times_payments_times_months():
    assert ab.expected_alerts(0.001, 25, 3) == pytest.approx(0.075)


def test_share_with_one_or_more_is_poisson():
    assert ab.share_with_at_least_one(np.array([0.0])) == 0.0
    assert ab.share_with_at_least_one(np.array([1.0])) == pytest.approx(1 - np.exp(-1))
    assert ab.share_with_at_least_one(np.array([])) == 0.0


def test_nudge_needs_an_unknown_call_active_at_a_new_payee_payment():
    rows = [
        ev("A", "u", "CALL_START", 0, caller_known=False), ev("A", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=500),
        ev("B", "u", "CALL_START", 0, caller_known=True), ev("B", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=500),
        ev("C", "u", "CALL_START", 0, caller_known=False), ev("C", "u", "CALL_END", 30),
        ev("C", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=500),
        ev("D", "u", "CALL_START", 0, caller_known=False), ev("D", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=False, amount_inr=500),
    ]
    assert ab.nudge_sessions(pd.DataFrame(rows)) == {"A"}


def test_tighter_nudge_rule_drops_small_payments():
    rows = [
        ev("A", "u", "CALL_START", 0, caller_known=False), ev("A", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=150),
        ev("B", "u", "CALL_START", 0, caller_known=False), ev("B", "u", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=900),
    ]
    df = pd.DataFrame(rows)
    assert ab.nudge_sessions(df) == {"A", "B"}
    assert ab.nudge_sessions(df, {"u": 100.0}, 2.0) == {"B"}


def test_compute_reports_rates_projection_and_budget_verdicts():
    n = 1000
    res = pd.DataFrame({
        "session_id": [f"S{i}" for i in range(n)], "split": "validation", "label": "legit",
        "alarm": [i < 1 for i in range(n)],  # 1 false alarm in 1000 payments
    })
    users = pd.DataFrame({"user_id": ["u1", "u2"], "split": "validation", "payments_per_month": [10.0, 80.0], "hist_median_inr": [100.0, 100.0]})
    events = pd.DataFrame([ev("S5", "u1", "CALL_START", 0, caller_known=False),
                           ev("S5", "u1", "PAYMENT_ATTEMPT", 60, payee_is_new=True, amount_inr=500)])
    m = ab.compute(res, users, events)
    assert m["pause"]["false_alarms"] == 1 and m["pause"]["rate"] == pytest.approx(0.001)
    # mean over the two users: 0.001 * (10 + 80)/2 * 3 months
    assert m["pause"]["mean_per_user"] == pytest.approx(0.001 * 45 * 3)
    assert m["pause"]["within_budget_mean"] and m["pause"]["within_budget_worst_tier"]
    assert m["nudge"]["sessions"] == 1
    assert m["legit_with_unknown_call_share"] == pytest.approx(1 / n)


def test_a_busy_user_over_budget_is_called_out():
    n = 100
    res = pd.DataFrame({"session_id": [f"S{i}" for i in range(n)], "split": "validation", "label": "legit", "alarm": [i < 10 for i in range(n)]})
    users = pd.DataFrame({"user_id": ["u"], "split": "validation", "payments_per_month": [80.0], "hist_median_inr": [100.0]})
    m = ab.compute(res, users, pd.DataFrame(columns=["session_id", "user_id", "event_type", "t_sec", "caller_known", "payee_is_new", "amount_inr"]))
    assert not m["pause"]["within_budget_mean"]
    assert "OVER" in ab.render(m, 0.0008)
