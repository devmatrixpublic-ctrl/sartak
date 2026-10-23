#!/usr/bin/env python3
"""Generate scam-script VARIANTS offline, for the red-team report only.

The variants are short outlines of the pretext a scammer uses (who they claim to be, the story, the pressure, what they ask
the victim to do), written so detection can be tested against wording it has not seen. They go to data/llm_variants/, which is
separate from the SatarkSim train, validation and held-out sets, and they are never used to train, calibrate or tune the
detector and never appear in the decision path. Provenance (generator, date, prompt hash, count) is appended to
data/llm_variants/PROVENANCE.md by every real run.

Needs ANTHROPIC_API_KEY. Without it the script prints why and exits 2 without touching the network, so a run is an explicit step.
Use --dry-run to see the prompts and the prompt hash with no API call.

Usage: ANTHROPIC_API_KEY=... python ops/eval/gen_variants.py --per-playbook 5
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "llm_variants"
DEFAULT_MODEL = "claude-sonnet-5-5"

PLAYBOOKS = {
    "digital_arrest": "a caller posing as police or an investigation agency who says the victim is under 'digital arrest' and must stay on a video call",
    "remote_access_kyc": "a caller posing as a bank or telecom officer who says KYC or an account problem must be fixed and asks the victim to install a remote-support app",
    "malicious_apk": "a message or caller who gets the victim to install an app from outside the Play Store to 'claim' a refund, prize or service",
    "family_emergency": "a caller or message claiming a relative is in trouble and money is needed at once",
    "screen_share": "a caller who asks the victim to share their screen 'to help' and then guides them through a payment",
}

PROMPT_TEMPLATE = (
    "You are helping test a fraud-protection app. Write {n} different short outlines (at most 45 words each) of how a scammer "
    "might run this scam: {description}. Each outline states the pretext, the pressure used, and what the victim is asked to do. "
    "Vary the wording, the claimed identity and the order of steps. Rules: no real person, company or agency names; no phone "
    "numbers, links, email addresses or account numbers; plain sentences. Return a JSON array of {n} strings and nothing else."
)

URL_RE = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|in|org|net|co|io|app)\b)", re.I)


def prompt_for(playbook: str, n: int) -> str:
    return PROMPT_TEMPLATE.format(n=n, description=PLAYBOOKS[playbook])


def prompt_hash() -> str:
    """Hash of the template and the playbook descriptions, so a change to either shows up in the provenance."""
    return hashlib.sha256((PROMPT_TEMPLATE + json.dumps(PLAYBOOKS, sort_keys=True)).encode("utf-8")).hexdigest()


def clean(text: str) -> str | None:
    """Keep an outline only if it is plain text with no link, address or long number; otherwise drop it."""
    t = " ".join(str(text).split())
    if not t or len(t.split()) > 60 or URL_RE.search(t) or "@" in t or re.search(r"\d{6,}", t):
        return None
    return t


def parse_reply(reply: str) -> list[str]:
    m = re.search(r"\[.*\]", reply, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [c for c in (clean(i) for i in items if isinstance(i, str)) if c]


def generate(per_playbook: int, model: str) -> list[dict]:
    import anthropic  # imported late: --dry-run and the tests do not need the SDK or a key

    client = anthropic.Anthropic()
    rows = []
    for pb in PLAYBOOKS:
        msg = client.messages.create(model=model, max_tokens=1500, messages=[{"role": "user", "content": prompt_for(pb, per_playbook)}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        rows += [{"playbook": pb, "variant": v} for v in parse_reply(text)]
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-playbook", type=int, default=5)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.dry_run:
        for pb in PLAYBOOKS:
            print(f"[{pb}] {prompt_for(pb, a.per_playbook)}\n")
        print("prompt hash:", prompt_hash())
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set: nothing generated. Set it and run again (or use --dry-run).", file=sys.stderr)
        return 2

    rows = generate(a.per_playbook, a.model)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc)
    out = a.out_dir / f"variants_{stamp:%Y%m%d_%H%M%S}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8", newline="\n")
    with (a.out_dir / "PROVENANCE.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n| {out.name} | {a.model} | {stamp:%Y-%m-%d} | `{prompt_hash()[:16]}` | {len(rows)} |\n")
    print(f"wrote {len(rows)} variants to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
