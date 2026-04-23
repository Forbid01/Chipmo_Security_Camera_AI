"""Tests for T02-20 — API deprecation / sunset header framework.

Covers:
- RFC 7231 IMF-fixdate formatting for Sunset
- LEGACY_DEPRECATION_MAP has entries for every legacy root route
- resolve_successor handles exact + prefix (video_feed/{id}) matches
- DeprecationHeadersMiddleware appends headers to legacy responses
  and leaves /api/v1/* responses untouched
- `@deprecated_endpoint` decorator appends headers without breaking
  Response injection
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Response

from shoplift_detector.app.core.deprecation import (
    DEFAULT_SUNSET_DATE,
    LEGACY_DEPRECATION_MAP,
    DeprecationHeadersMiddleware,
    apply_deprecation_headers,
    deprecated_endpoint,
    format_sunset,
    resolve_successor,
)

# ---------------------------------------------------------------------------
# format_sunset
# ---------------------------------------------------------------------------

def test_format_sunset_returns_imf_fixdate_from_datetime():
    ts = datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC)
    assert format_sunset(ts) == "Fri, 31 Dec 2027 23:59:59 GMT"


def test_format_sunset_accepts_iso_datetime_string():
    assert (
        format_sunset("2027-12-31T23:59:59+00:00")
        == "Fri, 31 Dec 2027 23:59:59 GMT"
    )


def test_format_sunset_accepts_bare_date_as_end_of_day():
    assert format_sunset("2027-12-31") == "Fri, 31 Dec 2027 23:59:59 GMT"


def test_format_sunset_none_passthrough():
    assert format_sunset(None) is None


# ---------------------------------------------------------------------------
# apply_deprecation_headers
# ---------------------------------------------------------------------------

def test_apply_deprecation_headers_writes_all_three_headers():
    response = Response()
    apply_deprecation_headers(
        response,
        successor="/api/v1/alerts",
        sunset=datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC),
    )
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == "Fri, 31 Dec 2027 23:59:59 GMT"
    assert (
        response.headers["Link"]
        == '</api/v1/alerts>; rel="successor-version"'
    )


def test_apply_deprecation_headers_defaults_to_project_sunset():
    response = Response()
    apply_deprecation_headers(response, successor="/api/v1/alerts")
    assert response.headers["Sunset"] == format_sunset(DEFAULT_SUNSET_DATE)


def test_apply_deprecation_headers_is_idempotent():
    response = Response()
    apply_deprecation_headers(response, successor="/a", sunset="2027-12-31")
    apply_deprecation_headers(response, successor="/a", sunset="2027-12-31")
    # Starlette's MutableHeaders replaces on set; re-application must
    # not produce duplicate entries.
    values = [v for k, v in response.raw_headers if k == b"deprecation"]
    assert len(values) == 1


# ---------------------------------------------------------------------------
# resolve_successor + LEGACY_DEPRECATION_MAP
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("legacy,successor", [
    ("/token", "/api/v1/auth/token"),
    ("/register", "/api/v1/auth/register"),
    ("/users/me", "/api/v1/auth/me"),
    ("/alerts", "/api/v1/alerts"),
    ("/video_feed", "/api/v1/video/feed"),
    ("/forgot-password", "/api/v1/auth/forgot-password"),
    ("/verify-code", "/api/v1/auth/verify-code"),
    ("/reset-password", "/api/v1/auth/reset-password"),
])
def test_legacy_deprecation_map_covers_root_endpoints(legacy, successor):
    assert LEGACY_DEPRECATION_MAP.get(legacy) == successor


def test_resolve_successor_handles_path_parameter_suffix():
    # /video_feed/42 → /api/v1/video/feed/42 via the prefix rule.
    assert resolve_successor("/video_feed/42") == "/api/v1/video/feed/42"


def test_resolve_successor_returns_none_for_unmapped_path():
    assert resolve_successor("/api/v1/alerts") is None
    assert resolve_successor("/health") is None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(DeprecationHeadersMiddleware)

    @app.get("/alerts")
    def legacy_alerts():
        return {"ok": True}

    @app.get("/video_feed/{camera_id}")
    def legacy_video(camera_id: int):
        return {"camera_id": camera_id}

    @app.get("/api/v1/alerts")
    def modern_alerts():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_middleware_adds_headers_to_legacy_route():
    import httpx

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/alerts")

    assert response.headers["Deprecation"] == "true"
    assert "Sunset" in response.headers
    assert response.headers["Link"].startswith("</api/v1/alerts>")
    assert 'rel="successor-version"' in response.headers["Link"]


@pytest.mark.asyncio
async def test_middleware_rewrites_path_parameter_into_successor():
    import httpx

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/video_feed/42")

    assert response.headers["Link"].startswith("</api/v1/video/feed/42>")


@pytest.mark.asyncio
async def test_middleware_leaves_v1_route_untouched():
    import httpx

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/api/v1/alerts")

    assert "Deprecation" not in response.headers
    assert "Sunset" not in response.headers
    assert "Link" not in response.headers


@pytest.mark.asyncio
async def test_middleware_leaves_non_deprecated_route_untouched():
    import httpx

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/health")

    assert "Deprecation" not in response.headers


# ---------------------------------------------------------------------------
# Decorator form
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decorator_appends_headers_when_response_param_present():
    app = FastAPI()

    @app.get("/legacy")
    @deprecated_endpoint(
        successor="/api/v1/legacy",
        sunset=datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC),
    )
    async def legacy(response: Response):
        return {"ok": True}

    import httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/legacy")

    assert r.headers["Deprecation"] == "true"
    assert r.headers["Sunset"] == "Fri, 31 Dec 2027 23:59:59 GMT"
    assert (
        r.headers["Link"] == '</api/v1/legacy>; rel="successor-version"'
    )


# ---------------------------------------------------------------------------
# Integration — confirm main app ships the middleware
# ---------------------------------------------------------------------------

def test_main_app_installs_deprecation_middleware():
    # main.py imports the middleware via `app.core.deprecation` while
    # this test file imports via `shoplift_detector.app.core.deprecation`.
    # Those are two distinct module objects under Python's import
    # system (conftest.py sys.path trick), so compare by qualname.
    from shoplift_detector.main import app

    qualnames = [m.cls.__qualname__ for m in app.user_middleware]
    assert "DeprecationHeadersMiddleware" in qualnames


@pytest.mark.asyncio
async def test_legacy_health_route_is_not_deprecated_on_main_app(client):
    # /health is a legacy root route but intentionally excluded from
    # the deprecation map (it's still the canonical liveness probe).
    response = await client.get("/health")
    assert "Deprecation" not in response.headers
