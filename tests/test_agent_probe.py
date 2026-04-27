"""T4-09 — agent-side ONVIF WS-Discovery probe."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


from sentry_agent import probe  # noqa: E402
from sentry_agent.probe import (  # noqa: E402
    WS_DISCOVERY_MCAST_ADDR,
    WS_DISCOVERY_PORT,
    ProbeResult,
    _parse_probe_match_body,
)


SAMPLE_PROBE_MATCH = b"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:tns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
  </soap:Header>
  <soap:Body>
    <tns:ProbeMatches>
      <tns:ProbeMatch>
        <tns:Scopes>onvif://www.onvif.org/name/HikvisionCam onvif://www.onvif.org/hardware/DS-2CD2385G1</tns:Scopes>
        <tns:XAddrs>http://192.168.1.50:8080/onvif/device_service</tns:XAddrs>
      </tns:ProbeMatch>
    </tns:ProbeMatches>
  </soap:Body>
</soap:Envelope>"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TestProbeMatchParser:
    def test_extracts_xaddrs(self):
        xaddrs, _scopes, _extras = _parse_probe_match_body(
            SAMPLE_PROBE_MATCH.decode()
        )
        assert xaddrs == ("http://192.168.1.50:8080/onvif/device_service",)

    def test_extracts_named_scopes(self):
        _xaddrs, scopes, extras = _parse_probe_match_body(
            SAMPLE_PROBE_MATCH.decode()
        )
        assert any("name/Hikvision" in s for s in scopes)
        assert extras.get("name") == "HikvisionCam"
        assert extras.get("hardware") == "DS-2CD2385G1"

    def test_malformed_payload_returns_empties(self):
        xaddrs, scopes, extras = _parse_probe_match_body("<garbage/>")
        assert xaddrs == ()
        assert scopes == ()
        assert extras == {}

    def test_multiple_xaddrs_preserved(self):
        body = """<tns:XAddrs>http://10.0.0.1/onvif http://10.0.0.2/onvif</tns:XAddrs>"""
        xaddrs, _scopes, _ex = _parse_probe_match_body(body)
        assert xaddrs == (
            "http://10.0.0.1/onvif",
            "http://10.0.0.2/onvif",
        )


# ---------------------------------------------------------------------------
# End-to-end probe — socket + parse
# ---------------------------------------------------------------------------

class _FakeSocket:
    """UDP socket stand-in that returns a scripted reply list."""

    def __init__(self, replies: list[tuple[bytes, tuple[str, int]]]):
        self._replies = list(replies)
        self.sent_packets: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data, addr):
        self.sent_packets.append((data, addr))
        return len(data)

    def settimeout(self, _value):
        pass

    def recvfrom(self, _max_bytes):
        if not self._replies:
            raise socket.timeout()
        return self._replies.pop(0)

    def close(self):
        pass


def test_probe_sends_to_correct_multicast_address():
    sock = _FakeSocket(replies=[])
    probe.probe(timeout_s=0.01, send_socket_factory=lambda: sock)
    assert sock.sent_packets, "probe must send at least one packet"
    _payload, destination = sock.sent_packets[0]
    assert destination == (WS_DISCOVERY_MCAST_ADDR, WS_DISCOVERY_PORT)


def test_probe_payload_targets_networkvideotransmitter():
    sock = _FakeSocket(replies=[])
    probe.probe(timeout_s=0.01, send_socket_factory=lambda: sock)
    payload = sock.sent_packets[0][0].decode()
    assert "NetworkVideoTransmitter" in payload
    assert "Probe" in payload


def test_probe_parses_probematch_into_result():
    sock = _FakeSocket(replies=[
        (SAMPLE_PROBE_MATCH, ("192.168.1.50", 3702))
    ])
    results = probe.probe(timeout_s=0.01, send_socket_factory=lambda: sock)
    assert len(results) == 1
    r = results[0]
    assert r.ip == "192.168.1.50"
    assert r.port == 8080
    assert "http://192.168.1.50:8080/onvif/device_service" in r.xaddrs


def test_probe_ignores_non_probematch_packets():
    """A stray 3702 packet with random XML must not surface as a
    discovered camera."""
    noise = b"<soap:Envelope>unrelated</soap:Envelope>"
    sock = _FakeSocket(replies=[(noise, ("10.0.0.99", 3702))])
    results = probe.probe(timeout_s=0.01, send_socket_factory=lambda: sock)
    assert results == []


def test_probe_deduplicates_identical_responders():
    """Dual-NIC cameras reply twice with the same XAddrs — dashboard
    must not show duplicates."""
    dup = [
        (SAMPLE_PROBE_MATCH, ("192.168.1.50", 3702)),
        (SAMPLE_PROBE_MATCH, ("192.168.1.50", 3702)),
    ]
    sock = _FakeSocket(replies=dup)
    results = probe.probe(timeout_s=0.01, send_socket_factory=lambda: sock)
    assert len(results) == 1


def test_probe_result_serializes():
    r = ProbeResult(ip="10.0.0.1", port=80, xaddrs=("u",), scopes=("s",))
    d = r.as_dict()
    assert d["ip"] == "10.0.0.1"
    assert d["manufacturer_id"] is None


# ---------------------------------------------------------------------------
# CLI integration — sentry-agent probe
# ---------------------------------------------------------------------------

def test_cli_probe_json_empty(monkeypatch, capsys):
    from sentry_agent.cli import main

    monkeypatch.setattr(probe, "probe", lambda *a, **k: [])
    # The CLI imports `probe` lazily — patch both module references.
    import sentry_agent.probe as probe_module
    monkeypatch.setattr(probe_module, "probe", lambda *a, **k: [])

    rc = main(["probe", "--timeout", "0.01", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() in ("[]", "[\n]", "[\n\n]")


def test_cli_probe_text(monkeypatch, capsys):
    from sentry_agent.cli import main

    fake_result = ProbeResult(
        ip="192.168.1.50",
        port=8080,
        xaddrs=("http://192.168.1.50:8080/onvif/device_service",),
        scopes=(),
        manufacturer_display="Hikvision",
        model_hint="DS-2CD2385G1",
    )
    import sentry_agent.probe as probe_module
    monkeypatch.setattr(probe_module, "probe", lambda *a, **k: [fake_result])

    rc = main(["probe", "--timeout", "0.01"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "192.168.1.50" in out
    assert "Hikvision" in out
    assert "DS-2CD2385G1" in out
