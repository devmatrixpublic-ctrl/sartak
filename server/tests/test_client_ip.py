"""Client address for rate limiting behind proxies. The attacker controls everything LEFT of what our proxies append."""
import pytest
from starlette.requests import Request

from app.core.clientip import client_ip


def req(xff: list[str] | None = None, peer: str | None = "10.0.0.7") -> Request:
    headers = [(b"x-forwarded-for", v.encode()) for v in (xff or [])]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234) if peer else None})


def test_default_ignores_the_header_so_it_cannot_be_spoofed():
    assert client_ip(req(["203.0.113.9"]), 0) == "10.0.0.7"
    assert client_ip(req(["203.0.113.9"])) == "10.0.0.7"


def test_one_trusted_hop_uses_the_last_entry_and_ignores_what_the_caller_prepended():
    assert client_ip(req(["198.51.100.4"]), 1) == "198.51.100.4"
    assert client_ip(req(["1.2.3.4, 5.6.7.8, 198.51.100.4"]), 1) == "198.51.100.4"      # spoofed prefix is ignored


def test_two_trusted_hops_use_the_second_from_the_right():
    assert client_ip(req(["9.9.9.9, 198.51.100.4, 10.1.1.1"]), 2) == "198.51.100.4"


def test_fewer_entries_than_trusted_hops_falls_back_to_the_peer():
    assert client_ip(req(["198.51.100.4"]), 2) == "10.0.0.7"
    assert client_ip(req(None), 1) == "10.0.0.7"                                           # header absent


def test_non_ip_text_cannot_choose_a_bucket():
    for bad in ("evil-bucket", "999.1.1.1", "198.51.100.4:8080", "unknown", "<script>"):
        assert client_ip(req([f"1.1.1.1, {bad}"]), 1) == "10.0.0.7", bad


def test_ipv6_is_normalised_and_several_header_lines_are_combined():
    assert client_ip(req(["2001:DB8:0:0:0:0:0:1"]), 1) == "2001:db8::1"
    assert client_ip(req(["1.2.3.4", "198.51.100.4"]), 1) == "198.51.100.4"                # two X-Forwarded-For lines


def test_no_peer_is_unknown_not_a_crash():
    assert client_ip(req(None, peer=None), 0) == "unknown"
    assert client_ip(req(["198.51.100.4"], peer=None), 1) == "198.51.100.4"


def test_negative_hops_are_treated_as_off():
    assert client_ip(req(["198.51.100.4"]), -3) == "10.0.0.7"
