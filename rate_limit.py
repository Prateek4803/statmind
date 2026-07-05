"""
rate_limit.py — Shared slowapi Limiter instance.

Why this module exists (P1-SEC-3):
  The Limiter used to be constructed inside main.py, which meant routers
  defined in other modules (auth.py, ppap_generator.py, routers/*) could not
  declare per-route limits — they only got the global 60/min default. That
  left the magic-link endpoint able to send up to 60 emails per minute per IP:
  enough to bomb a victim's inbox and burn the entire Resend daily quota
  (100 emails/day), i.e. a denial-of-service on login for every user.

  Constructing the limiter here breaks the circular-import problem:
  auth.py and main.py both import from this leaf module.

Usage in a router module:
    from rate_limit import limiter

    @router.post("/endpoint")
    @limiter.limit("3/minute")
    async def handler(request: Request, ...):   # `request` param is required
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Global defaults apply to every route via SlowAPIMiddleware (added in main.py).
# Individual routes can declare stricter limits with @limiter.limit(...).
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute", "600/hour"])
