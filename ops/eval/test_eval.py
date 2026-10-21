import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pd = pytest.importorskip("pandas")
pytest.importorskip("scipy")

import record_local_hashes as rlh  # noqa: E402
import run_eval as ev  # noqa: E402


def frame(scam_alarms, scam_total, legit_alarms, legit_total):
    rows = []
    for i in range(scam_total):
        rows.append(dict(split="validation", label="scam", alarm=i < scam_alarms, interdicted=i < scam_alarms,
                         lead_min=10.0 if i < scam_alarms else float("nan"), naive=i % 2 == 0))
    for i in range(legit_total):
        rows.append(dict(split="validation", label="legit", alarm=i < legit_alarms, interdicted=False,
                         lead_min=float("nan"), naive=False))
    rows.append(dict(split="train", label="legit", alarm=True, interdicted=False, lead_min=float("nan"), naive=True))
    return pd.DataFrame(rows)


def test_headline_counts_only_the_validation_split():
    h = ev.headline(frame(94, 100, 1, 2000))
    assert (h["scam_alarmed"], h["scam_sessions"]) == (94, 100)
    assert (h["legit_false_alarms"], h["legit_sessions"]) == (1, 2000)      # the train-split alarm is ignored
    assert h["recall"] == 0.94 and h["false_alarm_rate"] == 0.0005


def test_gate_passes_when_both_targets_are_met_at_the_boundary():
    h = ev.headline(frame(93, 100, 2, 2000))        # recall exactly 93%, false alarms exactly 0.1%
    assert ev.gate(h) == []


@pytest.mark.parametrize("alarmed,fa,expect", [
    (92, 0, "scam recall"),
    (100, 3, "false-alarm rate"),
])
def test_gate_fails_on_either_target(alarmed, fa, expect):
    failures = ev.gate(ev.headline(frame(alarmed, 100, fa, 2000)))
    assert len(failures) == 1 and expect in failures[0]


def test_gate_reports_both_failures():
    assert len(ev.gate(ev.headline(frame(50, 100, 100, 2000)))) == 2


def test_clopper_pearson_known_values():
    lo, hi = ev.clopper_pearson(0, 100)
    assert lo == 0.0 and 0.03 < hi < 0.04               # rule of three: ~3.6%
    lo, hi = ev.clopper_pearson(100, 100)
    assert hi == 1.0 and 0.96 < lo < 0.97
    lo, hi = ev.clopper_pearson(540, 578)               # M2's published interval is 91.1% - 95.3%
    assert round(lo, 3) == 0.911 and round(hi, 3) == 0.953


def test_shipped_report_headline_is_parseable():
    got = ev.parse_shipped_report(ev.SHIPPED_REPORT)
    assert got == {"scam_alarmed": 540, "scam_sessions": 578, "legit_false_alarms": 11, "legit_sessions": 9887}


def test_unparseable_report_is_an_error(tmp_path):
    bad = tmp_path / "r.md"
    bad.write_text("# nothing here")
    with pytest.raises(ValueError):
        ev.parse_shipped_report(bad)


def test_report_states_failure_and_mismatch_plainly():
    h = ev.headline(frame(50, 100, 100, 2000))
    text = ev.render_report(h, ev.gate(h), False, {"scam_alarmed": 1, "scam_sessions": 2,
                                                  "legit_false_alarms": 3, "legit_sessions": 4}, {"a.csv": "ab"}, 0.001)
    assert "Gate: FAIL" in text and "NO" in text and "`a.csv`: `ab`" in text


def test_input_hashes_cover_the_simulation_data_and_are_stable():
    a = ev.input_hashes(ev.ROOT / "data" / "satarksim")
    assert "data/satarksim/satarksim_sessions.csv" in a and "detector/reference/satark_detector.py" in a
    assert a == ev.input_hashes(ev.ROOT / "data" / "satarksim")
    assert all(len(v) == 64 for v in a.values())


def test_local_hash_manifest_roundtrip_and_tamper_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(rlh, "MANIFEST", tmp_path / "m.json")
    raw = tmp_path / "Base.csv"
    raw.write_text("a,b\n1,2\n")
    manifest = rlh.load()
    assert manifest["baf"]["sha256"] is None
    rlh.record(manifest, "baf", raw)
    assert rlh.verify(manifest, {"baf": raw}) == []
    raw.write_text("a,b\n1,3\n")
    assert "does not match" in rlh.verify(manifest, {"baf": raw})[0]
    assert "no hash recorded" in rlh.verify(manifest, {"ieee_cis": raw})[0]
    json.dumps(manifest)
