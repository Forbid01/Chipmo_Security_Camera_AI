"""Qwen2.5-VL inference service for alert verification.

The model is heavy (7B params) and slow (1-5s per call on a single
GPU) so the service is designed around three guarantees:

1. **Lazy load.** The transformers import and `from_pretrained` calls
   only run on first inference, so dev machines without a GPU and the
   unit-test runner never need the wheels installed.

2. **Single inference at a time.** A semaphore serializes calls. Two
   concurrent VLM forwards on a single GPU OOM faster than they speed
   anything up; we'd rather queue.

3. **Hard timeout.** Each `describe_alert` call is wrapped in
   `asyncio.wait_for`. A hung VLM must never block the alert pipeline
   — the orchestrator treats a timeout as a "not_run" verdict and the
   alert continues without VLM verification.

Output contract: `describe_alert` returns a `VlmVerdict` with a
free-text caption, a confidence float in [0, 1], and a structured
`reasoning` dict (the parsed JSON the model was prompted to emit). The
confidence is what the orchestrator compares against
`vlm_confidence_threshold`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


_model: Any = None
_processor: Any = None
_load_lock = threading.Lock()
_inference_semaphore = asyncio.Semaphore(1)


@dataclass
class VlmVerdict:
    caption: str
    confidence: float
    reasoning: dict[str, Any]
    latency_ms: int
    model_name: str


_PROMPT_TEMPLATE = """You are a security camera reviewer. The YOLO + behavior pipeline flagged this frame as a possible shoplifting incident.

Alert description from the upstream pipeline:
{description}

Look at the image and answer in **strict JSON** with this exact schema:
{{
  "is_shoplifting": <true | false>,
  "confidence": <float between 0 and 1>,
  "caption": "<one sentence describing what the person is doing>",
  "evidence": ["<short bullet>", "<short bullet>"]
}}

Rules:
- Only return the JSON object, no prose around it.
- `confidence` is your confidence that this is a real shoplifting event.
- If you cannot tell, set confidence below 0.4 and explain why in `evidence`.
"""


def _ensure_loaded() -> None:
    """Load Qwen2.5-VL on first use. Holds a thread lock so two
    concurrent first-callers don't race the model into GPU memory twice.

    Raises ImportError with an actionable message when transformers
    isn't installed (the main app's requirements.txt deliberately
    excludes it — only the GPU host's vlm_server/ image carries the
    wheel). Most Railway-style deployments use VLM_REMOTE_URL and
    never reach this code path.
    """
    global _model, _processor
    if _model is not None and _processor is not None:
        return
    with _load_lock:
        if _model is not None and _processor is not None:
            return

        import torch
        try:
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        except ImportError as exc:
            raise ImportError(
                "In-process VLM requires `transformers` + `accelerate`, "
                "which the main app deliberately omits to keep the "
                "Railway build under the timeout. Either install "
                "vlm_server/requirements.txt locally, or set "
                "VLM_REMOTE_URL to a vlm_server/ instance running on "
                "your GPU host."
            ) from exc

        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        torch_dtype = dtype_map.get(settings.VLM_DTYPE, torch.bfloat16)

        logger.info(
            "Loading VLM %s on %s (dtype=%s)",
            settings.VLM_MODEL_NAME,
            settings.VLM_DEVICE,
            settings.VLM_DTYPE,
        )
        _processor = AutoProcessor.from_pretrained(settings.VLM_MODEL_NAME)
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            settings.VLM_MODEL_NAME,
            torch_dtype=torch_dtype,
            device_map=settings.VLM_DEVICE,
        )
        _model.eval()


def _frame_to_pil(frame: "np.ndarray"):
    """Convert a BGR cv2 frame to a PIL.Image in RGB."""
    from PIL import Image

    if frame.ndim == 3 and frame.shape[2] == 3:
        # cv2 returns BGR; PIL expects RGB.
        rgb = frame[:, :, ::-1]
    else:
        rgb = frame
    return Image.fromarray(rgb)


def _parse_model_output(raw: str) -> dict[str, Any]:
    """Extract the JSON object from the model's reply.

    Qwen sometimes wraps its JSON in markdown fences or adds a sentence
    of preamble despite the prompt — strip both before json.loads. On
    parse failure we return a low-confidence fallback so the orchestrator
    can still write a row instead of dropping the result.
    """
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {
            "is_shoplifting": False,
            "confidence": 0.0,
            "caption": raw[:200],
            "evidence": ["model returned no JSON"],
        }
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {
            "is_shoplifting": False,
            "confidence": 0.0,
            "caption": raw[:200],
            "evidence": ["model returned invalid JSON"],
        }
    parsed.setdefault("is_shoplifting", False)
    parsed.setdefault("confidence", 0.0)
    parsed.setdefault("caption", "")
    parsed.setdefault("evidence", [])
    return parsed


def _run_inference_sync(frame: "np.ndarray", description: str) -> tuple[str, int]:
    _ensure_loaded()
    import torch

    image = _frame_to_pil(frame)
    prompt = _PROMPT_TEMPLATE.format(description=description)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    text = _processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _processor(
        text=[text], images=[image], return_tensors="pt"
    ).to(settings.VLM_DEVICE)

    started = time.monotonic()
    with torch.inference_mode():
        generated = _model.generate(
            **inputs,
            max_new_tokens=settings.VLM_MAX_NEW_TOKENS,
            do_sample=False,
        )
    # Strip the prompt tokens so we only decode the model's reply.
    trimmed = generated[:, inputs["input_ids"].shape[1]:]
    output = _processor.batch_decode(trimmed, skip_special_tokens=True)[0]
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return output, elapsed_ms


async def _describe_remote(
    *, frame: "np.ndarray", description: str
) -> VlmVerdict:
    """POST the frame to the remote VLM microservice.

    The image is JPEG-encoded + base64'd inline rather than uploaded as
    multipart so retries / logging are easier (one JSON body per call).
    JPEG quality 85 keeps the payload ~50-100KB for a 1080p frame which
    is well below typical request size caps.
    """
    import base64

    import cv2
    import httpx

    if not settings.VLM_API_KEY:
        # Fail closed — running remote VLM unauthenticated would expose
        # the GPU endpoint to the public internet.
        raise RuntimeError(
            "VLM_REMOTE_URL is set but VLM_API_KEY is empty. "
            "Set the shared secret on both the main app and the GPU host."
        )

    ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG for remote VLM")
    payload = {
        "description": description,
        "image_jpeg_b64": base64.b64encode(jpeg.tobytes()).decode("ascii"),
    }
    headers = {"Authorization": f"Bearer {settings.VLM_API_KEY}"}
    url = settings.VLM_REMOTE_URL.rstrip("/") + "/vlm/describe"

    async with httpx.AsyncClient(
        timeout=settings.VLM_TIMEOUT_SECONDS
    ) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()

    confidence = max(0.0, min(1.0, float(body.get("confidence", 0.0))))
    return VlmVerdict(
        caption=str(body.get("caption", "")),
        confidence=confidence,
        reasoning=body.get("reasoning") or {},
        latency_ms=int(body.get("latency_ms") or 0),
        model_name=str(body.get("model_name") or settings.VLM_MODEL_NAME),
    )


async def describe_alert(
    *,
    frame: "np.ndarray",
    description: str,
) -> VlmVerdict:
    """Run Qwen2.5-VL on one alert frame.

    Routes to either the in-process model (`_run_inference_sync`) or the
    remote `vlm_server/` microservice depending on `VLM_REMOTE_URL`.
    Raises asyncio.TimeoutError on overrun; the orchestrator catches
    that and downgrades the verdict to "not_run".
    """
    if not settings.VLM_ENABLED:
        return VlmVerdict(
            caption="",
            confidence=0.0,
            reasoning={"reason": "VLM disabled"},
            latency_ms=0,
            model_name=settings.VLM_MODEL_NAME,
        )

    # Remote mode — production deployment with main app on a small box
    # and the GPU on a separate host.
    if settings.VLM_REMOTE_URL:
        return await asyncio.wait_for(
            _describe_remote(frame=frame, description=description),
            timeout=settings.VLM_TIMEOUT_SECONDS,
        )

    # Local mode — single-box dev / GPU-attached deployments.
    async def _run() -> VlmVerdict:
        async with _inference_semaphore:
            raw, latency_ms = await asyncio.to_thread(
                _run_inference_sync, frame, description
            )
        parsed = _parse_model_output(raw)
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        return VlmVerdict(
            caption=str(parsed.get("caption", "")),
            confidence=confidence,
            reasoning=parsed,
            latency_ms=latency_ms,
            model_name=settings.VLM_MODEL_NAME,
        )

    return await asyncio.wait_for(_run(), timeout=settings.VLM_TIMEOUT_SECONDS)
