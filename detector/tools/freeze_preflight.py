#!/usr/bin/env python3
"""Pre-flight for the `detector-freeze` tag (plan 2.7). It never tags anything; it prints the command only if every check passes.

Why it exists: M4's held-out runner refuses to run unless HEAD is exactly the tagged commit with no tracked changes, and the held-out
set may be run ONCE. Tagging a commit that is unpushed, stale, red, or not yet proven on the phones wastes that one run.

Checks:
  1. no modified tracked files
  2. HEAD is on origin/main (pushed and merged)
  3. the tag does not exist yet, or already points at HEAD
  4. detector/src/main/resources/model.json equals a fresh export (the tree stays unchanged after re-exporting)
  5. the evaluation gate passes (recall >= 93%, false alarms <= 0.1%, point estimates) and equals detector_report.md
  6. the Kotlin detector tests pass (36 vectors, parity, fuzz)           [skip with --skip-gradle]
  7. app/e2e_log.md records the 36 vectors passing on at least TWO PHYSICAL phones (see the convention below)

Convention for check 7: in app/e2e_log.md, one table row per physical phone, containing the word "physical" and "36/36" and not the
word "emulator", for example
  | 21 | Physical: Pixel 7, Android 15 | App pipeline (instrumented) | 36/36 |
  | 22 | Physical: Redmi Note 9, Android 11 | App pipeline (instrumented) | 36/36 |

Usage (repo root): python detector/tools/freeze_preflight.py [--skip-gradle] [--tag detector-freeze]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def git(*args, cwd=ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def check_clean(cwd=ROOT) -> tuple[bool, str]:
    out = git("status", "--porcelain", "--untracked-files=no", cwd=cwd).stdout.strip()
    return (not out, "no modified tracked files" if not out else "modified tracked files:\n    " + out.replace("\n", "\n    "))


def check_on_main(cwd=ROOT, main_ref="origin/main") -> tuple[bool, str]:
    git("fetch", "-q", "origin", "main", cwd=cwd)
    ok = git("merge-base", "--is-ancestor", "HEAD", main_ref, cwd=cwd).returncode == 0
    return ok, ("HEAD is on origin/main" if ok else f"HEAD is not on {main_ref}: push and merge it first")


def check_tag(tag: str, cwd=ROOT) -> tuple[bool, str]:
    tagged = git("rev-list", "-n", "1", tag, cwd=cwd)
    if tagged.returncode != 0:
        return True, f"tag {tag} does not exist yet"
    head = git("rev-parse", "HEAD", cwd=cwd).stdout.strip()
    ok = tagged.stdout.strip() == head
    return ok, (f"tag {tag} already points at HEAD" if ok else f"tag {tag} exists on a DIFFERENT commit; do not move a freeze tag casually")


def physical_phone_rows(log_text: str) -> list[str]:
    rows = []
    for line in log_text.splitlines():
        low = line.lower()
        if line.lstrip().startswith("|") and "physical" in low and "36/36" in line and "emulator" not in low:
            rows.append(line.strip())
    return rows


def check_phones(log: Path | None = None) -> tuple[bool, str]:
    log = log or ROOT / "app" / "e2e_log.md"
    if not log.is_file():
        return False, f"{log.name} not found"
    rows = physical_phone_rows(log.read_text(encoding="utf-8"))
    devices = {re.sub(r"\s+", " ", r.split("|")[2].strip().lower()) for r in rows if r.count("|") >= 4}
    ok = len(devices) >= 2
    return ok, (f"{len(devices)} physical phone(s) recorded at 36/36" if ok
                else f"need 36/36 on at least 2 physical phones in {log.name}; found {len(devices)} (convention in this script's docstring)")


def run(cmd: list[str], cwd=ROOT) -> tuple[bool, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode == 0:
        return True, "passed"
    tail = (p.stdout + p.stderr).strip().splitlines()
    return False, f"failed (exit {p.returncode}): {tail[-1] if tail else ''}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-gradle", action="store_true")
    ap.add_argument("--tag", default="detector-freeze")
    a = ap.parse_args(argv)

    results: list[tuple[str, bool, str]] = []

    def add(name, res):
        ok, msg = res
        results.append((name, ok, msg))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {msg}", flush=True)

    add("1. clean tree", check_clean())
    add("2. HEAD on origin/main", check_on_main())
    add("3. tag state", check_tag(a.tag))
    ok, msg = run([sys.executable, "detector/tools/export_model.py"])
    drift = git("status", "--porcelain", "--untracked-files=no").stdout.strip()
    add("4. model.json is current", (ok and not drift, "re-export left the tree unchanged" if ok and not drift else
                                     f"re-export failed or changed files (commit them first): {msg or drift[:200]}"))
    add("5. evaluation gate passes and matches the report", run([sys.executable, "ops/eval/run_eval.py"]))
    if a.skip_gradle:
        results.append(("6. detector tests", True, "skipped"))
        print("[SKIP] 6. detector tests: skipped by --skip-gradle")
    else:
        add("6. detector tests", run(["gradle", "--no-daemon", "-q", "--max-workers=1", "test"], cwd=ROOT / "detector"))
    add("7. 36/36 on two physical phones", check_phones())

    failed = [r for r in results if not r[1]]
    print()
    if failed:
        print(f"NOT READY to freeze: {len(failed)} check(s) failed. Do not tag.")
        return 1
    sha = git("rev-parse", "HEAD").stdout.strip()
    print(f"READY. After the team signs off, tag this exact commit ({sha[:7]}):\n"
          f"  git tag -a {a.tag} -m 'Detector frozen for the one-time held-out run' {sha}\n  git push origin {a.tag}\n"
          "Then M4 runs `python ops/heldout/run_heldout.py` from a checkout of that tag, once. Any later detector change needs a new freeze.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
