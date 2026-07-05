"""
Shared test configuration.

All requests from fastapi.testclient come from the same pseudo-IP, so the
per-IP slowapi limits (e.g. 3/minute on /auth/magic-link) would throttle the
test suite itself and turn later tests into false 429 failures. Application-
level throttles that are part of the behavior under test (like the per-email
pending-token cap, which is DB-based) are unaffected by this switch.
"""
import pytest

from rate_limit import limiter


@pytest.fixture(autouse=True, scope="session")
def _disable_ip_rate_limiting():
    limiter.enabled = False
    yield
    limiter.enabled = True
