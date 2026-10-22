"""Record SHA-256 hashes of the local-only benchmark inputs (plan 4.3).

BAF and IEEE-CIS are not redistributable and too large for CI, so they are run on a developer
machine. Run this next to those runs and commit the updated input_hashes.json, so anyone can
confirm a committed report came from the file they have.

  python ops/eval/record_local_hashes.py --baf Base.csv --ieee train_transaction.csv
  python ops/eval/record_local_hashes.py --verify        # re-check files named in the manifest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import ROOT, sha256_file  # noqa: E402

MANIFEST = Path(__file__).with_name("input_hashes.json")
REPORTS = {"baf": "data/satarksim/baf_report.md", "ieee_cis": "data/satarksim/ieee_cis_report.md"}


def load() -> dict:
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"note": "Hashes of local-only benchmark inputs. null = the raw file was not available when this was written.",
            "baf": {"input": None, "sha256": None}, "ieee_cis": {"input": None, "sha256": None}}


def record(manifest: dict, key: str, path: Path) -> None:
    manifest[key] = {"input": path.name, "sha256": sha256_file(path), "report": REPORTS[key],
                     "report_sha256": sha256_file(ROOT / REPORTS[key])}


def verify(manifest: dict, files: dict[str, Path]) -> list[str]:
    problems = []
    for key, path in files.items():
        entry = manifest.get(key, {})
        if not entry.get("sha256"):
            problems.append(f"{key}: no hash recorded")
        elif sha256_file(path) != entry["sha256"]:
            problems.append(f"{key}: {path.name} does not match the recorded hash")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baf", type=Path)
    ap.add_argument("--ieee", type=Path)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    manifest = load()
    if a.verify:
        files = {k: p for k, p in (("baf", a.baf), ("ieee_cis", a.ieee)) if p}
        problems = verify(manifest, files)
        print("\n".join(problems) or "hashes match")
        return 1 if problems else 0
    if a.baf:
        record(manifest, "baf", a.baf)
    if a.ieee:
        record(manifest, "ieee_cis", a.ieee)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
