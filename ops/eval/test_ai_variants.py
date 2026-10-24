import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

import ai_variants as av  # noqa: E402

RANGES = {"family": (50, 300), "family_high": (130, 500), "arrest": (3000, 26000), "remote": (70, 350), "apk": (160, 830), "legit_tail": (14, 170)}
EVENT_TYPES = {"CALL_START", "CALL_END", "VIDEO_SESSION_START", "VIDEO_SESSION_END", "APP_INSTALL", "APP_FOREGROUND", "NEW_PAYEE", "PAYMENT_ATTEMPT"}


def test_every_scenario_builds_in_every_age_band():
    ev, users, sess = av.build(3, 161.0, 100.0, RANGES)
    assert len(sess) == len(av.SCENARIOS) * len(av.BANDS) * 3
    assert set(sess.age_band) == set(av.BANDS)
    assert set(ev.event_type) <= EVENT_TYPES
    assert list(ev.columns) == av.COLUMNS
    assert (ev.t_sec >= 0).all()
    assert set(sess.session_id) == set(ev.session_id) == set(users.user_id.str.replace("VU", "V"))


def test_building_is_deterministic():
    a = av.build(2, 161.0, 100.0, RANGES, seed=7)[0]
    b = av.build(2, 161.0, 100.0, RANGES, seed=7)[0]
    assert a.equals(b)
    assert not a.equals(av.build(2, 161.0, 100.0, RANGES, seed=8)[0])


def test_scams_are_expected_to_alarm_and_look_alikes_are_not():
    _, _, sess = av.build(1, 161.0, 100.0, RANGES)
    assert sess[sess.group == "scam"].expect_alarm.all()
    assert not sess[sess.group == "control"].expect_alarm.any()
    assert (sess.group == "scam").sum() == 7 * 3 and (sess.group == "control").sum() == 5 * 3


def test_scam_payments_are_large_and_genuine_small_ones_are_small():
    ev, _, sess = av.build(20, 100.0, 50.0, RANGES)
    pays = ev[ev.event_type == "PAYMENT_ATTEMPT"].merge(sess, on="session_id")
    arrest = pays[pays.scenario == "Digital arrest on a video call"].amount_inr
    small = pays[pays.scenario == "Genuine bank-support call, small payment"].amount_inr
    assert arrest.min() >= 100.0 * RANGES["arrest"][0] * 0.999
    assert small.max() <= 100.0 * 2.001


def test_split_scenario_makes_three_payments_to_one_payee():
    ev, _, sess = av.build(2, 100.0, 50.0, RANGES)
    sid = sess[sess.scenario == "Payment split into three"].session_id.iloc[0]
    p = ev[(ev.session_id == sid) & (ev.event_type == "PAYMENT_ATTEMPT")]
    assert len(p) == 3 and p.payee_id.nunique() == 1


def test_summarise_counts_and_gives_an_interval():
    out = pd.DataFrame({
        "scenario": ["x"] * 4, "group": "scam", "expect_alarm": True, "age_band": ["18-35", "18-35", "60+", "60+"],
        "alarm": [True, True, False, False], "mechanism": ["payment_score", "payment_score", "none", "none"], "interdicted": [True, True, False, False],
    })
    r = av.summarise(out)[0]
    assert (r["alarmed"], r["n"]) == (2, 4) and r["by_band"]["60+"] == 0.0
    assert r["ci95"][0] < 0.5 < r["ci95"][1]


@pytest.mark.skipif(os.environ.get("SATARK_SLOW") != "1", reason="fits the detector on 53,000 sessions (about 80 s); set SATARK_SLOW=1")
def test_end_to_end_on_the_real_simulator():
    data = av.ROOT / "data" / "satarksim"
    if not data.exists():
        pytest.skip("no simulator data")
    out, _ = av.run(data, 0.0008, 10)
    rows = {r["scenario"]: r for r in av.summarise(out)}
    assert rows["Fake KYC app"]["rate"] >= 0.95 and rows["Text-led, no call"]["rate"] >= 0.95
    controls = [r for r in rows.values() if r["group"] == "control"]
    assert sum(r["alarmed"] for r in controls) / sum(r["n"] for r in controls) <= 0.02
