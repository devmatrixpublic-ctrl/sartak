#!/usr/bin/env python3
"""Build a static metrics page (no server, no scripts, no live data) from the committed reports.

Inputs: ops/eval/reports/eval_result.json (headline numbers), detector/detector_report.md, ops/eval/fairness_report.md,
ops/eval/gbt_baseline_report.md, and alert counts exported from a test database (--db, a SQLite file; counts only, no ids).
Every number on the page is simulated or test data and is labelled that way.

Usage: python ops/dashboard/build.py [--db path/to/test.db] [--out ops/dashboard/dashboard.html]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM = "simulated data"

REPORTS = [
    ("Detector report", ROOT / "detector" / "detector_report.md"),
    ("Fairness by cohort", ROOT / "ops" / "eval" / "fairness_report.md"),
    ("Gradient-boosted baseline", ROOT / "ops" / "eval" / "gbt_baseline_report.md"),
]


def inline(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def md_to_html(md: str) -> str:
    """Just enough Markdown for our own reports: headings, tables, bullets, paragraphs. Everything is escaped."""
    out, lines, i = [], md.replace("\r\n", "\n").split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#"):
            level = min(len(ln) - len(ln.lstrip("#")) + 1, 6)  # the page owns h1
            out.append(f"<h{level}>{inline(ln.lstrip('#').strip())}</h{level}>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            i -= 1
            body = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            head, rest = body[0], body[1:]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rest) + "</tbody></table>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            i -= 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(("#", "|", "- ")):
                i += 1
                para.append(lines[i])
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


def alert_counts(db: Path | None) -> dict | None:
    """Counts only (by type, delivery and review state). No ids, devices or times leave the database."""
    if db is None or not db.is_file():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT type, delivered, review_status, COUNT(*) FROM alerts GROUP BY type, delivered, review_status").fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return {"total": sum(r[3] for r in rows), "rows": [{"type": r[0], "delivered": bool(r[1]), "review_status": r[2], "count": r[3]} for r in rows]}


def headline(path: Path) -> str:
    if not path.is_file():
        return "<p>No evaluation result found. Run <code>python ops/eval/run_eval.py</code>.</p>"
    d = json.loads(path.read_text(encoding="utf-8"))
    m = d["metrics"]
    return (f"<table><thead><tr><th>Measure ({SIM}, validation split)</th><th>Value</th></tr></thead><tbody>"
            f"<tr><td>Scam recall</td><td>{m['recall']:.1%} ({m['scam_alarmed']} of {m['scam_sessions']})</td></tr>"
            f"<tr><td>False alarms on legitimate sessions</td><td>{m['false_alarm_rate']:.3%} ({m['legit_false_alarms']} of {m['legit_sessions']})</td></tr>"
            f"<tr><td>Interdicted before first payment</td><td>{m['interdicted_rate']:.1%}</td></tr>"
            f"<tr><td>Median lead time</td><td>{m['median_lead_min']:.1f} min</td></tr>"
            f"<tr><td>Evaluation gate</td><td>{html.escape(str(d['gate']))}</td></tr></tbody></table>")


def build(db: Path | None = None) -> str:
    parts = ["<h2>Headline</h2><p class='sim'>All figures are " + SIM + ": a simulator, not real users or real traffic.</p>",
             headline(ROOT / "ops" / "eval" / "reports" / "eval_result.json")]
    counts = alert_counts(db)
    parts.append("<h2>Alerts in the test database</h2><p class='sim'>Test data from a development database, not real alerts.</p>")
    if counts is None:
        parts.append("<p>No test database was given (or it has no alerts table).</p>")
    else:
        parts.append(f"<p>Total alerts: <strong>{counts['total']}</strong> (test data)</p><table><thead><tr><th>Type</th><th>Delivered</th>"
                     "<th>Review</th><th>Count (test data)</th></tr></thead><tbody>"
                     + "".join(f"<tr><td>{html.escape(r['type'])}</td><td>{'yes' if r['delivered'] else 'no'}</td><td>{html.escape(r['review_status'])}</td><td>{r['count']}</td></tr>" for r in counts["rows"])
                     + "</tbody></table>")
    for title, path in REPORTS:
        parts.append(f"<h2>{html.escape(title)} <small>({SIM})</small></h2>")
        parts.append(md_to_html(path.read_text(encoding="utf-8")) if path.is_file() else f"<p>{html.escape(path.name)} not found.</p>")
    return PAGE.replace("{{BODY}}", "\n".join(parts))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Satark metrics</title>
<style>body{font:15px/1.5 system-ui,sans-serif;margin:24px auto;max-width:980px;padding:0 16px;color:#1a1a1a}
table{border-collapse:collapse;margin:8px 0 16px;width:100%}td,th{border:1px solid #ccc;padding:5px 8px;text-align:left;vertical-align:top}
th{background:#f3f3f3}code{background:#f3f3f3;padding:1px 4px}h2{margin-top:32px;border-bottom:1px solid #ddd}
.banner{background:#fff3cd;border:1px solid #e0c36a;padding:10px 14px}.sim{color:#7a4b00;font-weight:600}small{font-weight:400;color:#7a4b00}</style></head>
<body><h1>Satark metrics</h1>
<p class="banner"><strong>Every number on this page is simulated or test data.</strong> Nothing here measures real-world accuracy.
The page is static: generated from committed reports by <code>ops/dashboard/build.py</code>, with no live backend.</p>
{{BODY}}
</body></html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=None, help="SQLite test database to count alerts from")
    ap.add_argument("--out", type=Path, default=ROOT / "ops" / "dashboard" / "dashboard.html")
    a = ap.parse_args(argv)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(build(a.db), encoding="utf-8", newline="\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
