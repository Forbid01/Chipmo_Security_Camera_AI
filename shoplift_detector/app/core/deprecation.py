"""Deprecation / Sunset header framework.

Per docs/07-API-SPEC.md §9. A deprecated endpoint emits three HTTP
response headers on every call:

    Deprecation: true
    Sunset: <RFC 7231 IMF-fixdate>
    Link: </api/v2/...>; rel="successor-version"

`Deprecation` is an IETF draft (draft-ietf-httpapi-deprecation-header),
`Sunset` is RFC 8594, and `Link rel=successor-version` is RFC 5988.
Prometheus-scraped clients, SDK generators, and humans following the
`Link` can all consume the same headers.

Usage — declarative:

    from app.core.deprecation import deprecated_endpoint

    @app.get("/alerts")
    @deprecated_endpoint(successor="/api/v1/alerts", sunset="2027-12-31")
    async def legacy_alerts(...):
        ...

The decorator wraps the endpoint in a FastAPI dependency that appends
the headers to the response. It works for sync and async handlers.

Usage — programmatic (for middleware-style application to a whole
router or a legacy mount):

    from app.core.deprecation import apply_deprecation_headers

    apply_deprecation_headers(
        response,
        successor="/api/v1/alerts",
        sunset="2027-12-31",
    )
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any, TypeVar

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

F = TypeVar("F", bound=Callable[..., Any])


# Default sunset horizon for legacy root routes that are shadowed by a
# /api/v1/* equivalent. Callers can override per-endpoint.
DEFAULT_SUNSET_DATE: datetime = datetime(2027, 12, 31, 23, 59, 59, tzinfo=UTC)


def format_sunset(value: datetime | str | None) -> str | None:
    """Produce an RFC 7231 IMF-fixdate string from a datetime or ISO date.

    Returns None when the input is None so callers can pass the arg
    through without branching.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Accept bare dates (YYYY-MM-DD) as end-of-day UTC.
        if len(value) == 10:
            value = f"{value}T23:59:59+00:00"
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return format_datetime(value, usegmt=True)


def apply_deprecation_headers(
    response: Response,
    *,
    successor: str | None = None,
    sunset: datetime | str | None = None,
) -> None:
    """Attach Deprecation / Sunset / Link headers to `response`.

    Every header is additive and idempotent — re-applying overwrites
    rather than appending, so the helper is safe to call from both a
    decorator and a middleware on the same response.
    """
    response.headers["Deprecation"] = "true"

    sunset_str = format_sunset(sunset if sunset is not None else DEFAULT_SUNSET_DATE)
    if sunset_str:
        response.headers["Sunset"] = sunset_str

    if successor:
        # RFC 5988 Link header syntax; the URI is wrapped in angle
        # brackets and params are semicolon-separated.
        response.headers["Link"] = f'<{successor}>; rel="successor-version"'


def deprecated_endpoint(
    *,
    successor: str | None = None,
    sunset: datetime | str | None = None,
) -> Callable[[F], F]:
    """Decorator that appends deprecation headers to an endpoint's response.

    Expects the wrapped function to accept a FastAPI `Response` via
    dependency injection; if the signature does not already declare
    one, the decorator injects it.
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        has_response_param = any(
            p.annotation is Response or p.name == "response"
            for p in sig.parameters.values()
        )

        if has_response_param:
            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    response: Response | None = kwargs.get("response")
                    if response is None:
                        for arg in args:
                            if isinstance(arg, Response):
                                response = arg
                                break
                    result = await func(*args, **kwargs)
                    if response is not None:
                        apply_deprecation_headers(
                            response, successor=successor, sunset=sunset
                        )
                    return result

                async_wrapper.__signature__ = sig  # type: ignore[attr-defined]
                return async_wrapper  # type: ignore[return-value]

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                response: Response | None = kwargs.get("response")
                if response is None:
                    for arg in args:
                        if isinstance(arg, Response):
                            response = arg
                            break
                result = func(*args, **kwargs)
                if response is not None:
                    apply_deprecation_headers(
                        response, successor=successor, sunset=sunset
                    )
                return result

            sync_wrapper.__signature__ = sig  # type: ignore[attr-defined]
            return sync_wrapper  # type: ignore[return-value]

        # No Response param: inject one via a new parameter. FastAPI
        # recognizes `Response` annotations and supplies the current
        # response object automatically.
        new_params = list(sig.parameters.values()) + [
            inspect.Parameter(
                "_deprecation_response",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Response,
            )
        ]
        new_sig = sig.replace(parameters=new_params)

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def injected_async(*args, **kwargs):
                response = kwargs.pop("_deprecation_response")
                result = await func(*args, **kwargs)
                apply_deprecation_headers(
                    response, successor=successor, sunset=sunset
                )
                return result

            injected_async.__signature__ = new_sig  # type: ignore[attr-defined]
            return injected_async  # type: ignore[return-value]

        @functools.wraps(func)
        def injected_sync(*args, **kwargs):
            response = kwargs.pop("_deprecation_response")
            result = func(*args, **kwargs)
            apply_deprecation_headers(
                response, successor=successor, sunset=sunset
            )
            return result

        injected_sync.__signature__ = new_sig  # type: ignore[attr-defined]
        return injected_sync  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Middleware — path-based deprecation map
# ---------------------------------------------------------------------------

# Legacy → successor URL map for endpoints that predate /api/v1. The
# middleware looks up the incoming request path here and appends the
# deprecation headers to the response. Using path matching lets us
# deprecate existing routes without editing every decorator in
# main.py.
#
# Keys ending with `/` are treated as prefixes; exact matches come
# first. Path parameters are normalized by prefix-checking on the
# static portion (e.g. "/video_feed/" matches "/video_feed/42").
LEGACY_DEPRECATION_MAP: dict[str, str] = {
    "/token": "/api/v1/auth/token",
    "/register": "/api/v1/auth/register",
    "/users/me": "/api/v1/auth/me",
    "/alerts": "/api/v1/alerts",
    "/video_feed": "/api/v1/video/feed",
    "/video_feed/": "/api/v1/video/feed/",
    "/forgot-password": "/api/v1/auth/forgot-password",
    "/verify-code": "/api/v1/auth/verify-code",
    "/reset-password": "/api/v1/auth/reset-password",
}


def resolve_successor(
    path: str, mapping: dict[str, str] = LEGACY_DEPRECATION_MAP
) -> str | None:
    """Return the successor URL for `path`, or None if not deprecated.

    Exact matches win over prefix matches. Prefix entries end in `/`
    and the trailing segment of the incoming path is appended to the
    successor.
    """
    if path in mapping:
        return mapping[path]
    for legacy_prefix, successor_prefix in mapping.items():
        if not legacy_prefix.endswith("/"):
            continue
        if path.startswith(legacy_prefix):
            tail = path[len(legacy_prefix):]
            return successor_prefix + tail
    return None


class DeprecationHeadersMiddleware(BaseHTTPMiddleware):
    """Appends Deprecation/Sunset/Link headers to legacy route responses.

    Inspects the inbound request path against `LEGACY_DEPRECATION_MAP`
    (overridable via constructor). When the path is deprecated, calls
    `apply_deprecation_headers` on the outbound response with the
    configured default sunset date.
    """

    def __init__(
        self,
        app,
        *,
        mapping: dict[str, str] | None = None,
        sunset: datetime | str | None = None,
    ):
        super().__init__(app)
        self._mapping = mapping if mapping is not None else LEGACY_DEPRECATION_MAP
        self._sunset = sunset if sunset is not None else DEFAULT_SUNSET_DATE

    async def dispatch(
        self, request: Request, call_next
    ) -> StarletteResponse:
        response = await call_next(request)
        successor = resolve_successor(request.url.path, self._mapping)
        if successor is not None:
            apply_deprecation_headers(
                response, successor=successor, sunset=self._sunset
            )
        return response
