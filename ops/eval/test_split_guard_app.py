import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

import split_guard_app as sg  # noqa: E402

MIN = 60


def frame(rows):
    base = dict(session_id="S", event_type="PAYMENT_ATTEMPT", payee_id="P", payee_is_new=False, amount_inr=0.0)
    return pd.DataFrame([{**base, **r} for r in rows])


def amounts(rows):
    return [float(x) for x in sg.apply_guard(frame(rows)).amount_inr]


# These cases are the same as the Kotlin ones in app/src/test/.../PaymentPolicyTest.kt: the two copies must agree.

def test_three_small_payments_to_a_new_payee_become_one_running_total():
    out = sg.apply_guard(frame([dict(t_sec=0, amount_inr=1000, payee_is_new=True),
                                dict(t_sec=3 * MIN, amount_inr=1000), dict(t_sec=6 * MIN, amount_inr=1500)]))
    assert list(out.amount_inr) == [1000, 2000, 3500]
    assert list(out.payee_is_new)[1:] == [True, True]


def test_a_retry_of_the_same_payment_is_not_counted_twice():
    assert amounts([dict(t_sec=0, amount_inr=1000, payee_is_new=True), dict(t_sec=3 * MIN, amount_inr=1000),
                    dict(t_sec=3 * MIN + 20, amount_inr=1000)]) == [1000, 2000, 2000]


def test_a_known_payee_or_one_past_the_hour_is_left_alone():
    assert amounts([dict(t_sec=0, payee_id="K", amount_inr=500), dict(t_sec=2 * MIN, payee_id="K", amount_inr=500)]) == [500, 500]
    out = sg.apply_guard(frame([dict(t_sec=0, amount_inr=1000, payee_is_new=True), dict(t_sec=61 * MIN, amount_inr=1000)]))
    assert list(out.amount_inr) == [1000, 1000] and list(out.payee_is_new) == [True, False]


def test_different_payees_are_kept_apart():
    assert amounts([dict(t_sec=0, payee_id="A", amount_inr=1000, payee_is_new=True),
                    dict(t_sec=MIN, payee_id="B", amount_inr=700, payee_is_new=True),
                    dict(t_sec=3 * MIN, payee_id="A", amount_inr=1000), dict(t_sec=4 * MIN, payee_id="B", amount_inr=700)]) == [1000, 700, 2000, 1400]


def test_sessions_do_not_share_a_running_total():
    rows = [dict(session_id="S1", t_sec=0, amount_inr=1000, payee_is_new=True), dict(session_id="S2", t_sec=MIN, amount_inr=1000)]
    assert amounts(rows) == [1000, 1000]


def test_other_events_and_missing_amounts_pass_through():
    df = pd.DataFrame([dict(session_id="S", event_type="APP_INSTALL", t_sec=0, payee_id=None, payee_is_new=None, amount_inr=float("nan")),
                       dict(session_id="S", event_type="PAYMENT_ATTEMPT", t_sec=5, payee_id="P", payee_is_new=True, amount_inr=float("nan"))])
    out = sg.apply_guard(df)
    assert out.amount_inr.isna().all()


def test_sessions_changed_ignores_rows_with_no_amount():
    original = pd.DataFrame([dict(session_id="S", t_sec=0, amount_inr=float("nan")), dict(session_id="S", t_sec=1, amount_inr=5.0),
                             dict(session_id="T", t_sec=0, amount_inr=9.0)])
    guarded = original.copy()
    guarded.loc[1, "amount_inr"] = 12.0
    assert sg.sessions_changed(original, guarded) == 1


def test_combine_alarms_if_either_copy_does_and_keeps_the_earlier_time():
    main = pd.DataFrame(dict(session_id=["a", "b", "c"], alarm=[False, True, False], alarm_t=[float("nan"), 100.0, float("nan")],
                             mechanism=["none", "payment_score", "none"], first_pay_t=[50.0, 50.0, 50.0]))
    guard = pd.DataFrame(dict(session_id=["a", "b", "c"], alarm=[True, True, False], alarm_t=[40.0, 80.0, float("nan")],
                              mechanism=["payment_score"] * 3))
    out = sg.combine(main, guard).set_index("session_id")
    assert list(out.alarm) == [True, True, False]
    assert out.loc["a", "alarm_t"] == 40.0 and out.loc["b", "alarm_t"] == 80.0
    assert bool(out.loc["a", "interdicted"]) is True   # 40 is before the first payment at 50
