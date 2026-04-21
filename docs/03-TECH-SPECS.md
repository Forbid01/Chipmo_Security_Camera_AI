# 03 — Техникийн тодорхойлолтууд (Tech Specs)

Компонент бүрийн нарийн техник шаардлагa, interface, код байрлал,
тестлэх хуурай шалгуур.

---

## 1. Alert Deduplication

### Зорилго
Нэг event дээр олон alert явуулахыг зогсоох.

### Одоогийн асуудал
150-frame accumulator нь threshold-с удаа дараа хэтэрч олон alert trigger хийх боломжтой.

### Шийдэл

**State machine per `(camera_id, person_id)`:**

```python
class AlertState(Enum):
    IDLE = "idle"          # Alert илгээгдээгүй
    ACTIVE = "active"      # Alert илгээгдсэн, event үргэлжилж байна
    COOLDOWN = "cooldown"  # Alert илгээсэн, 60 сек хүлээх
    RESOLVED = "resolved"  # User label дуусгасан
```

**Transitions:**
- `IDLE + score > threshold` → send alert, `ACTIVE`
- `ACTIVE + event ended (no person)` → `COOLDOWN` for 60s
- `COOLDOWN + timer expired` → `IDLE`
- `COOLDOWN + score > threshold + same person_id` → **NO ALERT**
- `*` + user label → `RESOLVED` (archived)

### Storage

```sql
CREATE TABLE alert_state (
    id BIGSERIAL PRIMARY KEY,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    person_track_id INT NOT NULL,
    state VARCHAR(16) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_trigger_at TIMESTAMPTZ NOT NULL,
    cooldown_expires_at TIMESTAMPTZ,
    alert_id BIGINT REFERENCES alerts(id),
    UNIQUE (camera_id, person_track_id, started_at)
);

CREATE INDEX idx_alert_state_camera ON alert_state (camera_id, state);
```

### Файлын байршил

- Service: `shoplift_detector/app/services/alert_manager.py`
- Migration: `alembic/versions/xxxx_add_alert_state.py`
- Test: `tests/services/test_alert_manager.py`

### Acceptance

- Нэг person_id-д нэг event дээр яг 1 Telegram илгээгдэнэ
- 60 сек cooldown-ны дотор дахин trigger болсон ч alert гарахгүй
- Unit test coverage ≥ 90%

---

## 2. ByteTrack Tuning

### Зорилго
Хүний ID frame хооронд алдагдахгүй барих.

### Шийдэл

`shoplift_detector/app/config/tracker.yaml` (шинээр үүсгэнэ):

```yaml
tracker_type: bytetrack
track_high_thresh: 0.6  # was 0.5
track_low_thresh: 0.1
new_track_thresh: 0.7
track_buffer: 60        # was 30 (frames)
match_thresh: 0.8
fuse_score: true
```

### Rationale

- `track_high_thresh: 0.6` — илүү итгэлтэй detection-ийг л active track болгоно
- `track_buffer: 60` — хүн түр харагдахгүй болоход 2 секунд (30 FPS) хүртэл ID хадгална
- `fuse_score: true` — detection + tracking score-уудыг нэгтгэнэ

### Acceptance

- Pilot data дээр ID алдагдал rate 5%-аас доош
- 2 секундийн дотор дахин орж ирсэн хүний ID ижил байна

---

## 3. Metrics & Observability

### Зорилго
Бодит цагийн system health, accuracy-г мониторинг хийх.

### Prometheus metrics

```python
# shoplift_detector/observability/metrics.py

from prometheus_client import Counter, Histogram, Gauge

alerts_total = Counter(
    "chipmo_alerts_total",
    "Total alerts triggered",
    ["store_id", "camera_id", "alert_type"]
)

false_positives_total = Counter(
    "chipmo_false_positives_total",
    "Alerts labeled as false positive by users",
    ["store_id"]
)

true_positives_total = Counter(
    "chipmo_true_positives_total",
    "Alerts confirmed as theft by users",
    ["store_id"]
)

inference_latency = Histogram(
    "chipmo_inference_latency_seconds",
    "End-to-end inference latency",
    ["camera_id", "stage"],  # stage: yolo, reid, rag, vlm
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

gpu_memory_used_bytes = Gauge(
    "chipmo_gpu_memory_used_bytes",
    "GPU memory usage",
    ["gpu_id"]
)

camera_fps = Gauge(
    "chipmo_camera_fps",
    "Current FPS per camera",
    ["camera_id"]
)

camera_online = Gauge(
    "chipmo_camera_online",
    "1 if camera is streaming, 0 otherwise",
    ["camera_id"]
)
```

### Grafana dashboard

**Panels:**
1. Alert rate (per store, per hour)
2. False positive rate (rolling 7-day, per store)
3. GPU memory / utilization
4. Inference latency (p50, p95, p99)
5. Camera uptime (heatmap: camera_id × time)
6. Camera FPS distribution

Dashboard JSON: `observability/grafana/chipmo-dashboard.json`

### Docker compose (dev)

```yaml
services:
  prometheus:
    image: prom/prometheus:v2.50.0
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.3.0
    volumes:
      - grafana-data:/var/lib/grafana
      - ./observability/grafana/provisioning:/etc/grafana/provisioning
    ports:
      - "3001:3000"

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
```

### Acceptance

- Prometheus-д бүх metric 5 сек-д нэг scrape болно
- Grafana dashboard-д бүх panel харагдана
- Alert rate-ийг тухайн секундээс харагдана

---

## 4. Night Mode Adaptive Threshold

### Зорилго
Бага гэрэлтэй орчинд (шөнө) pose detection-ийн буурсан accuracy-г compensate хийх.

### Шийдэл

**Brightness detection:**

```python
import cv2
import numpy as np

def compute_brightness(frame: np.ndarray) -> float:
    """Returns mean luminance (0-255)"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))

NIGHT_THRESHOLD_LUMINANCE = 60.0  # tunable
```

**Adaptive parameters:**

```python
@dataclass
class DetectionConfig:
    base_threshold: float = 100.0  # accumulator threshold
    night_multiplier: float = 1.3

    # Signal weights
    looking_around_weight: float = 1.5
    looking_around_night_factor: float = 0.7

    # ... other signals

    def for_conditions(self, brightness: float) -> "DetectionConfig":
        if brightness < NIGHT_THRESHOLD_LUMINANCE:
            return DetectionConfig(
                base_threshold=self.base_threshold * self.night_multiplier,
                looking_around_weight=self.looking_around_weight * self.looking_around_night_factor,
                # ... adjust other weights
            )
        return self
```

### Файлын байршил

- Module: `shoplift_detector/app/ai/adaptive_config.py`
- Tests: `tests/ai/test_adaptive_config.py`
- Config: `shoplift_detector/app/config/detection.yaml` (base values, шинээр үүсгэнэ)

### Acceptance

- Шөнийн цагт FP rate өдрийн FP rate-ийн 1.2x-аас их биш
- Brightness detection 100ms-д 1 удаа тооцно (FPS-д нөлөөлөхгүй)

---

## 5. OSNet Re-ID

### Зорилго
Олон камер хоорондын хүнийг таних.

### Шийдэл

**Model choice:** `osnet_x0_25` (жижиг model, 512-dim embedding, ~2.8M param)

```python
# shoplift_detector/app/ai/reid.py

import torch
import torchreid
from torchreid.utils import FeatureExtractor

class ReIDExtractor:
    def __init__(self, device: str = "cuda"):
        self.extractor = FeatureExtractor(
            model_name="osnet_x0_25",
            model_path="models/osnet_x0_25_imagenet.pth",
            device=device,
        )

    def extract(self, person_crop: np.ndarray) -> np.ndarray:
        """Returns 512-dim embedding"""
        features = self.extractor(person_crop)
        return features.cpu().numpy()[0]

    def extract_batch(self, crops: List[np.ndarray]) -> np.ndarray:
        """Batched extraction"""
        features = self.extractor(crops)
        return features.cpu().numpy()
```

### Qdrant collection (per store)

```python
collection_name = f"store_{store_id}_reid"
vector_params = VectorParams(
    size=512,
    distance=Distance.COSINE,
)

# TTL policy (Qdrant-д built-in TTL байхгүй, manual cleanup)
# Worker: хуучин > 2 цаг embedding-ийг delete
```

### Cross-camera matching

```python
def match_across_cameras(
    new_embedding: np.ndarray,
    store_id: str,
    threshold: float = 0.85,
) -> Optional[str]:
    results = qdrant.search(
        collection_name=f"store_{store_id}_reid",
        query_vector=new_embedding,
        limit=1,
    )
    if results and results[0].score > threshold:
        return results[0].payload["person_id"]
    return None
```

### Acceptance

- 1 crop → embedding < 10ms (GPU)
- Qdrant query < 20ms
- Demo дэлгүүр (4 камер)-д 95%+ accuracy per track

---

## 6. RAG Case Memory

### Зорилго
Өмнөх confirmed case-уудтай харьцуулж худал alert дарах.

### Case schema

```python
@dataclass
class CaseEmbedding:
    case_id: UUID
    store_id: UUID
    camera_id: UUID
    timestamp: datetime

    # Components
    pose_vector: np.ndarray   # 256-dim (PCA-аар reduce-ээс төлөв эмбэдд)
    clip_vector: np.ndarray   # 512-dim (CLIP image embedding)
    behavior_vector: np.ndarray  # 6-dim (behavior signal scores)

    # Combined
    combined_vector: np.ndarray  # 768-dim (concat + normalize)

    # Metadata
    label: Literal["theft", "false_positive", "unlabeled"]
    confidence: float
    clip_path: str
```

### Qdrant schema

```python
collection_name = f"store_{store_id}_cases"

VectorParams(
    size=768,
    distance=Distance.COSINE,
)

# Payload:
{
    "case_id": "...",
    "camera_id": "...",
    "timestamp": "2026-04-17T14:23:41Z",
    "label": "false_positive",
    "confidence": 0.92,
    "behavior_scores": [0.2, 0.8, 0.1, ...],
    "clip_path": "s3://...",
}
```

### Check pipeline

```python
# shoplift_detector/app/ai/rag_check.py

def should_suppress_alert(
    case: CaseEmbedding,
    store_id: str,
    top_k: int = 5,
    fp_threshold: float = 0.8,
) -> Tuple[bool, Optional[str]]:
    """
    Return (suppress, reason).
    Suppress if 2+ of top-3 are labeled false_positive with sim > 0.8.
    """
    results = qdrant.search(
        collection_name=f"store_{store_id}_cases",
        query_vector=case.combined_vector,
        limit=top_k,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="label",
                    match=MatchValue(value="false_positive"),
                )
            ]
        ),
    )

    high_sim_fps = [r for r in results[:3] if r.score > fp_threshold]
    if len(high_sim_fps) >= 2:
        ids = [r.payload["case_id"] for r in high_sim_fps]
        return True, f"Similar to FP cases: {ids}"
    return False, None
```

### Файлын байршил

- Module: `shoplift_detector/app/ai/rag_check.py`
- Schema: `shoplift_detector/app/models/case.py` эсвэл SQLAlchemy model бол `shoplift_detector/app/db/models/case.py`
- Seeding script: `scripts/seed_rag_from_feedback.py`
- Test: `tests/ai/test_rag_check.py`

### Acceptance

- Pilot pilot data-гаар FP rate 40%+ буурна
- RAG query p95 < 50ms
- Initial seed: бүх одоогийн labeled event Qdrant-д

---

## 7. VLM Verification Layer

### Зорилго
Rule + RAG-аар суьлсэн case-ыг финал confirm хийх.

### Model

**Qwen2.5-VL 7B** (Ollama-аар serve)
- Quantization: Q4_K_M (~5 GB VRAM)
- Latency target: p95 < 1 секунд

### API client

```python
# shoplift_detector/app/ai/vlm_client.py

import httpx
from pydantic import BaseModel

class VLMVerdict(BaseModel):
    is_suspicious: bool
    confidence: float  # 0-1
    reason: str

class VLMClient:
    def __init__(self, base_url: str = "http://ollama:11434"):
        self.base_url = base_url
        self.model = "qwen2.5vl:7b-q4_k_m"

    async def verify(
        self,
        keyframes: List[bytes],  # 3-5 images
        behavior_description: str,
    ) -> VLMVerdict:
        prompt = self._build_prompt(behavior_description)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [base64.b64encode(f).decode() for f in keyframes],
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
            )
            data = response.json()["response"]
            return VLMVerdict.model_validate_json(data)

    def _build_prompt(self, description: str) -> str:
        return f"""Та CCTV камерын зургийг шинжилж байгаа security AI.

Илэрсэн зан байдал:
{description}

Дараах зургуудыг хараад энэ хүн хулгайлж байна уу гэдгийг тогтоо.

Хариулт JSON форматаар:
{{
  "is_suspicious": true/false,
  "confidence": 0-1,
  "reason": "Монгол хэлээр товч тайлбар"
}}
"""
```

### Integration point

Pipeline-д RAG check-ийн дараагаар:

```python
async def process_event(event: SuspiciousEvent) -> AlertDecision:
    # Layer 1: Rule-based (already done, event reached here)

    # Layer 2: RAG
    suppress, reason = should_suppress_alert(event.case, event.store_id)
    if suppress:
        return AlertDecision(action="suppress", reason=reason)

    # Layer 3: VLM
    verdict = await vlm_client.verify(
        keyframes=event.keyframes,
        behavior_description=event.behavior_text,
    )
    if verdict.confidence < 0.5:
        return AlertDecision(action="suppress", reason=verdict.reason)

    return AlertDecision(action="alert", reason=verdict.reason, vlm_confidence=verdict.confidence)
```

### Acceptance

- p95 latency < 1 секунд
- Pilot data-гаар rule-only-оос FP rate 70%+ буурна
- Hallucination rate < 5% (manual spot-check)

---

## 8. Dynamic FPS Controller

### Зорилго
GPU load-ийг идэвхгүй үед багасгах.

### State machine

```
     ┌──────┐      person detected    ┌────────┐
     │ IDLE │ ─────────────────────→  │ ACTIVE │
     │ 3FPS │                          │ 15 FPS │
     └──────┘ ←──────── 60s no person ─┴────┬───┘
                                            │ behavior score > 0.4
                                            ▼
                                      ┌──────────┐
                                      │SUSPICIOUS│
                                      │  30 FPS  │
                                      └──────────┘
                                            ▲
                                            │ 10s normal
                                            │
                                         back to ACTIVE
```

### Implementation

```python
# shoplift_detector/app/streaming/fps_controller.py

class FPSController:
    def __init__(self):
        self.state = "idle"
        self.last_person_seen = None
        self.last_suspicious = None
        self.target_fps = 3

    def update(self, has_person: bool, behavior_score: float):
        now = time.time()

        if has_person:
            self.last_person_seen = now

        if behavior_score > 0.4:
            self.last_suspicious = now

        # State transitions
        if self.last_suspicious and (now - self.last_suspicious) < 10:
            new_state = "suspicious"
            self.target_fps = 30
        elif self.last_person_seen and (now - self.last_person_seen) < 60:
            new_state = "active"
            self.target_fps = 15
        else:
            new_state = "idle"
            self.target_fps = 3

        if new_state != self.state:
            logger.info(f"FPS state: {self.state} → {new_state}")
            self.state = new_state
```

### Integration

Camera reader-д FPS sleep хоорондын интервал-г `1/target_fps`-д тохируулна.

### Acceptance

- GPU load дундажлаарлагаар 50%+ хэмнэгдэнэ
- Transition latency < 100ms
- Suspicious event-ийг дутуу frame-аар миссэгдэхгүй

---

## 9. Batched Inference

### Зорилго
GPU forward pass нэг дор олон камерт ажиллуулж throughput нэмэгдүүлэх.

### Implementation

```python
# shoplift_detector/app/ai/batch_inference.py

import asyncio
from collections import defaultdict

class BatchInferenceEngine:
    def __init__(
        self,
        model,
        max_batch_size: int = 8,
        max_wait_ms: int = 100,
    ):
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.queue: List[Tuple[str, np.ndarray, asyncio.Future]] = []
        self.lock = asyncio.Lock()

    async def predict(self, camera_id: str, frame: np.ndarray) -> dict:
        future = asyncio.Future()
        async with self.lock:
            self.queue.append((camera_id, frame, future))
            if len(self.queue) >= self.max_batch_size:
                await self._flush()

        # Timeout flush
        asyncio.create_task(self._timeout_flush())
        return await future

    async def _timeout_flush(self):
        await asyncio.sleep(self.max_wait_ms / 1000)
        async with self.lock:
            if self.queue:
                await self._flush()

    async def _flush(self):
        if not self.queue:
            return
        batch = self.queue[:]
        self.queue.clear()

        frames = np.stack([b[1] for b in batch])
        results = self.model(frames)  # batched forward

        for (cam_id, _, fut), res in zip(batch, results):
            fut.set_result(res)
```

### Acceptance

- Throughput 3x+ сайжирна (4-8 камертай тест)
- Latency overhead < 50ms

---

## 10. TensorRT Optimization

### Зорилго
Model forward pass-ийг FP16 TensorRT engine-аар 2-3x хурдлуулах.

### YOLO export

```bash
yolo export model=yolo11s-pose.pt format=engine half=True device=0
# Output: yolo11s-pose.engine
```

### OSNet export (ONNX → TRT)

```python
import torch
from torchreid.utils import FeatureExtractor

extractor = FeatureExtractor(model_name="osnet_x0_25", ...)
dummy_input = torch.randn(1, 3, 256, 128).cuda()

torch.onnx.export(
    extractor.model,
    dummy_input,
    "osnet_x0_25.onnx",
    input_names=["input"],
    output_names=["embedding"],
    dynamic_axes={"input": {0: "batch"}, "embedding": {0: "batch"}},
    opset_version=17,
)
```

```bash
trtexec --onnx=osnet_x0_25.onnx --saveEngine=osnet.trt --fp16
```

### Runtime integration

`shoplift_detector/app/ai/trt_runtime.py` — TRT engine loader.

### Acceptance

- YOLO inference 2x+ хурдан (A100 / RTX 5060 benchmark)
- Accuracy-д нөлөө < 0.5% mAP

---

## 11. Active Learning UI

### Зорилго
Харилцагчаас тодорхой бус case-ууд label авах.

### Backend API

```python
# shoplift_detector/app/api/v1/labels.py

@router.get("/labels/pending")
async def list_pending_labels(store_id: UUID, limit: int = 20):
    """
    Return top N uncertain cases for user to label.
    Uncertainty = |vlm_confidence - 0.5| inverse.
    """
    return await label_service.get_pending(store_id, limit)

@router.post("/labels/{case_id}")
async def submit_label(case_id: UUID, label: LabelInput):
    """
    label: "theft" | "false_positive" | "not_sure" | "skip"
    """
    return await label_service.submit(case_id, label)
```

### Frontend

- Route: `/labels/pending`
- Mobile-first design
- Preview: 5-sec looped clip + key frame
- 4 larger buttons: Thief / Not thief / Not sure / Skip
- Progress: "5/20 labeled, 3 more to unlock auto-tune"

### Retrain trigger

- 20 new labels → Bayesian opt weight tune
- 50 new labels → full retrain job

### Acceptance

- 1 case дээр label өгөхөд ≤ 5 секунд
- Mobile-д responsive
- Label-ийн дараа RAG-д шинэ case нэмэгдэнэ

---

## 12. Edge-Central Sync Protocol

### Зорилго
Харилцагчийн edge box-д хууч мэдээлэлтэй ажиллахаас хамгаалах.

### Endpoints (Central)

```
POST /api/edge/register
  → edge_box-ийг бүртгэнэ, token буцаана

POST /api/edge/heartbeat
  → edge status, metrics

POST /api/edge/alerts
  → new alert + clip upload

GET /api/edge/sync-pack
  → latest weights + Qdrant snapshot URL

POST /api/edge/feedback-upload
  → user labels (if any collected locally)
```

### Sync pack structure

```
sync_pack_{store_id}_{version}.tar.gz
├── manifest.json
├── weights.json          # behavior signal weights
├── detection_config.yaml # adaptive thresholds
├── qdrant_snapshot.bin   # store-specific case DB
├── vlm_prompts.yaml      # any new prompt templates
└── signature.sig         # HMAC-SHA256
```

### Rollout

- Edge pulls sync pack weekly
- Atomic swap (download → verify → replace)
- Rollback if validation fails

### Acceptance

- Sync doesn't interrupt alert pipeline
- 3-version backward compatibility
- Signature verification 100%

---

## 13. Privacy Components

### Face blur (per-store toggle)

```python
# shoplift_detector/app/ai/privacy.py

def blur_faces(frame: np.ndarray, pose_result) -> np.ndarray:
    """Blur face bbox in frame using pose keypoints."""
    for person in pose_result:
        nose = person.keypoints[0]
        ears = person.keypoints[3:5]
        if all(k.confidence > 0.5 for k in [nose, *ears]):
            x_min = int(min(k.x for k in ears) - 20)
            y_min = int(nose.y - 50)
            x_max = int(max(k.x for k in ears) + 20)
            y_max = int(nose.y + 30)
            region = frame[y_min:y_max, x_min:x_max]
            frame[y_min:y_max, x_min:x_max] = cv2.GaussianBlur(region, (51, 51), 0)
    return frame
```

### Clip encryption at rest

- AES-256-GCM
- Key per store (stored in Vault / sealed secret)
- Decryption only during label viewing (audit logged)

### Audit log

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(64),  -- view_clip, download_clip, label_clip
    resource_type VARCHAR(32),
    resource_id UUID,
    ip_address INET,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

### Acceptance

- Face blur option бүр харилцагчид toggle
- Clip at-rest encryption верификация
- Audit log-г 1 жил хадгална

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [02-ROADMAP.md](./02-ROADMAP.md)
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md)
- [06-DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md)

---

Updated: 2026-04-20
