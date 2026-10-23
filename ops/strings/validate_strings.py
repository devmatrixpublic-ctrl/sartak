"""Validate the user-facing reason strings (plan 4.4).

Checks, all of which fail the build:
  1. every code in contracts/reason_codes.json has an English string, and no string is orphaned;
  2. each string is short, plain, and never shows a raw code name;
  3. each string mentions only its own reason: the "concepts" it triggers must include the code's
     primary concepts and stay inside the set that code is allowed to mention;
  4. app/src/main/res/values/strings.xml is exactly what generate_strings.py produces
     (so the file M1 consumes cannot drift from the validated source).

Usage: python ops/strings/validate_strings.py   (exit 1 on any problem)
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODES = ROOT / "contracts" / "reason_codes.json"
SOURCE = Path(__file__).with_name("reason_strings_en.json")
XML_OUT = ROOT / "app" / "src" / "main" / "res" / "values" / "strings.xml"
MAX_LEN = 140

# What a sentence is "about". Regexes are intentionally narrow; tests pin their behaviour.
CONCEPTS = {
    "contact": r"in your contacts|unknown person|unknown caller|someone who isn't",
    "call": r"\bcall\b",
    "video": r"\bvideo\b",
    "play": r"from Google Play",
    "sideload": r"outside Google Play",
    "install": r"\binstall",
    "remote": r"remote-access|screen-shar",
    "new_payee": r"never paid|new payee",
    "added": r"added this payee",
    "amount": r"\bamount\b|\blarge\b|\blarger\b|usual payments|normal range|far outside",
    "repeat": r"several times",
    "p2p": r"payment to a person",
    "order": r"in the order",
    "long": r"2 hours or more",
    "recent": r"few minutes|last 2 hours|shortly",
}

# code -> (primary concepts that MUST appear, extra concepts that MAY appear)
RULES = {
    "F_UNK_CONTACT_RECENT": ({"contact", "recent"}, set()),
    "F_UNK_CALL_ACTIVE": ({"call", "contact"}, set()),
    "F_UNK_VIDEO_ACTIVE": ({"video", "call", "contact"}, set()),
    "F_MINS_SINCE_UNK_LOG": ({"recent", "contact"}, set()),
    "F_INSTALL_PLAY_DURING_UNK": ({"play", "install", "contact"}, set()),
    "F_INSTALL_SIDELOAD_DURING_UNK": ({"sideload", "install", "contact"}, set()),
    "F_WATCHLIST_APP": ({"remote"}, {"install"}),
    "F_NEW_PAYEE": ({"new_payee"}, set()),
    "F_PAYEE_ADDED_AFTER_UNK": ({"added", "contact"}, set()),
    "F_LOG_AMT_RATIO": ({"amount"}, set()),
    "F_ROBUST_Z_POS": ({"amount"}, set()),
    "F_REPEAT_TO_PAYEE": ({"repeat"}, set()),
    "F_IS_P2P": ({"p2p"}, set()),
    "F_OCSS_ORDERED": ({"order"}, {"contact", "install", "new_payee"}),
    "F_NEWPAYEE_X_AMT": ({"new_payee", "amount"}, set()),
    "F_UNK_X_NEWPAYEE": ({"new_payee", "contact", "recent"}, set()),
    "RULE_SIDELOAD_DURING_CALL": ({"sideload", "install", "contact"}, set()),
    "RULE_LONG_SESSION": ({"long", "video", "call", "contact"}, set()),
}


def concepts_in(text: str) -> set[str]:
    return {name for name, rx in CONCEPTS.items() if re.search(rx, text, re.IGNORECASE)}


def load_codes(path: Path = CODES) -> list[str]:
    return [c["code"] for c in json.loads(path.read_text(encoding="utf-8"))["codes"]]


def load_strings(path: Path = SOURCE) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))["strings"]


URL_RE = re.compile(r"(https?://|www[.]|[a-z0-9-]+[.](com|in|org|net|co|io|app|me|ly|xyz|info)([^a-z]|$))", re.I)
# A warning must never be able to read as a request for a secret: the words themselves are banned.
SECRET_RE = re.compile(r"(^|[^a-z])(PIN|OTP)([^a-z]|$)", re.I)


def safety_problems(code: str, text: str) -> list[str]:
    out = []
    if URL_RE.search(text):
        out.append(f"{code}: contains a URL or web address")
    if SECRET_RE.search(text):
        out.append(f"{code}: mentions a PIN or OTP (strings must never ask for one)")
    return out


HI_SOURCE = Path(__file__).with_name("reason_strings_hi.json")
HI_XML_OUT = ROOT / "app" / "src" / "main" / "res" / "values-hi" / "strings.xml"
# The Hindi spellings of PIN and OTP (and "one-time"): no string may mention them either.
HI_SECRET_RE = re.compile(r"पिन|ओटीपी|ओ\.?\s?टी\.?\s?पी|वन[- ]?टाइम")


def validate_hindi(codes: list[str], strings: dict[str, str]) -> list[str]:
    """Every code needs a Hindi string; each must be Hindi, short, link-free and must never mention a PIN or OTP."""
    problems: list[str] = []
    for code in codes:
        text = strings.get(code)
        if text is None:
            problems.append(f"{code}: no Hindi string")
            continue
        problems += [p.replace(": ", " (Hindi): ", 1) for p in safety_problems(code, text)]
        if HI_SECRET_RE.search(text):
            problems.append(f"{code} (Hindi): mentions a PIN or OTP (strings must never ask for one)")
        if not re.search("[\u0900-\u097F]", text):
            problems.append(f"{code} (Hindi): has no Devanagari text")
        if not text.strip() or len(text) > MAX_LEN or "\n" in text:
            problems.append(f"{code} (Hindi): must be 1-{MAX_LEN} characters on one line")
        if re.search(r"\b(F_|RULE_)[A-Z0-9_]+\b", text):
            problems.append(f"{code} (Hindi): shows a raw code name")
    for code in strings:
        if code not in codes:
            problems.append(f"{code} (Hindi): string exists but the code is not in reason_codes.json")
    return problems


def check_hindi_xml(strings: dict[str, str]) -> list[str]:
    from generate_strings import render_xml

    if not HI_XML_OUT.is_file():
        return [f"values-hi/{HI_XML_OUT.name} is missing: run generate_strings.py"]
    src = json.loads(HI_SOURCE.read_text(encoding="utf-8")).get("source", "unknown")
    want = render_xml(strings, source=src).replace("from reason_strings_en.json", "from reason_strings_hi.json")
    if HI_XML_OUT.read_text(encoding="utf-8") != want:
        return [f"values-hi/{HI_XML_OUT.name} is out of date: run generate_strings.py"]
    ET.parse(HI_XML_OUT)
    return []


def validate(codes: list[str], strings: dict[str, str], rules=RULES) -> list[str]:
    problems: list[str] = []
    for code in codes:
        if code not in strings:
            problems.append(f"{code}: no English string")
    for code in strings:
        if code not in codes:
            problems.append(f"{code}: string exists but the code is not in reason_codes.json")
    for code in codes:
        text = strings.get(code)
        if text is None:
            continue
        problems += safety_problems(code, text)
        if code not in rules:
            problems.append(f"{code}: no concept rule in validate_strings.py (add one when adding a code)")
            continue
        if not text.strip() or len(text) > MAX_LEN:
            problems.append(f"{code}: must be 1-{MAX_LEN} characters")
        if re.search(r"\b(F_|RULE_)[A-Z0-9_]+\b", text):
            problems.append(f"{code}: shows a raw code name")
        if "\n" in text:
            problems.append(f"{code}: must not contain line breaks")
        primary, extra = rules[code]
        found = concepts_in(text)
        if not primary <= found:
            problems.append(f"{code}: does not mention {sorted(primary - found)}")
        stray = found - primary - extra
        if stray:
            problems.append(f"{code}: also mentions other reasons {sorted(stray)}")
    return problems


def check_xml(strings: dict[str, str], xml_path: Path = XML_OUT) -> list[str]:
    from generate_strings import render_xml

    if not xml_path.is_file():
        return [f"{xml_path.name} is missing: run generate_strings.py"]
    if xml_path.read_text(encoding="utf-8") != render_xml(strings):
        return [f"{xml_path.name} is out of date: run generate_strings.py"]
    ET.parse(xml_path)  # well-formed
    return []


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    codes, strings = load_codes(), load_strings()
    hi = json.loads(HI_SOURCE.read_text(encoding="utf-8"))["strings"]
    problems = validate(codes, strings) + check_xml(strings) + validate_hindi(codes, hi) + check_hindi_xml(hi)
    for p in problems:
        print("FAIL", p)
    print(f"{len(codes)} codes, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
