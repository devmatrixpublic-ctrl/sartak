"""Release gate: fail if any temporary stub marker is still in the tree.

Markers (implementation plan, "Marking temporary code"): `@SatarkStub` (Kotlin) and
`# SATARK_STUB` (Python). Usage: python ops/ci/check_stubs.py [root]
         exit 0 = clean, 1 = stubs found (listed): the release job uses this.
       python ops/ci/check_stubs.py --new-since <git-ref> [root]
         exit 1 only if the diff against <git-ref> adds more markers than it removes (net increase):
         pull requests use this, so existing stubs do not turn every PR red, replacing a stub with a
         stub is allowed, but nobody can introduce an extra one unnoticed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(r"@SatarkStub\b|#\s*SATARK_STUB\b")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "build", ".gradle"}
SCAN_SUFFIXES = {".py", ".kt", ".kts", ".java", ".xml", ".yaml", ".yml", ".json", ".toml", ".gradle"}
PLANNED = Path(__file__).with_name("planned_stubs.txt")
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


def planned_stubs() -> list[tuple[str, str]]:
    """(path, text) pairs from planned_stubs.txt: markers the plan itself lists. Each entry exempts ONE added marker line."""
    out = []
    if PLANNED.is_file():
        for line in PLANNED.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                cells = [c.strip() for c in line.split("|")]
                if len(cells) >= 2 and cells[0] and cells[1]:
                    out.append((cells[0], cells[1]))
    return out


def changed_markers(root: Path, ref: str) -> tuple[list[tuple[str, str]], int]:
    """(marker lines ADDED, number of marker lines REMOVED) by the diff from `ref` to HEAD (three-dot)."""
    out = subprocess.run(["git", "-C", str(root), "diff", "--unified=0", "--no-color", f"{ref}...HEAD"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git diff against {ref} failed: {out.stderr.strip()}")
    hits, removed, current = [], 0, ""
    planned, used = planned_stubs(), set()
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("--- a/"):
            current = line[6:]
        elif line.startswith(("+++", "---")):
            continue
        elif line[:1] in "+-" and MARKER.search(line):
            if Path(current).suffix not in SCAN_SUFFIXES or Path(current).name in {"check_stubs.py", "test_check_stubs.py"}:
                continue
            if line.startswith("+"):
                text = line[1:].strip()
                allowed = next((i for i, (p, t) in enumerate(planned) if p == current and t in text and i not in used), None)
                if allowed is not None:
                    used.add(allowed)           # a planned stub, exempted once
                else:
                    hits.append((current, text))
            else:
                removed += 1
    return hits, removed


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--new-since":
        root = Path(argv[3] if len(argv) > 3 else ".").resolve()
        try:
            added, removed = changed_markers(root, argv[2])
        except RuntimeError as exc:
            print(f"FAIL {exc}")
            return 1
        for path, line in added:
            print(f"ADDED STUB {path}: {line}")
        net = len(added) - removed
        print(f"{len(added)} stub marker(s) added, {removed} removed (net {net:+d})")
        return 1 if net > 0 else 0
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    hits = find_stubs(root)
    for path, n, line in hits:
        print(f"{path}:{n}: {line}")
    print(f"{len(hits)} stub marker(s) found" if hits else "no stub markers")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
