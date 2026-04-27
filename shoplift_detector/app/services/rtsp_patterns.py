"""Loader + matcher for the RTSP URL pattern catalog (T4-10).

The catalog lives next to this module as `rtsp_patterns.json` so it
is shipped verbatim in every image and operators can override it with
an environment variable in air-gapped deployments.

Three public affordances:

* `load_patterns()` — returns the parsed catalog, cached.
* `match_by_oui(mac)` — maps a MAC OUI prefix to the manufacturer
  record. Used by the ONVIF probe (T4-09) once a device is discovered.
* `candidate_urls(manufacturer_id, ip, user, password, port=None)` —
  materializes the RTSP URL list for a given manufacturer, ordered
  by score (highest first).
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path(__file__).with_name("rtsp_patterns.json")


def _catalog_path() -> Path:
    override = os.environ.get("RTSP_PATTERNS_PATH")
    return Path(override) if override else DEFAULT_CATALOG_PATH


@lru_cache(maxsize=1)
def load_patterns() -> dict[str, Any]:
    """Read + parse the JSON catalog. Cached for the life of the
    process; operators needing a hot-reload can call `load_patterns.cache_clear()`.
    """
    path = _catalog_path()
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "manufacturers" not in data:
        raise ValueError(
            f"rtsp_patterns catalog at {path} missing top-level 'manufacturers' key"
        )
    return data


def list_manufacturers() -> list[dict[str, Any]]:
    """Convenience: return every manufacturer record with credential
    hints stripped (safe for UI display)."""
    catalog = load_patterns()
    return [
        {
            "id": m["id"],
            "display_name": m["display_name"],
            "oui_prefixes": list(m.get("oui_prefixes", [])),
            "default_port": int(m.get("default_port", 554)),
        }
        for m in catalog["manufacturers"]
    ]


def _normalize_oui(value: str) -> str:
    """Strip everything that isn't hex, uppercase, and return the
    first three octets (6 hex chars). Handles MACs in the common
    forms `aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`, `aabbccddeeff`.
    """
    hex_only = "".join(ch for ch in value if ch.isalnum()).upper()
    return hex_only[:6]


def match_by_oui(mac_or_oui: str) -> dict[str, Any] | None:
    """Return the manufacturer record whose OUI list contains the
    given MAC's first three octets, or None. Falls back to the
    `generic` entry only at call sites that want it — this function
    returns None when nothing matched so callers can still log the
    miss.
    """
    needle = _normalize_oui(mac_or_oui)
    if len(needle) < 6:
        return None
    catalog = load_patterns()
    for entry in catalog["manufacturers"]:
        for prefix in entry.get("oui_prefixes", []):
            if _normalize_oui(prefix) == needle:
                return entry
    return None


def get_manufacturer(manufacturer_id: str) -> dict[str, Any] | None:
    catalog = load_patterns()
    for entry in catalog["manufacturers"]:
        if entry["id"] == manufacturer_id:
            return entry
    return None


def candidate_urls(
    manufacturer_id: str,
    *,
    ip: str,
    user: str,
    password: str,
    port: int | None = None,
) -> list[str]:
    """Produce the RTSP URL list for a manufacturer, highest-score
    first. Unknown manufacturers fall back to `generic`.

    The returned list is what the agent iterates through when the
    customer has not yet supplied a vendor-specific URL.
    """
    entry = get_manufacturer(manufacturer_id) or get_manufacturer("generic")
    if entry is None:
        return []
    port = int(port or entry.get("default_port", 554))

    urls: list[tuple[int, str]] = []
    for pattern in entry.get("patterns", []):
        template = pattern["template"]
        score = int(pattern.get("score", 0))
        variables = {
            "user": user,
            "password": password,
            "ip": ip,
            "port": port,
        }
        variables.update(pattern.get("variables", {}) or {})
        try:
            url = template.format(**variables)
        except KeyError as exc:  # missing variable in template
            logger.warning(
                "rtsp_pattern_unresolved",
                extra={
                    "manufacturer": manufacturer_id,
                    "template": template,
                    "missing": str(exc),
                },
            )
            continue
        urls.append((score, url))

    urls.sort(key=lambda pair: (-pair[0], pair[1]))
    return [url for _, url in urls]


def credential_hints(manufacturer_id: str) -> list[dict[str, Any]]:
    """Return the `[{username, password, note}]` hint list for UI
    display in test-connection failure messages (T4-14)."""
    entry = get_manufacturer(manufacturer_id)
    if entry is None:
        return []
    return [dict(hint) for hint in entry.get("credential_hints", [])]


__all__ = [
    "candidate_urls",
    "credential_hints",
    "get_manufacturer",
    "list_manufacturers",
    "load_patterns",
    "match_by_oui",
]
