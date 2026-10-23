import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build as b  # noqa: E402


def test_markdown_is_escaped_so_a_report_cannot_inject_script():
    out = b.md_to_html("# Title <script>alert(1)</script>\n\n| a | b |\n|---|---|\n| <img src=x onerror=y> | **2** |\n\n- <b>x</b>\n")
    assert "<script" not in out and "<img" not in out and "<b>x" not in out
    assert "&lt;script&gt;" in out and "<strong>2</strong>" in out and "<table>" in out and "<li>" in out


def test_alert_counts_are_counts_only(tmp_path):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE alerts (id TEXT, device_id TEXT, type TEXT, delivered INT, failure_reason TEXT, review_status TEXT, created_at TEXT)")
    con.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?)", [
        ("a1", "secret-device-1", "alarm", 1, None, "open", "2026-01-01"),
        ("a2", "secret-device-2", "alarm", 1, None, "open", "2026-01-02"),
        ("a3", "secret-device-3", "long_session", 0, "x", "cleared", "2026-01-03")])
    con.commit(); con.close()
    c = b.alert_counts(db)
    assert c["total"] == 3 and {"type": "alarm", "delivered": True, "review_status": "open", "count": 2} in c["rows"]
    assert "secret-device" not in str(c) and "a1" not in str(c)
    assert b.alert_counts(tmp_path / "missing.db") is None and b.alert_counts(None) is None


def test_every_section_and_the_page_are_labelled_simulated():
    page = b.build(None)
    assert "simulated or test data" in page
    assert page.count("simulated data") >= 4
    assert "<script" not in page.lower()  # static: no scripts at all
    assert "http://" not in page and "https://" not in page


EVAL_RESULT = b.ROOT / "ops" / "eval" / "reports" / "eval_result.json"


@pytest.mark.skipif(
    not EVAL_RESULT.is_file(),
    reason="needs ops/eval/reports/eval_result.json, which ops/eval/run_eval.py generates and git ignores "
           "(the evaluation job checks the real numbers)",
)
def test_headline_numbers_come_from_the_eval_result_file():
    page = b.build(None)
    m = re.search(r"Scam recall</td><td>([\d.]+)%", page)
    assert m and 80 < float(m.group(1)) <= 100
