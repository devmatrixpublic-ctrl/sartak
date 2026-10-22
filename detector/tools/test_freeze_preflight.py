import importlib.util
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location("fp", Path(__file__).with_name("freeze_preflight.py"))
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

EMULATOR_ONLY = """| 18 | Emulator, API 35 | Detector only | 36/36 |
| 19 | Emulator, API 35 | App pipeline | 36/36 |
| Device | Android emulator. **Not a physical phone.** |"""
ONE_PHONE = EMULATOR_ONLY + "\n| 21 | Physical: Pixel 7, Android 15 | App pipeline | 36/36 |"
TWO_PHONES = ONE_PHONE + "\n| 22 | Physical: Redmi Note 9, Android 11 | App pipeline | 36/36 |"


def test_emulator_runs_and_the_not_a_physical_phone_note_do_not_count():
    assert fp.physical_phone_rows(EMULATOR_ONLY) == []


def test_phone_evidence_needs_two_distinct_physical_devices(tmp_path):
    log = tmp_path / "e2e_log.md"
    for text, expect in ((EMULATOR_ONLY, False), (ONE_PHONE, False), (TWO_PHONES, True)):
        log.write_text(text)
        assert fp.check_phones(log)[0] is expect
    log.write_text(ONE_PHONE + "\n| 22 | Physical: Pixel 7, Android 15 | Detector only | 36/36 |")     # same phone twice is one phone
    assert fp.check_phones(log)[0] is False


def test_a_failing_phone_run_is_not_counted():
    assert fp.physical_phone_rows("| 21 | Physical: Pixel 7 | App pipeline | 33/36 |") == []


def _repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("1")
    g("add", "-A"); g("commit", "-q", "-m", "one")
    return g


def test_clean_tree_check_sees_modified_tracked_files_but_ignores_untracked(tmp_path):
    _repo(tmp_path)
    assert fp.check_clean(tmp_path)[0] is True
    (tmp_path / "untracked.txt").write_text("x")
    assert fp.check_clean(tmp_path)[0] is True
    (tmp_path / "a.txt").write_text("2")
    assert fp.check_clean(tmp_path)[0] is False


def test_tag_check_allows_absent_or_same_commit_and_rejects_a_moved_tag(tmp_path):
    g = _repo(tmp_path)
    assert fp.check_tag("detector-freeze", tmp_path)[0] is True                  # absent
    g("tag", "detector-freeze")
    assert fp.check_tag("detector-freeze", tmp_path)[0] is True                  # at HEAD
    (tmp_path / "a.txt").write_text("2"); g("commit", "-qam", "two")
    assert fp.check_tag("detector-freeze", tmp_path)[0] is False                 # HEAD moved past the tag
