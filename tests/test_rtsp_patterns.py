"""T4-10 — RTSP URL pattern catalog tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHOPLIFT = ROOT / "shoplift_detector"
if str(SHOPLIFT) not in sys.path:
    sys.path.insert(0, str(SHOPLIFT))

os.environ.setdefault("SECRET_KEY", "test-secret")

from shoplift_detector.app.services import rtsp_patterns  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    rtsp_patterns.load_patterns.cache_clear()
    yield
    rtsp_patterns.load_patterns.cache_clear()


def test_catalog_json_parses_and_has_manufacturers():
    data = rtsp_patterns.load_patterns()
    assert data["version"] == 1
    assert len(data["manufacturers"]) >= 5


@pytest.mark.parametrize("mfg_id", [
    "hikvision", "dahua", "axis", "uniview", "tplink", "generic",
])
def test_required_manufacturers_present(mfg_id):
    assert rtsp_patterns.get_manufacturer(mfg_id) is not None


class TestMatchByOui:
    def test_hikvision_oui_matches(self):
        entry = rtsp_patterns.match_by_oui("4C:BD:8F:11:22:33")
        assert entry is not None and entry["id"] == "hikvision"

    def test_dashes_instead_of_colons(self):
        """MAC may arrive as `aa-bb-cc-dd-ee-ff` from Windows tooling."""
        entry = rtsp_patterns.match_by_oui("3C-EF-8C-AA-BB-CC")
        assert entry is not None and entry["id"] == "dahua"

    def test_no_separator(self):
        entry = rtsp_patterns.match_by_oui("00408CDEADBE")
        assert entry is not None and entry["id"] == "axis"

    def test_case_insensitive(self):
        entry = rtsp_patterns.match_by_oui("4c:bd:8f:11:22:33")
        assert entry is not None and entry["id"] == "hikvision"

    def test_unknown_returns_none(self):
        """We deliberately do NOT fall back to generic here — callers
        need to know when a MAC is unrecognized so they can log +
        retry later."""
        assert rtsp_patterns.match_by_oui("FF:FF:FF:00:00:00") is None

    def test_short_input_returns_none(self):
        assert rtsp_patterns.match_by_oui("abc") is None


class TestCandidateUrls:
    def test_hikvision_urls_rendered(self):
        urls = rtsp_patterns.candidate_urls(
            "hikvision", ip="192.168.1.50", user="admin", password="pw"
        )
        # Both patterns resolve.
        assert len(urls) == 2
        # Score ordering — modern ISAPI path first.
        assert urls[0] == "rtsp://admin:pw@192.168.1.50:554/Streaming/Channels/101"
        assert "/h264/ch1/main/av_stream" in urls[1]

    def test_port_override(self):
        urls = rtsp_patterns.candidate_urls(
            "dahua", ip="10.0.0.5", user="admin", password="x", port=10554
        )
        assert urls[0].startswith("rtsp://admin:x@10.0.0.5:10554/")

    def test_unknown_falls_back_to_generic(self):
        """Unknown manufacturer IDs still return SOMETHING — otherwise
        the camera add flow dead-ends on unrecognized vendors."""
        urls = rtsp_patterns.candidate_urls(
            "no-such-vendor", ip="1.2.3.4", user="u", password="p"
        )
        assert urls, "expected generic fallback"
        assert "onvif/profile1" in urls[0] or "live" in urls[-1]

    def test_ordering_is_deterministic(self):
        """Two calls with the same args must return the exact same
        list — the UI ranks suggestions by position and random jitter
        would confuse users."""
        args = {"ip": "1.1.1.1", "user": "u", "password": "p"}
        first = rtsp_patterns.candidate_urls("axis", **args)
        second = rtsp_patterns.candidate_urls("axis", **args)
        assert first == second


class TestCredentialHints:
    def test_hikvision_has_hints(self):
        hints = rtsp_patterns.credential_hints("hikvision")
        assert hints, "hikvision must carry at least one hint"
        for h in hints:
            assert {"username", "password", "note"}.issubset(h)

    def test_unknown_returns_empty(self):
        assert rtsp_patterns.credential_hints("nope") == []


class TestListManufacturers:
    def test_returns_hint_stripped(self):
        """UI-safe listing must not leak factory-default credentials —
        those belong in failure-message hints only (T4-14)."""
        entries = rtsp_patterns.list_manufacturers()
        assert entries
        for entry in entries:
            assert "credential_hints" not in entry
            assert "patterns" not in entry


def test_env_override_path(tmp_path, monkeypatch):
    """RTSP_PATTERNS_PATH env override lets on-prem operators ship a
    patched catalog without rebuilding the image."""
    minimal = {
        "version": 1,
        "manufacturers": [
            {
                "id": "only-one",
                "display_name": "Only",
                "oui_prefixes": ["11:22:33"],
                "default_port": 554,
                "patterns": [
                    {
                        "template": "rtsp://{user}:{password}@{ip}:{port}/only",
                        "score": 100,
                    }
                ],
                "credential_hints": [],
            }
        ],
    }
    override = tmp_path / "patterns.json"
    override.write_text(json.dumps(minimal), encoding="utf-8")

    monkeypatch.setenv("RTSP_PATTERNS_PATH", str(override))
    rtsp_patterns.load_patterns.cache_clear()

    assert rtsp_patterns.get_manufacturer("only-one") is not None
    # The baked-in hikvision entry is now invisible — env override wins.
    assert rtsp_patterns.get_manufacturer("hikvision") is None
