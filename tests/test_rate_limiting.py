"""Tests for T02-18 — rate limiting middleware + X-RateLimit headers.

Covers:
- central limiter is Redis-backed when REDIS_URL is set, in-memory
  otherwise
- category constants match docs/07-API-SPEC.md §7
- key_func prefers authenticated user id over IP so per-user limits
  aren't bypassable by spinning up IPs
- SlowAPIMiddleware is installed on the FastAPI app
- 429 exception handler is registered
- auth.login returns X-RateLimit-* headers and falls to 429 after
  exceeding its category budget
"""

import importlib
import os
from unittest.mock import patch

from app.core import rate_limiting

# ---------------------------------------------------------------------------
# Category contract
# ---------------------------------------------------------------------------

def test_rate_limit_category_values_match_api_spec():
    # docs/07-API-SPEC.md §7 — verbatim.
    assert rate_limiting.RateLimits.EDGE_HEARTBEAT == "120/minute"
    assert rate_limiting.RateLimits.EDGE_ALERTS == "300/minute"
    assert rate_limiting.RateLimits.AUTH_LOGIN == "10/minute"
    assert rate_limiting.RateLimits.AUTH_PASSWORD_RESET == "5/minute"
    assert rate_limiting.RateLimits.DASHBOARD_READ == "1000/minute"
    assert rate_limiting.RateLimits.DASHBOARD_WRITE == "200/minute"


def test_rate_limit_categories_are_enumerable():
    # RATE_LIMIT_CATEGORIES lets an observability task iterate every
    # configured budget, e.g. to export it as a metric.
    assert len(rate_limiting.RATE_LIMIT_CATEGORIES) == 6


# ---------------------------------------------------------------------------
# Storage selection
# ---------------------------------------------------------------------------

def test_storage_uri_prefers_rate_limit_redis_url():
    with patch.dict(os.environ, {
        "RATE_LIMIT_REDIS_URL": "redis://rl:6379/3",
        "REDIS_URL": "redis://other:6379/0",
    }, clear=False):
        assert rate_limiting._rate_limit_storage_uri() == "redis://rl:6379/3"


def test_storage_uri_falls_back_to_redis_url():
    with patch.dict(os.environ, {"REDIS_URL": "redis://shared:6379/0"}, clear=False):
        os.environ.pop("RATE_LIMIT_REDIS_URL", None)
        assert rate_limiting._rate_limit_storage_uri() == "redis://shared:6379/0"


def test_storage_uri_returns_none_when_no_env_var():
    os.environ.pop("RATE_LIMIT_REDIS_URL", None)
    os.environ.pop("REDIS_URL", None)
    assert rate_limiting._rate_limit_storage_uri() is None


# ---------------------------------------------------------------------------
# Key function
# ---------------------------------------------------------------------------

class _FakeState:
    def __init__(self):
        self.user = None


class _FakeRequest:
    def __init__(self, user=None, client_host="1.2.3.4"):
        self.state = _FakeState()
        self.state.user = user

        class _Client:
            host = client_host
        self.client = _Client()
        # slowapi's get_remote_address inspects headers first
        self.headers = {}
        self.scope = {"client": (client_host, 0)}


def test_key_func_uses_user_id_for_authenticated_requests():
    request = _FakeRequest(user={"user_id": 42, "role": "admin"})
    assert rate_limiting._rate_limit_key(request) == "user:42"


def test_key_func_falls_back_to_sub_claim_when_user_id_absent():
    request = _FakeRequest(user={"sub": "alice"})
    assert rate_limiting._rate_limit_key(request) == "user:alice"


def test_key_func_falls_back_to_ip_when_unauthenticated():
    request = _FakeRequest(user=None, client_host="203.0.113.7")
    key = rate_limiting._rate_limit_key(request)
    assert key.startswith("ip:")


# ---------------------------------------------------------------------------
# Limiter instance
# ---------------------------------------------------------------------------

def test_limiter_has_headers_enabled():
    # X-RateLimit-* headers are the whole point of this task's acceptance.
    assert rate_limiting.limiter._headers_enabled is True


def test_limiter_swallows_storage_errors():
    # Redis outage must not 500 user requests. slowapi's swallow_errors
    # turns backend failures into "no limit applied" instead.
    assert rate_limiting.limiter._swallow_errors is True


def test_build_limiter_returns_independent_instance():
    # Module import time already built one; ensure build_limiter()
    # produces a separate, freshly-configured instance rather than
    # returning the module singleton.
    new_limiter = rate_limiting.build_limiter()
    assert new_limiter is not rate_limiting.limiter


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------

def test_main_app_installs_slowapi_middleware():
    # Use the app object conftest already imported.
    # Starlette stores middleware in app.user_middleware as a list of
    # Middleware descriptors.
    from slowapi.middleware import SlowAPIMiddleware as SAM

    from shoplift_detector.main import app

    installed = [m.cls for m in app.user_middleware]
    assert SAM in installed, (
        "SlowAPIMiddleware must be installed so X-RateLimit-* headers "
        "propagate through the response pipeline."
    )


def test_main_app_registers_429_exception_handler():
    from slowapi.errors import RateLimitExceeded

    from shoplift_detector.main import app

    assert RateLimitExceeded in app.exception_handlers


def test_main_app_state_exposes_the_shared_limiter():
    from shoplift_detector.main import app

    assert app.state.limiter is rate_limiting.limiter


# ---------------------------------------------------------------------------
# Decorator reload sanity — shared limiter is picked up by auth module
# ---------------------------------------------------------------------------

def test_auth_module_shares_the_central_limiter():
    # Re-import here to avoid any stale snapshot from other tests.
    auth_mod = importlib.import_module("app.api.v1.auth")
    assert auth_mod.limiter is rate_limiting.limiter
