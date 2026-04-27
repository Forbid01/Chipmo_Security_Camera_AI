"""Standalone Qwen2.5-VL HTTP microservice.

Runs on the user's own GPU host. Exposes a single authenticated
endpoint that the main Chipmo backend calls when an alert needs VLM
verification:

    POST /vlm/describe
      Authorization: Bearer <VLM_API_KEY>
      { "description": "...", "image_jpeg_b64": "..." }

    → 200 OK
      { "caption": "...", "confidence": 0.0..1.0,
        "reasoning": {...}, "latency_ms": 1234, "model_name": "..." }

Why a separate process instead of the full main app?
  - The full app pulls in torch, ultralytics, asyncpg, alembic, slowapi,
    sentry-sdk, etc. None of that is needed on the GPU host. Keeping
    this microservice minimal means a smaller image and a smaller
    attack surface on the box that holds the heaviest model weights.
  - The GPU host can be deployed independently (RunPod, your own rack,
    a campus server) and scaled / replaced without touching the API
    tier on Railway.

Env vars:
  - VLM_API_KEY     — shared bearer token (REQUIRED). The service
                       refuses to start without it so a misconfigured
                       deploy can't expose Qwen to the open internet.
  - VLM_MODEL_NAME  — default "Qwen/Qwen2.5-VL-7B-Instruct"
  - VLM_DEVICE      — "cuda" / "cuda:0" / "cpu" (cpu only useful for
                       smoke tests; 7B on CPU is unusable in practice)
  - VLM_DTYPE       — "bfloat16" / "float16" / "float32"
  - VLM_MAX_NEW_TOKENS — default 256
  - HF_HOME         — model cache location (default /root/.cache/huggingface)

Run:
  uvicorn vlm_server.main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
from typing import Any

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vlm_server")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VLM_API_KEY = os.environ.get("VLM_API_KEY", "").strip()
VLM_MODEL_NAME = os.environ.get("VLM_MODEL_NAME", "Qwen/Qwen2.5-VL-7B-Instruct")
VLM_DEVICE = os.environ.get("VLM_DEVICE", "cuda")
VLM_DTYPE = os.environ.get("VLM_DTYPE", "bfloat16")
VLM_MAX_NEW_TOKENS = int(os.environ.get("VLM_MAX_NEW_TOKENS", "256"))

if not VLM_API_KEY:
    raise RuntimeError(
        "VLM_API_KEY env var is required — refusing to start an "
        "unauthenticated VLM endpoint. Set the same shared secret on "
        "both the main app and this server."
    )


# ---------------------------------------------------------------------------
# Model load (lazy + thread-safe)
# ---------------------------------------------------------------------------

_model: Any = None
_processor: Any = None
_load_lock = threading.Lock()
_inference_semaphore = asyncio.Semaphore(1)


def _ensure_loaded() -> None:
    global _model, _processor
    if _model is not None and _processor is not None:
        return
    with _load_lock:
        if _model is not None and _processor is not None:
            return

        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        torch_dtype = dtype_map.get(VLM_DTYPE, torch.bfloat16)

        logger.info(
            "Loading VLM %s on %s (dtype=%s)", VLM_MODEL_NAME, VLM_DEVICE, VLM_DTYPE
        )
        _processor = AutoProcessor.from_pretrained(VLM_MODEL_NAME)
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            VLM_MODEL_NAME,
            torch_dtype=torch_dtype,
            device_map=VLM_DEVICE,
        )
        _model.eval()


# ---------------------------------------------------------------------------
# Prompt + parsing (kept identical to the in-process service so swapping
# between local / remote leaves the verdict shape unchanged)
# ---------------------------------------------------------------------------

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


def _parse_model_output(raw: str) -> dict[str, Any]:
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


def _decode_jpeg_b64(b64: str) -> np.ndarray:
    raw = base64.b64decode(b64, validate=False)
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(
            status_code=400, detail="Could not decode image_jpeg_b64"
        )
    return frame


def _run_inference_sync(frame: np.ndarray, description: str) -> tuple[str, int]:
    _ensure_loaded()
    import torch
    from PIL import Image

    rgb = frame[:, :, ::-1] if frame.ndim == 3 and frame.shape[2] == 3 else frame
    image = Image.fromarray(rgb)
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
    inputs = _processor(text=[text], images=[image], return_tensors="pt").to(
        VLM_DEVICE
    )
    started = time.monotonic()
    with torch.inference_mode():
        generated = _model.generate(
            **inputs, max_new_tokens=VLM_MAX_NEW_TOKENS, do_sample=False
        )
    trimmed = generated[:, inputs["input_ids"].shape[1]:]
    output = _processor.batch_decode(trimmed, skip_special_tokens=True)[0]
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return output, elapsed_ms


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Chipmo VLM (Qwen2.5-VL)",
    version="1.0.0",
    docs_url="/docs",
)


_bearer = HTTPBearer(auto_error=False)


def _require_api_key(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    if creds.credentials != VLM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )


class DescribeRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=4000)
    image_jpeg_b64: str = Field(..., min_length=1)


class DescribeResponse(BaseModel):
    caption: str
    confidence: float
    reasoning: dict
    latency_ms: int
    model_name: str


@app.get("/health")
async def health() -> dict:
    """Liveness probe. Loaded model state is reported but not blocked
    on — the model is lazy-loaded so a fresh container is healthy
    before the first inference."""
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model_name": VLM_MODEL_NAME,
        "device": VLM_DEVICE,
    }


@app.post(
    "/vlm/describe",
    response_model=DescribeResponse,
    dependencies=[Depends(_require_api_key)],
)
async def vlm_describe(payload: DescribeRequest) -> DescribeResponse:
    """One-shot VLM verification. Serializes inference behind a
    semaphore so two concurrent calls on a single GPU don't OOM each
    other; the main app's own timeout will tear down stragglers."""
    frame = _decode_jpeg_b64(payload.image_jpeg_b64)
    async with _inference_semaphore:
        raw, latency_ms = await asyncio.to_thread(
            _run_inference_sync, frame, payload.description
        )
    parsed = _parse_model_output(raw)
    confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
    return DescribeResponse(
        caption=str(parsed.get("caption", "")),
        confidence=confidence,
        reasoning=parsed,
        latency_ms=latency_ms,
        model_name=VLM_MODEL_NAME,
    )
