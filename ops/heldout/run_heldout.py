"""One-time held-out run (plan 4.6).

Refuses to run unless ALL of these hold:
  1. the git tag `detector-freeze` exists and HEAD is exactly that commit, with no tracked changes;
  2. the held-out events file hashes (SHA-256) to the sealed value;
  3. ops/heldout/heldout_result.md does not exist yet (the run happens once; the result is committed once).

Then it trains the reference detector on SatarkSim exactly as the evaluation pipeline does, scores every
held-out case, and writes heldout_result.md (decision per case + tag + hash).

Sealed hash: the plan gives it as 3382c295...a475 (truncated). Until the full value is written to
ops/heldout/expected_sha256.txt we pin that prefix and suffix, and we also require agreement with the
`SHA256` file that ships beside the data if there is one.

Usage (repo root):
  python ops/heldout/run_heldout.py --check                       # run every guard, change nothing
  python ops/heldout/run_heldout.py --heldout data/heldout/heldout_events.csv
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
TAG = "detector-freeze"
SEALED_PREFIX, SEALED_SUFFIX = "3382c295", "a475"
EXPECTED_FILE = HERE / "expected_sha256.txt"
RESULT = HERE / "heldout_result.md"
DEFAULT_HELDOUT = ROOT / "data" / "satarksim" / "heldout" / "heldout_events.csv"


class Refusal(Exception):
    """A guard failed. The message says exactly which one."""


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed: {out.stderr.strip() or 'no output'}")
    return out.stdout.strip()


def check_freeze(repo: Path = ROOT, tag: str = TAG) -> str:
    try:
        tag_commit = _git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    except Refusal:
        raise Refusal(f"tag '{tag}' does not exist: the detector has not been frozen")
    head = _git(repo, "rev-parse", "HEAD")
    if head != tag_commit:
        raise Refusal(f"HEAD ({head[:8]}) is not at '{tag}' ({tag_commit[:8]}): check out the frozen commit")
    dirty = [l for l in _git(repo, "status", "--porcelain", "--untracked-files=no").splitlines() if l.strip()]
    if dirty:
        raise Refusal(f"tracked files differ from '{tag}': {dirty[0].strip()}")
    return head


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_hash(heldout: Path, expected_file: Path = EXPECTED_FILE) -> str:
    if not heldout.is_file():
        raise Refusal(f"held-out file not found: {heldout}")
    actual = sha256_file(heldout)
    if expected_file.is_file():
        want = expected_file.read_text().strip().lower()
        if actual != want:
            raise Refusal(f"held-out SHA-256 {actual[:12]}... does not match expected_sha256.txt")
    elif not (actual.startswith(SEALED_PREFIX) and actual.endswith(SEALED_SUFFIX)):
        raise Refusal(f"held-out SHA-256 {actual[:8]}...{actual[-4:]} does not match the sealed "
                      f"{SEALED_PREFIX}...{SEALED_SUFFIX}")
    sidecar = heldout.with_name("SHA256")
    if sidecar.is_file() and sidecar.read_text().split()[0].lower() != actual:
        raise Refusal("held-out file does not match the SHA256 file shipped beside it")
    return actual


def check_not_run_before(result: Path = RESULT) -> None:
    if result.exists():
        raise Refusal(f"{result.name} already exists: the held-out set is run once and the result committed once")


def guards(heldout: Path, repo: Path = ROOT, result: Path = RESULT, expected_file: Path = EXPECTED_FILE) -> tuple[str, str]:
    check_not_run_before(result)
    head = check_freeze(repo)
    digest = check_hash(heldout, expected_file)
    return head, digest


def score_cases(heldout: Path, data: Path, alpha: float, users_csv: Path | None):
    """Train exactly as run_eval does, then score the held-out events. Returns (rows, baseline_note)."""
    sys.path.insert(0, str(ROOT / "detector" / "reference"))
    import json

    import pandas as pd
    import satark_detector as sd

    wl = json.loads((ROOT / "detector" / "reference" / "params.json").read_text())["watchlisted_remote_apps"]
    det, _, (users, sessions, _, _, _, _) = sd.evaluate(data, alpha, wl)

    ev = pd.read_csv(heldout, low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        if c in ev:
            ev[c] = ev[c].map({"True": True, "False": False, True: True, False: False})
    # The shipped model (detector/src/main/resources/model.json) is what runs on the phone. The reference trained here must
    # agree with it, or the held-out result would describe a different model from the one that ships.
    model = json.loads((ROOT / "detector" / "src" / "main" / "resources" / "model.json").read_text())
    for band, c in model["cohort_thresholds"].items():
        if abs(det.thr[band] - c["threshold"]) > 1e-9:
            raise Refusal(f"model.json is stale: cohort {band} threshold {c['threshold']} != retrained {det.thr[band]}; "
                          "run detector/tools/export_model.py before the held-out run")
    if users_csv is not None:
        hu = pd.read_csv(users_csv)
        note = f"user baselines from {users_csv.name}"
    else:
        # No per-user history exists for the sealed cases, so each is scored as a brand-new user, exactly as the phone does:
        # the cold-start population prior from model.json, and an unknown age band, which uses the pooled conformal threshold.
        hu = pd.DataFrame({"user_id": ev.user_id.unique()})
        hu["hist_median_inr"] = float(model["baseline"]["prior_median_inr"])
        hu["hist_mad_inr"] = float(model["baseline"]["prior_mad_inr"])
        hu["age_band"] = "unknown"
        det.thr["unknown"] = float(model["pooled_threshold"])
        note = (f"NO per-user history supplied: every case scored as a brand-new user, as the phone does "
                f"(cold-start prior median {hu.hist_median_inr.iloc[0]:.2f} / MAD {hu.hist_mad_inr.iloc[0]:.2f} from model.json; "
                f"age band unknown, pooled conformal threshold {det.thr['unknown']:.3f})")
    pay, alerts, first_pay = sd.featurize(ev, hu, wl)
    per_session = ev.groupby("session_id").agg(user_id=("user_id", "first")).reset_index()
    per_session = per_session.merge(hu[["user_id", "age_band"]], on="user_id", how="left")
    if "label" in ev:
        per_session = per_session.merge(ev.groupby("session_id").label.first().reset_index(), on="session_id", how="left")
    res = sd.decide(det, pay, alerts, first_pay, per_session)
    return res, note


def render_result(res, head: str, digest: str, note: str, when: str) -> str:
    lines = ["# Held-out result (run once)", "",
             f"- tag: `{TAG}` at commit `{head}`",
             f"- held-out SHA-256: `{digest}`",
             f"- run at: {when}",
             f"- baseline assumption: {note}", "",
             "| Case | Decision | Mechanism | Alarm at (s) | First payment (s) | Interdicted |", "|---|---|---|---|---|---|"]
    for r in res.sort_values("session_id").itertuples(index=False):
        alarm_t = "" if r.alarm_t != r.alarm_t else f"{r.alarm_t:.0f}"
        pay_t = "" if r.first_pay_t != r.first_pay_t else f"{r.first_pay_t:.0f}"
        lines.append(f"| {r.session_id} | {'ALARM' if r.alarm else 'no alarm'} | {r.mechanism} | {alarm_t} | {pay_t} | "
                     f"{'yes' if r.interdicted else 'no'} |")
    flagged = int(res.alarm.sum())
    lines += ["", f"**{flagged}/{len(res)} cases raised an alarm.**",
              "", "Write up every miss and every unexpected alarm below, by hand, before this file is committed.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heldout", type=Path, default=DEFAULT_HELDOUT)
    ap.add_argument("--users", type=Path, help="optional per-user history for the held-out cases")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "satarksim")
    ap.add_argument("--alpha", type=float, default=0.001)
    ap.add_argument("--check", action="store_true", help="run every guard and stop; writes nothing")
    a = ap.parse_args(argv)
    try:
        head, digest = guards(a.heldout)
    except Refusal as exc:
        print(f"REFUSED: {exc}")
        return 2
    if a.check:
        print(f"all guards pass: HEAD {head[:8]} is at {TAG}, held-out hash {digest[:8]}... matches")
        return 0
    res, note = score_cases(a.heldout, a.data, a.alpha, a.users)
    RESULT.write_text(render_result(res, head, digest, note, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                      encoding="utf-8", newline="\n")
    print(RESULT.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
