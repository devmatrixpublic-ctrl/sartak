#!/usr/bin/env python3
"""Out-of-sample check on FRESH simulator draws the detector has never seen (plan "Person B", phase 1).

What it does: builds new SatarkSim datasets from new random seeds (detector/reference/build_satarksim.py, into a temp folder), scores EVERY
session of each with the detector exactly as shipped (trained and calibrated on the shipped data's train and calibration splits, nothing
re-tuned), and writes one report: precision, recall, false-alarm rate with 95% intervals, per-playbook recall, false alarms by kind of
look-alike legitimate session, and the named missed scams with a rule-based tag for the likely cause.

What it is NOT: it is not the sealed held-out run (ops/heldout/run_heldout.py: needs the freeze tag, and it can only be done once), it does
not read data/satarksim/heldout, and it is not real-world accuracy. It shows how the numbers move across independent random draws of the
SAME simulator. The fresh sets also lack the Kaggle hour/merchant mix and the NPCI average-ticket calibration the shipped set used (those
files are not in the repo), so they carry a small deliberate distribution shift; the report says so.

Usage (repo root):  python ops/eval/fresh_seed_eval.py [--seeds 777001 777002 777003] [--keep DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "detector" / "reference"
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REF))

from run_eval import clopper_pearson  # noqa: E402

DEFAULT_SEEDS = (777001, 777002, 777003)
OUT = ROOT / "ops" / "eval" / "reports" / "fresh_seed_report.md"
PREVALENCES = ((None, "as simulated"), (1e-3, "1 scam in 1,000 sessions"), (1e-4, "1 in 10,000"))


# ---- building and scoring ---------------------------------------------------------------------------------------------------
def generate(seed: int, workdir: Path) -> Path:
    """Run the simulator with a different seed into workdir/seed<N>. A placeholder stands in for the simulator's required --heldout
    argument, so the sealed real cases are never involved."""
    out = workdir / f"seed{seed}"
    if (out / "satarksim_sessions.csv").is_file():
        return out
    params = json.loads((REF / "params.json").read_text(encoding="utf-8"))
    params["seed"] = seed
    pfile = workdir / f"params_{seed}.json"
    pfile.write_text(json.dumps(params), encoding="utf-8")
    placeholder = workdir / "placeholder_heldout.csv"
    placeholder.write_text("session_id\n", encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1"}          # the build report contains the rupee sign; Windows' default code page cannot write it
    r = subprocess.run([sys.executable, str(REF / "build_satarksim.py"), "--params", str(pfile), "--heldout", str(placeholder), "--out", str(out)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0 or not (out / "satarksim_events.csv").is_file():
        raise RuntimeError(f"simulator failed for seed {seed}: {(r.stdout + r.stderr)[-500:]}")
    return out


def load_detector(alpha: float, watchlist: list[str]):
    """The detector exactly as the evaluation pipeline builds it: fitted on the shipped train split, calibrated on the shipped calibration split."""
    import satark_detector as sd
    det, res, _ = sd.evaluate(ROOT / "data" / "satarksim", alpha, watchlist)
    return sd, det, res


def score_dataset(sd, det, watchlist: list[str], data: Path) -> pd.DataFrame:
    users = pd.read_csv(data / "satarksim_users.csv")
    sessions = pd.read_csv(data / "satarksim_sessions.csv")
    events = pd.read_csv(data / "satarksim_events.csv", low_memory=False)
    for c in ("caller_known", "payee_is_new"):
        events[c] = events[c].map({"True": True, "False": False, True: True, False: False})
    pay, alerts, first_pay = sd.featurize(events, users, watchlist)
    res = sd.decide(det, pay, alerts, first_pay, sessions)
    scored = pay.assign(score=det.score(pay))
    res = res.merge(scored.groupby("session_id").score.max().rename("max_score"), on="session_id", how="left")
    res = res.merge(scored.groupby("session_id").size().rename("n_pay"), on="session_id", how="left")
    res["n_pay"] = res.n_pay.fillna(0).astype(int)
    res["thr"] = res.age_band.map(det.thr)
    return res


# ---- analysis ---------------------------------------------------------------------------------------------------------------
BELOW_THRESHOLD = "score below the age-band threshold (the payment looked too ordinary)"


def classify_miss(row) -> str:
    """Likely cause of a missed scam, by RULE in this order (a tag to direct attention, not proof of cause)."""
    if row["n_pay"] == 0:
        return "no payment screen reached (nothing for the payment score to judge)"
    if not bool(row["call_state_available"]):
        return "phone does not expose call state (the unknown call is invisible)"
    if not bool(row["usage_access"]):
        return "usage access off (foreground apps invisible)"
    if row["playbook"] == "remote_access" and row["week"] >= 6:
        return "remote-access app that is not on the watch-list (new from week 6)"
    return BELOW_THRESHOLD


def rates(res: pd.DataFrame) -> dict:
    scam, legit = res[res.label == "scam"], res[res.label == "legit"]
    s_n, s_k, l_n, l_k = len(scam), int(scam.alarm.sum()), len(legit), int(legit.alarm.sum())
    return {"scam_n": s_n, "scam_hit": s_k, "legit_n": l_n, "legit_fa": l_k,
            "interdicted": int(scam.interdicted.sum()), "median_lead_min": float(scam.lead_min.median())}


def precision(recall: float, fa_rate: float, prevalence: float) -> float:
    tp, fp = recall * prevalence, fa_rate * (1 - prevalence)
    return tp / (tp + fp) if tp + fp else float("nan")


def pooled(parts: list[dict]) -> dict:
    keys = ("scam_n", "scam_hit", "legit_n", "legit_fa", "interdicted")
    out = {k: sum(p[k] for p in parts) for k in keys}
    out["median_lead_min"] = float(np.median([p["median_lead_min"] for p in parts]))
    return out


def by_playbook(res: pd.DataFrame) -> pd.DataFrame:
    s = res[res.label == "scam"]
    return s.groupby("playbook").agg(n=("alarm", "size"), hit=("alarm", "sum")).reset_index()


def fa_by_kind(res: pd.DataFrame) -> pd.DataFrame:
    l = res[res.label == "legit"]
    return l.groupby("session_kind").agg(n=("alarm", "size"), fa=("alarm", "sum")).reset_index()


def missed(res: pd.DataFrame, tag: str) -> pd.DataFrame:
    m = res[(res.label == "scam") & (~res.alarm)].copy()
    if m.empty:
        m["cause"], m["gap"] = pd.Series(dtype=object), pd.Series(dtype=float)
    else:
        m["cause"] = m.apply(classify_miss, axis=1)
        m["gap"] = np.where(m.cause == BELOW_THRESHOLD, m.thr - m.max_score, np.nan)  # how far under the threshold, logit scale
    m["dataset"] = tag
    return m


# ---- report -----------------------------------------------------------------------------------------------------------------
def ci(k: int, n: int) -> str:
    lo, hi = clopper_pearson(k, n)
    return f"{lo:.1%} - {hi:.1%}"


def headline_rows(name: str, r: dict) -> list[str]:
    rec, far = r["scam_hit"] / r["scam_n"], r["legit_fa"] / r["legit_n"]
    base = r["scam_n"] / (r["scam_n"] + r["legit_n"])
    prec = [precision(rec, far, base if p is None else p) for p, _ in PREVALENCES]
    return [f"| {name} | {r['scam_hit']}/{r['scam_n']} = {rec:.1%} ({ci(r['scam_hit'], r['scam_n'])}) | "
            f"{r['legit_fa']}/{r['legit_n']} = {far:.3%} ({clopper_pearson(r['legit_fa'], r['legit_n'])[0]:.3%} - {clopper_pearson(r['legit_fa'], r['legit_n'])[1]:.3%}) | "
            f"{prec[0]:.1%} | {prec[1]:.2%} | {prec[2]:.3%} |"]


def render(seeds, per_seed: dict, shipped_val: dict, books: pd.DataFrame, kinds: pd.DataFrame, miss: pd.DataFrame, fa_mech: pd.Series,
           elapsed: float, shipped_books: pd.DataFrame | None = None) -> str:
    tot = pooled(list(per_seed.values()))
    L = ["# Results on fresh simulator draws (Person B, phase 1)", "",
         "**Simulated data throughout.** This is not real-world accuracy and not the sealed held-out run. It re-draws the simulator with new seeds "
         "(never seen by the detector) and scores every session with the detector exactly as shipped: nothing was re-tuned. "
         f"Seeds: {', '.join(str(s) for s in seeds)}. Built in {elapsed:.0f} s.", "",
         "The fresh sets lack the Kaggle hour/merchant mix and the NPCI average-ticket calibration the shipped set used (those files are not in the "
         "repository), so they also carry a small distribution shift. That is a feature of this test, not a flaw to hide.", "",
         "## 1. Headline", "",
         "| Dataset | Scam recall (95% CI) | False alarms on legit (95% CI) | Precision as simulated | Precision at 1 scam in 1,000 | Precision at 1 in 10,000 |",
         "|---|---|---|---|---|---|"]
    L += headline_rows("Shipped validation split (reference)", shipped_val)
    for s in seeds:
        L += headline_rows(f"Fresh seed {s}", per_seed[s])
    L += headline_rows("**Fresh seeds pooled**", tot)
    far = tot["legit_fa"] / tot["legit_n"]
    rec = tot["scam_hit"] / tot["scam_n"]
    L += ["", f"Read the precision columns carefully: with a false-alarm rate of {far:.3%} the share of alarms that are real scams collapses as scams get "
              f"rarer ({precision(rec, far, 1e-3):.1%} at one scam in 1,000 sessions). That is arithmetic, not a bug, and it is why the app warns and holds "
              f"rather than blocks. Interdicted before the first payment: {tot['interdicted']}/{tot['scam_n']} = {tot['interdicted'] / tot['scam_n']:.1%}.", "",
         "## 2. Recall by scam playbook", "",
         "| Playbook | Fresh seeds, pooled: caught | Recall (95% CI) | Shipped validation split: caught | Recall |", "|---|---|---|---|---|"]
    ship = {} if shipped_books is None else {r.playbook: r for _, r in shipped_books.iterrows()}
    for _, r in books.sort_values("playbook").iterrows():
        s = ship.get(r.playbook)
        sv = f"{int(s.hit)}/{int(s.n)} | {int(s.hit) / int(s.n):.1%}" if s is not None else "n/a | n/a"
        L.append(f"| {r.playbook} | {int(r.hit)}/{int(r.n)} | {int(r.hit) / int(r.n):.1%} ({ci(int(r.hit), int(r.n))}) | {sv} |")
    L += ["", "## 3. False alarms by kind of legitimate session (pooled)", "",
          "Look-alike sessions (`hn_*`) are built to resemble scams: a real family emergency, a real remote-support call, rent day.", "",
          "| Session kind | Sessions | False alarms | Rate |", "|---|---|---|---|"]
    for _, r in kinds.sort_values("fa", ascending=False).iterrows():
        L.append(f"| {r.session_kind} | {int(r.n)} | {int(r.fa)} | {int(r.fa) / int(r.n):.3%} |")
    L += ["", "Which rule fired on the false alarms: " + (", ".join(f"{k} {v}" for k, v in fa_mech.items()) or "none") + ".", "",
          "## 4. What the model gets wrong: missed scams", ""]
    if miss.empty:
        L.append("No scam was missed on the fresh seeds.")
    else:
        causes = miss.groupby("cause").size().sort_values(ascending=False)
        L += [f"{len(miss)} scam sessions were missed. The cause below is a RULE-BASED TAG (first matching reason in a fixed order), so it directs "
              "attention but is not proof.", "", "| Likely cause | Missed | Share |", "|---|---|---|"]
        for c, n in causes.items():
            L.append(f"| {c} | {n} | {n / len(miss):.0%} |")
        L += ["", "### Named cases (up to 3 per playbook and cause; the full list is in the JSON next to this report)", "",
              "| Dataset | Session | Playbook | Age band | Week | Likely cause | Short of threshold |", "|---|---|---|---|---|---|---|"]
        shown = miss.sort_values(["playbook", "cause", "dataset", "session_id"]).groupby(["playbook", "cause"]).head(3)
        for _, r in shown.iterrows():
            gap = "" if pd.isna(r.gap) else f"{r.gap:.2f}"
            L.append(f"| {r.dataset} | {r.session_id} | {r.playbook} | {r.age_band} | {int(r.week)} | {r.cause} | {gap} |")
        L += ["", "Per playbook, how the misses split by cause:", "", "| Playbook | Missed | Of which: score below threshold |", "|---|---|---|"]
        for pb, g in miss.groupby("playbook"):
            L.append(f"| {pb} | {len(g)} | {int((g.cause == BELOW_THRESHOLD).sum())} |")
    L += ["", "## 5. What this does and does not show", "",
          "- It shows the recall and false-alarm figures are not an accident of one random draw: across independent draws they move by the amounts in section 1.",
          "- It does not show real-world accuracy. Both the training data and this test come from the same simulator and share its assumptions.",
          "- Section 4 is the honest list of where the detector fails; each cause is a known limitation, not a surprise.",
          "- The sealed held-out run is still to do, and can only be done once. It is blocked on purpose until the `detector-freeze` tag exists.", ""]
    return "\n".join(L) + "\n"


def run(seeds, workdir: Path, out: Path) -> dict:
    t0 = time.time()
    params = json.loads((REF / "params.json").read_text(encoding="utf-8"))
    wl, alpha = params["watchlisted_remote_apps"], params["calibration_alpha"]
    sd, det, shipped_res = load_detector(alpha, wl)
    v = shipped_res[shipped_res.split == "validation"]
    shipped_val = rates(v)
    per_seed, books, kinds, misses, fa_mech = {}, [], [], [], []
    for s in seeds:
        res = score_dataset(sd, det, wl, generate(s, workdir))
        per_seed[s] = rates(res)
        books.append(by_playbook(res))
        kinds.append(fa_by_kind(res))
        misses.append(missed(res, f"seed {s}"))
        fa_mech.append(res[(res.label == "legit") & res.alarm].mechanism)
    books = pd.concat(books).groupby("playbook")[["n", "hit"]].sum().reset_index()
    kinds = pd.concat(kinds).groupby("session_kind")[["n", "fa"]].sum().reset_index()
    miss = pd.concat(misses, ignore_index=True)
    fa_m = pd.concat(fa_mech).value_counts()
    text = render(seeds, per_seed, shipped_val, books, kinds, miss, fa_m, time.time() - t0, by_playbook(v))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    detail = out.with_suffix(".json")
    detail.write_text(json.dumps({"seeds": list(seeds), "per_seed": per_seed, "shipped_validation": shipped_val,
                                  "missed": miss[["dataset", "session_id", "playbook", "age_band", "week", "cause", "gap"]].round({"gap": 3}).to_dict("records")}, indent=1),
                      encoding="utf-8")
    return {"per_seed": per_seed, "pooled": pooled(list(per_seed.values())), "missed": len(miss)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--keep", type=Path, help="keep the generated datasets in this folder (default: a temp folder that is deleted)")
    a = ap.parse_args(argv)
    if a.keep:
        a.keep.mkdir(parents=True, exist_ok=True)
        r = run(a.seeds, a.keep, a.out)
    else:
        with tempfile.TemporaryDirectory(prefix="satark-fresh-") as td:
            r = run(a.seeds, Path(td), a.out)
    p = r["pooled"]
    print(f"wrote {a.out}: recall {p['scam_hit']}/{p['scam_n']} = {p['scam_hit'] / p['scam_n']:.1%}, "
          f"false alarms {p['legit_fa']}/{p['legit_n']} = {p['legit_fa'] / p['legit_n']:.3%}, {r['missed']} scams missed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
