"""Prometheus `/metrics` scrape endpoint.

Thin wrapper around `app.observability.CHIPMO_REGISTRY` (T02-08). The
registry owns state; this module only exposes it in OpenMetrics text
format at two paths:

  - GET /metrics           (convention root; what Prometheus scrapers
                           default to)
  - GET /api/v1/metrics   (versioned alias; keeps the route discoverable
                           under the existing /api/v1 surface)

Both paths produce identical output so a Prometheus config can target
either one without duplicating samples. We do not authenticate the
endpoint — restrict access at the network/ingress layer (same pattern
every prom-client service follows).
"""

from app.observability import CHIPMO_REGISTRY
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get(
    "",
    summary="Prometheus metrics (OpenMetrics text format)",
    include_in_schema=False,
)
def metrics_endpoint() -> Response:
    payload = generate_latest(CHIPMO_REGISTRY)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
