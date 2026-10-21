"""The checklist is only worth anything if its links are real: every test name and file it cites must exist."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = (Path(__file__).parent / "checklist.md").read_text(encoding="utf-8")


def all_test_names() -> set[str]:
    names: set[str] = set()
    for base in (ROOT / "server" / "tests", ROOT / "ops"):
        for f in base.rglob("test_*.py"):
            names |= set(re.findall(r"^def (test_\w+)", f.read_text(encoding="utf-8"), re.MULTILINE))
    return names


def test_every_test_the_checklist_cites_exists():
    cited = set(re.findall(r"`(?:[\w./]+::)?(test_\w+)`", CHECKLIST))
    assert len(cited) >= 20, "the checklist should cite many tests; did the format change?"
    missing = sorted(cited - all_test_names())
    assert not missing, f"checklist cites tests that do not exist: {missing}"


def test_every_file_the_checklist_cites_exists():
    cited = set(re.findall(r"`((?:ops|server|contracts)/[\w./-]+?\.(?:py|md|sql|txt))`", CHECKLIST))
    assert cited
    missing = sorted(c for c in cited if not (ROOT / c).exists()
                     and c != "contracts/pins.txt")            # deliberately absent, and the checklist says so
    assert not missing, f"checklist cites files that do not exist: {missing}"
    assert not (ROOT / "contracts" / "pins.txt").exists() or "pins.txt" in CHECKLIST


def test_every_row_has_an_explicit_status():
    rows = [l for l in CHECKLIST.splitlines() if l.startswith("| ") and "---" not in l and "Status" not in l]
    assert rows
    bad = [r[:70] for r in rows if not re.search(r"\*\*(Done|Partial|Open|Not done|Tool done|Written|Blocking)", r)]
    assert not bad, f"rows without a status: {bad}"
