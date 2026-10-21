"""Release gate: fail if any temporary stub marker is still in the tree.

Markers (implementation plan, "Marking temporary code"): `@SatarkStub` (Kotlin) and
`# SATARK_STUB` (Python). Usage: python ops/ci/check_stubs.py [root]
Exit 0 = clean, 1 = stubs found (listed), so the release job goes red.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MARKER = re.compile(r"@SatarkStub\b|#\s*SATARK_STUB\b")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "build", ".gradle"}
SCAN_SUFFIXES = {".py", ".kt", ".kts", ".java", ".xml", ".yaml", ".yml", ".json", ".toml", ".gradle"}
SELF_FILES = {Path(__file__).resolve(), Path(__file__).with_name("test_check_stubs.py").resolve()}


def find_stubs(root: Path) -> list[tuple[Path, int, str]]:
    hits = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.suffix not in SCAN_SUFFIXES or path.resolve() in SELF_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if MARKER.search(line):
                hits.append((path.relative_to(root), n, line.strip()))
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    hits = find_stubs(root)
    for path, n, line in hits:
        print(f"{path}:{n}: {line}")
    print(f"{len(hits)} stub marker(s) found" if hits else "no stub markers")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
