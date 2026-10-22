import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import run_heldout as rh  # noqa: E402


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    (r / "f.txt").write_text("1")
    git(r, "add", "f.txt")
    git(r, "commit", "-q", "-m", "one")
    return r


def commit_more(repo, text="2"):
    (repo / "f.txt").write_text(text)
    git(repo, "commit", "-q", "-am", "next")


# --- freeze guard --------------------------------------------------------------------
def test_refuses_when_the_freeze_tag_does_not_exist(repo):
    with pytest.raises(rh.Refusal, match="has not been frozen"):
        rh.check_freeze(repo)


def test_accepts_head_exactly_at_the_tag(repo):
    git(repo, "tag", "detector-freeze")
    assert len(rh.check_freeze(repo)) == 40


def test_refuses_an_untagged_commit_after_the_tag(repo):
    git(repo, "tag", "detector-freeze")
    commit_more(repo)
    with pytest.raises(rh.Refusal, match="is not at"):
        rh.check_freeze(repo)


def test_refuses_when_tracked_files_are_modified(repo):
    git(repo, "tag", "detector-freeze")
    (repo / "f.txt").write_text("edited after freeze")
    with pytest.raises(rh.Refusal, match="differ"):
        rh.check_freeze(repo)


def test_untracked_files_do_not_block(repo):
    git(repo, "tag", "detector-freeze")
    (repo / "scratch.txt").write_text("x")
    rh.check_freeze(repo)


# --- hash guard ----------------------------------------------------------------------
def make_file(tmp_path, content=b"events"):
    p = tmp_path / "heldout_events.csv"
    p.write_bytes(content)
    return p, hashlib.sha256(content).hexdigest()


def test_hash_must_match_the_expected_file(tmp_path):
    p, digest = make_file(tmp_path)
    exp = tmp_path / "expected.txt"
    exp.write_text(digest + "\n")
    assert rh.check_hash(p, exp) == digest
    exp.write_text("0" * 64)
    with pytest.raises(rh.Refusal, match="does not match expected"):
        rh.check_hash(p, exp)


def test_without_an_expected_file_the_sealed_prefix_and_suffix_are_enforced(tmp_path):
    p, _ = make_file(tmp_path)
    with pytest.raises(rh.Refusal, match="sealed"):
        rh.check_hash(p, tmp_path / "absent.txt")


def test_sealed_prefix_and_suffix_accepts_a_matching_digest(tmp_path, monkeypatch):
    p, digest = make_file(tmp_path)
    monkeypatch.setattr(rh, "SEALED_PREFIX", digest[:8])
    monkeypatch.setattr(rh, "SEALED_SUFFIX", digest[-4:])
    assert rh.check_hash(p, tmp_path / "absent.txt") == digest


def test_sidecar_sha256_file_must_agree(tmp_path):
    p, digest = make_file(tmp_path)
    exp = tmp_path / "expected.txt"
    exp.write_text(digest)
    (tmp_path / "SHA256").write_text("f" * 64 + "  heldout_events.csv\n")
    with pytest.raises(rh.Refusal, match="SHA256 file"):
        rh.check_hash(p, exp)
    (tmp_path / "SHA256").write_text(digest + "  heldout_events.csv\n")
    assert rh.check_hash(p, exp) == digest


def test_missing_heldout_file_is_refused(tmp_path):
    with pytest.raises(rh.Refusal, match="not found"):
        rh.check_hash(tmp_path / "nope.csv")


# --- run once ------------------------------------------------------------------------
def test_refuses_to_run_twice(tmp_path):
    result = tmp_path / "heldout_result.md"
    rh.check_not_run_before(result)
    result.write_text("done")
    with pytest.raises(rh.Refusal, match="run once"):
        rh.check_not_run_before(result)


def test_all_guards_together_in_order(repo, tmp_path):
    p, digest = make_file(tmp_path)
    exp = tmp_path / "expected.txt"
    exp.write_text(digest)
    result = tmp_path / "heldout_result.md"
    with pytest.raises(rh.Refusal, match="has not been frozen"):
        rh.guards(p, repo, result, exp)
    git(repo, "tag", "detector-freeze")
    head, got = rh.guards(p, repo, result, exp)
    assert got == digest and head == subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                                    capture_output=True, text=True).stdout.strip()
    result.write_text("x")
    with pytest.raises(rh.Refusal, match="run once"):
        rh.guards(p, repo, result, exp)


def test_cli_check_mode_reports_a_refusal_without_writing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rh, "RESULT", tmp_path / "heldout_result.md")
    p, _ = make_file(tmp_path)
    assert rh.main(["--heldout", str(p), "--check"]) == 2          # the real repo has no detector-freeze tag yet
    assert "REFUSED" in capsys.readouterr().out
    assert not (tmp_path / "heldout_result.md").exists()


# --- scoring adapter (slow: trains the reference detector, ~90 s) -----------------------
@pytest.mark.skipif(os.environ.get("RUN_SLOW") != "1", reason="set RUN_SLOW=1 to train the detector")
def test_scoring_adapter_on_a_heldout_shaped_file(tmp_path):
    import pandas as pd

    data = rh.ROOT / "data" / "satarksim"
    ev = pd.read_csv(data / "satarksim_events.csv", low_memory=False)
    sess = pd.read_csv(data / "satarksim_sessions.csv")
    val = sess[sess.split == "validation"]
    ids = list(val[val.label == "scam"].session_id.head(5)) + list(val[val.label == "legit"].session_id.head(5))
    held = ev[ev.session_id.isin(ids)].merge(sess[["session_id", "label"]], on="session_id")
    path = tmp_path / "heldout_events.csv"
    held.to_csv(path, index=False)

    res, note = rh.score_cases(path, data, 0.001, None)
    assert len(res) == 10 and set(res.alarm.unique()) <= {True, False}
    assert "NO per-user history supplied" in note and "pooled conformal threshold" in note and "brand-new user" in note
    text = rh.render_result(res, "a" * 40, "b" * 64, note, "now")
    assert "baseline assumption" in text and "cases raised an alarm" in text
    assert all(sid in text for sid in ids)
