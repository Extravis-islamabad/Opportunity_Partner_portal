"""
API rate limiting via slowapi.

Per-route limits apply to expensive AI endpoints so a single hostile partner
can't exhaust our Groq free-tier quota for everyone else.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Key by IP address. For production you can switch to a JWT-aware keyer;
# see slowapi docs for the Request->user pattern.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
