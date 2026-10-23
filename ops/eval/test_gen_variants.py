import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gen_variants as g  # noqa: E402


def test_no_key_means_no_run_and_exit_2(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert g.main(["--out-dir", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []


def test_dry_run_needs_no_key_and_prints_the_hash(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert g.main(["--dry-run", "--per-playbook", "2"]) == 0
    assert g.prompt_hash() in capsys.readouterr().out


def test_prompt_hash_is_stable_and_covers_the_playbooks(monkeypatch):
    h = g.prompt_hash()
    assert len(h) == 64 and h == g.prompt_hash()
    monkeypatch.setitem(g.PLAYBOOKS, "x", "y")
    assert g.prompt_hash() != h


def test_outlines_with_links_addresses_or_long_numbers_are_dropped():
    assert g.clean("Caller claims to be an officer and demands a transfer.") is not None
    for bad in ("Visit www.bank.in now", "Open https://x.io", "Mail me at a@b.com", "Call 9876543210 now", ""):
        assert g.clean(bad) is None, bad


def test_reply_parsing_keeps_only_clean_strings():
    reply = 'Here you go: ["Claims to be police.", "See http://x.com", 5, "Asks to install an app."]'
    assert g.parse_reply(reply) == ["Claims to be police.", "Asks to install an app."]
    assert g.parse_reply("not json") == []


def test_variants_live_outside_the_training_and_heldout_dirs():
    assert g.OUT_DIR.name == "llm_variants" and g.OUT_DIR.parent.name == "data"
    assert "heldout" not in str(g.OUT_DIR) and "satarksim" not in str(g.OUT_DIR)
