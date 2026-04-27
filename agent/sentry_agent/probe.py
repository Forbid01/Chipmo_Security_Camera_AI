"""ONVIF WS-Discovery probe (T4-09).

Discovers IP cameras on the local LAN via the WS-Discovery UDP
multicast protocol (RFC-style ad-hoc, part of the ONVIF Profile S
base). Deliberately uses ONLY the standard library so the Docker
image does not grow another wire-format dependency; `onvif-zeep` is
reserved for follow-up DeviceMgmt calls (T4-11+).

Flow:

1. Craft a WS-Discovery Probe SOAP envelope (ONVIF NetworkVideoTransmitter
   type).
2. Send it to the multicast group 239.255.255.250:3702 from an
   ephemeral UDP socket.
3. Collect ProbeMatch replies for up to `timeout_s` seconds.
4. Parse the `XAddrs` / `Scopes` out of each reply and resolve the
   sender's MAC OUI against the T4-10 pattern catalog.

The probe is read-only — no cameras are modified, no credentials are
attempted. That's deliberate: this function can run under
low-privilege accounts and on untrusted networks (customers
occasionally try it from laptops on random hotel Wi-Fi).
"""

from __future__ import annotations

import logging
import re
import socket
import struct
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("sentry_agent.probe")

WS_DISCOVERY_MCAST_ADDR = "239.255.255.250"
WS_DISCOVERY_PORT = 3702
DEFAULT_TIMEOUT_S = 5.0

# Probe template. The MessageID is randomized per call so replies
# from one probe don't get cross-associated with another that's
# running concurrently on the same host.
_PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:tns="http://schemas.xmlsoap.org/ws/2005/04/discovery"
    xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:MessageID>uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </soap:Header>
  <soap:Body>
    <tns:Probe>
      <tns:Types>dn:NetworkVideoTransmitter</tns:Types>
    </tns:Probe>
  </soap:Body>
</soap:Envelope>"""


@dataclass(frozen=True)
class ProbeResult:
    ip: str
    port: int
    xaddrs: tuple[str, ...]
    scopes: tuple[str, ...]
    manufacturer_id: str | None = None
    manufacturer_display: str | None = None
    model_hint: str | None = None
    mac_oui: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_XADDRS_RE = re.compile(r"<(?:\w+:)?XAddrs>([^<]+)</(?:\w+:)?XAddrs>", re.IGNORECASE)
_SCOPES_RE = re.compile(r"<(?:\w+:)?Scopes>([^<]+)</(?:\w+:)?Scopes>", re.IGNORECASE)
_SCOPE_NAME_RE = re.compile(
    r"onvif://www\.onvif\.org/(?P<kind>name|hardware|location)/(?P<value>[^ /]+)",
    re.IGNORECASE,
)


def _parse_probe_match(body: str) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    """Return (xaddrs, scopes, extras) extracted from a ProbeMatch.

    Using regex rather than a full XML parser keeps the probe cheap
    on constrained edge hardware and sidesteps XML-namespace
    wrangling for a payload we only read a handful of fields from.
    """
    xaddrs: tuple[str, ...] = tuple()
    scopes: tuple[str, ...] = tuple()
    extras: dict[str, Any] = {}

    xaddrs_match = _XADDRS_RE.search(body)
    if xaddrs_match:
        xaddrs = tuple(x for x in xaddrs_match.group(1).split() if x)

    scopes_match = _SCOPES_RE.search(body)
    if scopes_match:
        scopes = tuple(s for s in scopes_match.group(1).split() if s)
        for scope in scopes:
            named = _SCOPE_NAME_RE.match(scope)
            if named:
                extras.setdefault(named.group("kind"), named.group("value"))

    return xaddrs, scopes, extras


def _extract_host(xaddrs: tuple[str, ...]) -> str | None:
    """First XAddr is usually `http://<ip>:<port>/onvif/device_service`.
    We pull the hostname out for matching + UI display."""
    for addr in xaddrs:
        m = re.match(r"^https?://([^/:]+)(?::(\d+))?", addr, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _arp_lookup(ip: str) -> str | None:
    """Best-effort MAC address lookup via the local ARP cache.

    Reading /proc/net/arp (Linux) is the simplest cross-distro route.
    On Windows/macOS the customer's Docker container won't have ARP
    access anyway — those platforms rely on the manufacturer hints
    embedded in the ONVIF Scopes field.
    """
    try:
        with open("/proc/net/arp", "r", encoding="utf-8") as fh:
            for line in fh.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    mac = parts[3]
                    if mac and mac != "00:00:00:00:00:00":
                        return mac
    except OSError:
        pass
    return None


def _enrich_manufacturer(ip: str, extras: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve (manufacturer_id, manufacturer_display, model_hint, mac_oui).

    Tries two paths in order:

    1. MAC OUI lookup via ARP + T4-10 pattern catalog.
    2. ONVIF Scopes hardware/name field, matched against the
       display_name of each manufacturer record.
    """
    # Optional — the backend sync may ship a custom catalog via env,
    # so we defer the import until the probe actually runs.
    try:
        from app.services import rtsp_patterns  # type: ignore[import-not-found]
    except ImportError:
        rtsp_patterns = None  # type: ignore[assignment]

    mac = _arp_lookup(ip)
    mac_oui = mac[:8].upper() if mac else None

    mfg_id: str | None = None
    mfg_display: str | None = None

    if rtsp_patterns is not None and mac:
        entry = rtsp_patterns.match_by_oui(mac)
        if entry is not None:
            mfg_id = entry["id"]
            mfg_display = entry["display_name"]

    hardware = extras.get("hardware") or extras.get("name")
    if rtsp_patterns is not None and mfg_id is None and hardware:
        for entry in rtsp_patterns.list_manufacturers():
            if entry["display_name"].lower().split()[0] in hardware.lower():
                mfg_id = entry["id"]
                mfg_display = entry["display_name"]
                break

    return mfg_id, mfg_display, hardware, mac_oui


# ---------------------------------------------------------------------------
# Socket handling
# ---------------------------------------------------------------------------

def _open_multicast_socket(*, bind_host: str = "") -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Linux supports SO_REUSEPORT; BSD/macOS needs it for concurrent probes.
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    # Cap the TTL so the probe doesn't leak onto upstream networks —
    # default=1 restricts to the immediate LAN segment.
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.bind((bind_host, 0))
    return sock


def _listen_for_replies(
    sock: socket.socket,
    *,
    deadline: float,
    max_bytes: int = 65535,
) -> list[tuple[bytes, tuple[str, int]]]:
    replies: list[tuple[bytes, tuple[str, int]]] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(remaining)
        try:
            data, addr = sock.recvfrom(max_bytes)
        except socket.timeout:
            break
        except OSError as exc:
            logger.warning("probe_socket_error", extra={"error": str(exc)})
            break
        replies.append((data, addr))
    return replies


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def probe(
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    send_socket_factory=_open_multicast_socket,
    now=time.monotonic,
) -> list[ProbeResult]:
    """Send a WS-Discovery probe and return every ProbeMatch reply.

    Args:
        timeout_s: Total wall-clock window we wait for replies. Most
            cameras respond within 1-2s on a quiet LAN; 5s is the
            conservative default. Reduce for CI / test harnesses.
        send_socket_factory: Override for unit tests. Returns an
            already-bound UDP socket.
        now: Monotonic clock; injectable for deterministic tests.

    The return list is deduplicated by (ip, xaddrs) — cameras that
    respond multiple times (e.g. dual-nic boxes) only surface once.
    """
    message_id = uuid.uuid4().hex
    probe_payload = _PROBE_TEMPLATE.format(message_id=message_id).encode("utf-8")

    sock = send_socket_factory()
    try:
        sock.sendto(probe_payload, (WS_DISCOVERY_MCAST_ADDR, WS_DISCOVERY_PORT))
        deadline = now() + timeout_s
        raw_replies = _listen_for_replies(sock, deadline=deadline)
    finally:
        try:
            sock.close()
        except OSError:
            pass

    results: list[ProbeResult] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for body_bytes, (src_ip, _src_port) in raw_replies:
        try:
            body = body_bytes.decode("utf-8", errors="replace")
        except Exception:
            continue
        # Only consume ProbeMatches — random LAN chatter on 3702
        # gets dropped.
        if "ProbeMatch" not in body:
            continue

        xaddrs, scopes, extras = _parse_probe_match(body)
        host = _extract_host(xaddrs) or src_ip
        port_match = re.search(r":(\d+)/", xaddrs[0]) if xaddrs else None
        port = int(port_match.group(1)) if port_match else 80

        dedup_key = (host, xaddrs)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        mfg_id, mfg_display, model_hint, mac_oui = _enrich_manufacturer(host, extras)

        results.append(
            ProbeResult(
                ip=host,
                port=port,
                xaddrs=xaddrs,
                scopes=scopes,
                manufacturer_id=mfg_id,
                manufacturer_display=mfg_display,
                model_hint=model_hint,
                mac_oui=mac_oui,
                extras=extras,
            )
        )

    return results


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ProbeResult",
    "WS_DISCOVERY_MCAST_ADDR",
    "WS_DISCOVERY_PORT",
    "probe",
]


# ---------------------------------------------------------------------------
# For test injection — hand-crafted probe-match payloads
# ---------------------------------------------------------------------------

def _parse_probe_match_body(body: str) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    """Exposed for tests; mirrors `_parse_probe_match`."""
    return _parse_probe_match(body)


# Suppress the dummy IP-packet struct warning on some Python builds —
# the import is declared here purely to keep mypy happy without
# emitting a stub for future IP-layer introspection.
_ = struct
