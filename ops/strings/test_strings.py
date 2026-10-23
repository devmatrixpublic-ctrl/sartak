import pytest
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import generate_strings as gen  # noqa: E402
import validate_strings as val  # noqa: E402


def real():
    return val.load_codes(), val.load_strings()


def test_shipped_strings_validate_cleanly():
    codes, strings = real()
    assert val.validate(codes, strings) == []


def test_shipped_xml_is_in_sync_and_well_formed():
    _, strings = real()
    assert val.check_xml(strings) == []
    root = ET.parse(val.XML_OUT).getroot()
    names = {s.get("name") for s in root.findall("string")}
    assert names == {gen.resource_name(c) for c in val.load_codes()}


@pytest.mark.parametrize("bad", [
    "Open https://example.com to check this payment.", "Visit www.bank.in now", "Go to secure-pay.com",
    "Share your PIN to continue", "Read out the OTP", "enter your otp",
])
def test_strings_with_a_url_pin_or_otp_fail(bad):
    codes = val.load_codes()
    strings = dict(val.load_strings())
    strings[codes[0]] = bad
    assert any(codes[0] in p and ("URL" in p or "PIN or OTP" in p) for p in val.validate(codes, strings))


def test_ordinary_words_are_not_mistaken_for_pin_or_otp():
    assert val.safety_problems("X", "Keep the line open, it is a pinned note about the photo.") == []


def test_missing_string_fails_the_build():
    codes, strings = real()
    del strings["F_NEW_PAYEE"]
    assert any("F_NEW_PAYEE: no English string" in p for p in val.validate(codes, strings))


def test_orphan_string_for_unknown_code_fails():
    codes, strings = real()
    strings["F_INVENTED"] = "Something happened."
    assert any("F_INVENTED" in p for p in val.validate(codes, strings))


def test_new_code_without_a_concept_rule_fails():
    codes, strings = real()
    codes.append("F_FUTURE")
    strings["F_FUTURE"] = "Something new."
    assert any("no concept rule" in p for p in val.validate(codes, strings))


def test_string_that_leaks_another_reason_fails():
    codes, strings = real()
    strings["F_NEW_PAYEE"] = "You're paying someone you have never paid before, on a call with someone who isn't in your contacts."
    problems = val.validate(codes, strings)
    assert any("F_NEW_PAYEE" in p and "also mentions" in p for p in problems)


def test_string_that_omits_its_own_reason_fails():
    codes, strings = real()
    strings["F_REPEAT_TO_PAYEE"] = "Please be careful."
    assert any("F_REPEAT_TO_PAYEE: does not mention" in p for p in val.validate(codes, strings))


def test_raw_code_name_and_overlong_text_fail():
    codes, strings = real()
    strings["F_IS_P2P"] = "F_IS_P2P: this is a payment to a person."
    strings["F_NEW_PAYEE"] = "You have never paid before. " * 10
    problems = val.validate(codes, strings)
    assert any("F_IS_P2P: shows a raw code name" in p for p in problems)
    assert any("F_NEW_PAYEE: must be 1-" in p for p in problems)


def test_stale_xml_is_detected(tmp_path):
    _, strings = real()
    stale = tmp_path / "strings.xml"
    stale.write_text(gen.render_xml(dict(strings, F_IS_P2P="Edited by hand.")), encoding="utf-8")
    assert any("out of date" in p for p in val.check_xml(strings, stale))
    assert any("missing" in p for p in val.check_xml(strings, tmp_path / "nope.xml"))


def test_android_escaping_of_apostrophes_and_ampersands():
    assert gen.android_escape("You're a & b") == "You\\'re a &amp; b"
    xml = gen.render_xml({"F_NEW_PAYEE": "You're paying <x>"}, codes=["F_NEW_PAYEE"])
    root = ET.fromstring(xml)
    assert root.find("string").text == "You\\'re paying <x>"


# ---- Hindi ----

def _hi():
    import json
    return json.loads(val.HI_SOURCE.read_text(encoding="utf-8"))["strings"]


def test_shipped_hindi_validates_cleanly():
    assert val.validate_hindi(val.load_codes(), _hi()) == []
    assert val.check_hindi_xml(_hi()) == []


def test_a_code_without_hindi_fails():
    hi = dict(_hi()); hi.pop(val.load_codes()[0])
    assert any("no Hindi string" in p for p in val.validate_hindi(val.load_codes(), hi))


@pytest.mark.parametrize("bad", [
    "अपना पिन बताइए", "ओटीपी साझा करें", "अपना OTP बताइए", "अपना PIN डालें", "यहाँ देखें https://x.in", "www.bank.in पर जाएँ", "सुरक्षित रहें secure-pay.com",
])
def test_hindi_strings_with_a_link_pin_or_otp_fail(bad):
    hi = dict(_hi()); code = val.load_codes()[0]; hi[code] = bad
    assert any(code in p for p in val.validate_hindi(val.load_codes(), hi)), bad


def test_hindi_must_actually_be_hindi():
    hi = dict(_hi()); code = val.load_codes()[0]; hi[code] = "You are on a call."
    assert any("no Devanagari" in p for p in val.validate_hindi(val.load_codes(), hi))
