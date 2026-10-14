"""
API rate limiting via slowapi.

Per-route limits apply to expensive AI endpoints so a single hostile partner
can't exhaust our Groq free-tier quota for everyone else, and to the auth
endpoints so passwords and MFA codes cannot be guessed at speed.
"""
from slowapi import Limiter
from starlette.requests import Request


def client_ip(request: Request) -> str:
    """The address of the person making the request, for rate limits and audit.

    Deliberately request.client.host and never a raw X-Forwarded-For read.
    The API is always reached through nginx, so the TCP peer is the nginx
    container; uvicorn's proxy-headers middleware (FORWARDED_ALLOW_IPS, set in
    the Dockerfile and both compose files) replaces it with the real client
    address — but only when the peer is one of the trusted proxy networks, and
    taking the right-most untrusted hop, so a client cannot choose its own
    address by sending the header itself. Reading the header here would undo
    exactly that protection.

    Before that was configured, every request appeared to come from nginx, so
    all users shared one 10-a-minute login bucket and every audit row carried
    the proxy's address.
    """
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


limiter = Limiter(key_func=client_ip, default_limits=[])
