import importlib.util
import pathlib
import subprocess

spec = importlib.util.spec_from_file_location("check_stubs", pathlib.Path(__file__).with_name("check_stubs.py"))
check_stubs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_stubs)


def test_finds_python_and_kotlin_markers_and_skips_venv(tmp_path):
    (tmp_path / "a.py").write_text("x = 1  # SATARK_STUB\n")
    (tmp_path / "b.kt").write_text("@SatarkStub\nfun f() {}\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "c.py").write_text("# SATARK_STUB\n")
    hits = check_stubs.find_stubs(tmp_path)
    assert sorted(str(p) for p, _, _ in hits) == ["a.py", "b.kt"]


def test_clean_tree_exits_zero_and_dirty_exits_one(tmp_path):
    (tmp_path / "ok.py").write_text("print('hi')\n")
    assert check_stubs.main(["x", str(tmp_path)]) == 0
    (tmp_path / "bad.py").write_text("# SATARK_STUB: remove me\n")
    assert check_stubs.main(["x", str(tmp_path)]) == 1


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def _repo_with_stub(tmp_path):
    (tmp_path / "old.py").write_text("x = 1  # SATARK_STUB (already on main)\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "feature")


def test_workflow_text_that_merely_mentions_the_marker_is_not_a_stub(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: no stubs\nsteps:\n  - name: A PR may not add a stub marker\n")
    assert check_stubs.main(["x", str(tmp_path)]) == 0


def test_new_since_fails_only_on_a_net_increase(tmp_path):
    _repo_with_stub(tmp_path)
    (tmp_path / "ok.py").write_text("print('fine')\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "clean change")
    assert check_stubs.main(["x", "--new-since", "main", str(tmp_path)]) == 0     # pre-existing stub tolerated

    (tmp_path / "new.kt").write_text("@SatarkStub\nfun temp() {}\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "adds a stub")
    assert check_stubs.main(["x", "--new-since", "main", str(tmp_path)]) == 1
    assert check_stubs.main(["x", str(tmp_path)]) == 1                           # release mode: any marker fails


def test_replacing_a_stub_with_a_stub_is_not_a_net_increase(tmp_path):
    _repo_with_stub(tmp_path)
    (tmp_path / "old.py").write_text("x = 1\n")
    (tmp_path / "new.py").write_text("y = 2  # SATARK_STUB (replacement)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "swap")
    assert check_stubs.main(["x", "--new-since", "main", str(tmp_path)]) == 0
    (tmp_path / "extra.py").write_text("z = 3  # SATARK_STUB (one more)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "extra")
    assert check_stubs.main(["x", "--new-since", "main", str(tmp_path)]) == 1


def test_removing_a_stub_is_fine(tmp_path):
    _repo_with_stub(tmp_path)
    (tmp_path / "old.py").write_text("x = 1\n")
    _git(tmp_path, "commit", "-q", "-am", "removed")
    assert check_stubs.main(["x", "--new-since", "main", str(tmp_path)]) == 0


def test_new_since_with_an_unknown_ref_fails_loudly(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "x")
    assert check_stubs.main(["x", "--new-since", "no-such-ref", str(tmp_path)]) == 1
