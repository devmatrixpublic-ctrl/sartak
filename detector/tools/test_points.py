"""The Python mirror of the display points must agree with the Kotlin cases. Run: pytest detector/tools/test_points.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
import points  # noqa: E402

CASES = json.loads((ROOT / "detector/src/test/resources/golden/points_cases.json").read_text(encoding="utf-8"))


def test_points_match_the_shared_cases():
    for c, want in CASES["points"]:
        assert points.points(c) == want, c


def test_bands_match_the_shared_cases():
    for total, want in CASES["bands"]:
        assert points.band(total) == want, total
