import importlib.util
import pathlib

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
