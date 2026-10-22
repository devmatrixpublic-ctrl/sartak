"""Who is the client, for rate limiting, when the server sits behind proxies (Render's load balancer).

`X-Forwarded-For` is `client, proxy1, proxy2...`: every proxy APPENDS the address it received the request from. Entries to the
LEFT are whatever the caller chose to send, so they are never trusted. With `trusted_proxy_hops = N` (the number of proxies we
operate or trust in front of the app) the client is the N-th entry from the RIGHT. Anything doubtful falls back to the address of
the immediate peer, which an attacker cannot forge. The default is 0: ignore the header entirely.
"""
import ipaddress

from fastapi import Request


def client_ip(request: Request, trusted_hops: int = 0) -> str:
    peer = request.client.host if request.client else "unknown"
    if trusted_hops <= 0:
        return peer
    entries: list[str] = []
    for value in request.headers.getlist("x-forwarded-for"):
        entries += [p.strip() for p in value.split(",") if p.strip()]
    if len(entries) < trusted_hops:
        return peer                      # fewer hops than we trust: the header cannot be what our proxies produced
    candidate = entries[-trusted_hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer                      # not an IP address: do not let free text pick a bucket
