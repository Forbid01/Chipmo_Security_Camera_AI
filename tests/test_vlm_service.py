"""Tests for `vlm_service` that DON'T require GPU / transformers.

We exercise:
- `_parse_model_output` against the messy reality of LLM JSON replies
  (markdown fences, missing keys, malformed JSON, stray prose) — these
  are the failure modes seen in production prompts.
- The `VLM_ENABLED=False` short-circuit path of `describe_alert`,
  which must return a clean "not run" verdict without touching the GPU.
- Frame conversion (BGR → RGB → PIL) so a regression in cv2 channel
  ordering surfaces here instead of as garbled VLM input.
"""

import numpy as np
import pytest

from shoplift_detector.app.services import vlm_service


# ---------------------------------------------------------------------------
# JSON parser robustness
# ---------------------------------------------------------------------------


def test_parse_clean_json():
    raw = (
        '{"is_shoplifting": true, "confidence": 0.82, '
        '"caption": "Person concealing item", "evidence": ["a", "b"]}'
    )
    parsed = vlm_service._parse_model_output(raw)
    assert parsed["is_shoplifting"] is True
    assert parsed["confidence"] == 0.82
    assert parsed["caption"] == "Person concealing item"
    assert parsed["evidence"] == ["a", "b"]


def test_parse_strips_markdown_fence():
    """Qwen often wraps JSON in ```json … ``` despite the prompt rule."""
    raw = (
        "Here's my analysis:\n```json\n"
        '{"is_shoplifting": false, "confidence": 0.2, "caption": "OK", "evidence": []}'
        "\n```"
    )
    parsed = vlm_service._parse_model_output(raw)
    assert parsed["is_shoplifting"] is False
    assert parsed["confidence"] == 0.2


def test_parse_handles_missing_keys():
    raw = '{"caption": "just a caption"}'
    parsed = vlm_service._parse_model_output(raw)
    assert parsed["is_shoplifting"] is False
    assert parsed["confidence"] == 0.0
    assert parsed["caption"] == "just a caption"
    assert parsed["evidence"] == []


def test_parse_handles_malformed_json():
    raw = "{not valid json at all"
    parsed = vlm_service._parse_model_output(raw)
    assert parsed["confidence"] == 0.0
    assert parsed["is_shoplifting"] is False


def test_parse_handles_no_json_block():
    raw = "I cannot determine from this image."
    parsed = vlm_service._parse_model_output(raw)
    assert parsed["confidence"] == 0.0
    # Caption falls back to a clipped version of the raw output so
    # operators still see *something* in the audit trail.
    assert "cannot determine" in parsed["caption"]


# ---------------------------------------------------------------------------
# describe_alert short-circuit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_alert_short_circuits_when_disabled(monkeypatch):
    """The most common production state on Railway: VLM_ENABLED=False.
    `describe_alert` must return a verdict without loading the model
    or making an inference call — otherwise the import chain alone
    would OOM the container."""
    monkeypatch.setattr(vlm_service.settings, "VLM_ENABLED", False)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    verdict = await vlm_service.describe_alert(frame=frame, description="x")
    assert verdict.confidence == 0.0
    assert verdict.latency_ms == 0
    assert verdict.reasoning == {"reason": "VLM disabled"}


# ---------------------------------------------------------------------------
# Frame conversion
# ---------------------------------------------------------------------------


def test_frame_to_pil_converts_bgr_to_rgb():
    """cv2 hands us BGR; PIL expects RGB. A red pixel in BGR is
    (0, 0, 255). After conversion it must be (255, 0, 0) — getting
    this wrong means the VLM sees blue when the operator sees red."""
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    frame[0, 0] = (0, 0, 255)  # red in BGR
    img = vlm_service._frame_to_pil(frame)
    pixel = img.getpixel((0, 0))
    assert pixel == (255, 0, 0)


# ---------------------------------------------------------------------------
# Remote mode (HTTP to vlm_server microservice)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_alert_routes_to_remote_when_url_set(monkeypatch):
    """When VLM_REMOTE_URL is configured, describe_alert must call out
    over HTTP instead of loading transformers in-process. A regression
    here would cause the main app to OOM trying to load Qwen on a
    machine without a GPU."""
    from unittest.mock import AsyncMock, patch

    monkeypatch.setattr(vlm_service.settings, "VLM_ENABLED", True)
    monkeypatch.setattr(vlm_service.settings, "VLM_REMOTE_URL", "https://vlm.example.com")
    monkeypatch.setattr(vlm_service.settings, "VLM_API_KEY", "test-secret")

    fake_verdict = vlm_service.VlmVerdict(
        caption="remote caption",
        confidence=0.7,
        reasoning={"is_shoplifting": True},
        latency_ms=1500,
        model_name="Qwen/Qwen2.5-VL-7B-Instruct",
    )

    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with patch.object(
        vlm_service, "_describe_remote", AsyncMock(return_value=fake_verdict)
    ) as remote_mock:
        verdict = await vlm_service.describe_alert(
            frame=frame, description="test"
        )
    remote_mock.assert_awaited_once()
    assert verdict.caption == "remote caption"


@pytest.mark.asyncio
async def test_remote_mode_refuses_without_api_key(monkeypatch):
    """Fail-closed: the remote URL is set but the bearer secret isn't.
    Better to crash loudly here than silently expose the GPU endpoint
    to anyone who finds the URL."""
    monkeypatch.setattr(vlm_service.settings, "VLM_API_KEY", "")
    monkeypatch.setattr(vlm_service.settings, "VLM_REMOTE_URL", "https://x.example")
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="VLM_API_KEY"):
        await vlm_service._describe_remote(frame=frame, description="x")
