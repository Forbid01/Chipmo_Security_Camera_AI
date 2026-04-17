# 02 — Хөгжүүлэлтийн Roadmap

## Зорилго

Одоогийн архитектураас target архитектур руу шилжих ажлын
4 үе шаттай төлөвлөгөө. Тохирох sprint/week тус бүрд нь хуваарилагдсан.

---

## Phase 1 — Quick Wins (2 долоо хоног)

Яаралтай засах ёстой, өндөр impact-тай жижиг шинэчлэлүүд. Одоогийн
pilot-ын чанарыг шууд сайжруулна.

### Sprint 1.1 (1 долоо хоног)

- [ ] **Alert dedup fix**
  - Cooldown per `person_id`: 60 сек
  - `alert_state` table (active/cooldown/resolved)
  - Backend: `shoplift_detector/services/alert_manager.py`
  - Acceptance: Нэг event дээр Telegram 1 удаа л очно

- [ ] **ByteTrack параметр tune**
  - `track_high_thresh: 0.5 → 0.6`
  - `track_buffer: 30 → 60`
  - `match_thresh: 0.8` (keep)
  - Config: `shoplift_detector/config/tracker.yaml`
  - Acceptance: Хүний ID алдагдах rate < 5% (одоо магадгүй 10-20%)

- [ ] **Metrics endpoint нэмэх**
  - `/metrics` endpoint (Prometheus format)
  - Core metrics:
    - `alerts_total{store_id, type}` counter
    - `false_positives_total{store_id}` counter
    - `inference_latency_seconds{camera_id}` histogram
    - `gpu_memory_bytes` gauge
  - Docker compose-д Prometheus + Grafana-г дотоод service болгож нэмнэ
  - Acceptance: Grafana dashboard-д бодит FP rate/store харагдана

### Sprint 1.2 (1 долоо хоног)

- [ ] **Night mode adaptive threshold**
  - Brightness detection (frame mean lumens)
  - Threshold < 60 lumens → "night mode" activate
  - Night mode-д: accumulator threshold ×1.3, `looking_around` weight ×0.7
  - Acceptance: Шөнийн цагт FP rate өдрийнхөөс 20% дээш биш

- [ ] **Camera disconnect handling**
  - RTSP disconnect → exponential backoff (1s, 2s, 4s, 8s, max 60s)
  - 5+ минут offline → харилцагч руу notification
  - Heartbeat табл `camera_health(camera_id, last_seen, status)`
  - Acceptance: Сервер тал камер offline-ийг 30 сек дотор мэдэж байна

- [ ] **Clip retention policy**
  - Normal clip: 48h TTL
  - Alert clip: 30 хоног
  - Feedback label-тэй clip: unlimited (флаг)
  - Cron job: daily cleanup
  - Acceptance: Disk usage тогтвортой, өсөхгүй

---

## Phase 2 — Core AI упgrade (4-6 долоо хоног)

Detection accuracy-г онцгой ахиулна. False positive 50%+ буурна.

### Sprint 2.1 — Re-ID (2 долоо хоног)

- [ ] **OSNet integration**
  - `torchreid` install
  - Model: `osnet_x0_25` (жижиг, 512-dim embedding)
  - Hook: YOLO detection → crop → OSNet → embedding
  - Module: `shoplift_detector/ai/reid.py`
  - Acceptance: 1 crop-д < 10ms embedding

- [ ] **Per-store Qdrant setup**
  - Docker compose-д Qdrant service
  - Collection per store: `store_{store_id}_reid`
  - 512-dim, cosine similarity
  - TTL: 2 цаг (working memory)
  - Acceptance: Insert + query < 20ms

- [ ] **Cross-camera ID merge**
  - Same-store, different cameras → ID харилцан таних
  - Similarity threshold: 0.85
  - Merged ID-г frontend-д харуулах (track history)
  - Acceptance: Харилцагч манай demo-д 4 камертай дэлгүүрт 1 хүнийг бүх камерт нэг ID-тэй харна

### Sprint 2.2 — RAG Case Memory (2 долоо хоног)

- [ ] **Case embedding schema**
  - Feature vector: pose sequence (150-frame) + behavior scores + crop CLIP embedding
  - Combined 768-dim (pose 256 + CLIP 512 aligned)
  - Collection: `store_{store_id}_cases`
  - Metadata: `{label, timestamp, camera_id, confidence}`

- [ ] **RAG check при alert**
  - Сэжигтэй event → top-5 similar case query
  - Хэрэв top-3-ын 2+ нь `false_positive` label, similarity > 0.8 → suppress
  - Module: `shoplift_detector/ai/rag_check.py`
  - Acceptance: Pilot data-гаар FP rate 40%+ буурна

- [ ] **Case DB populate (initial seed)**
  - Одоогийн нийт feedback label-тай event-үүдийг embedding → Qdrant
  - Migration script: `scripts/seed_rag_from_feedback.py`
  - Acceptance: Бүх existing label-тай case Qdrant-д орсон

### Sprint 2.3 — Dynamic FPS + Batched Inference (2 долоо хоног)

- [ ] **Dynamic FPS controller**
  - States: idle (3 FPS) / active (15 FPS) / suspicious (30 FPS)
  - Transition:
    - idle → active: person detected
    - active → suspicious: behavior score > 0.4
    - суспийс → active: 10 сек normal
    - active → idle: 60 сек no person
  - Module: `shoplift_detector/streaming/fps_controller.py`
  - Acceptance: GPU load дундажлаарлагаар 50%+ хэмнэгдэнэ

- [ ] **Batched inference**
  - Multiple camera frames буферлэнэ (max 100ms wait)
  - Batch size: 4-8 (GPU capacity-аар)
  - Module: `shoplift_detector/ai/batch_inference.py`
  - Acceptance: Throughput 3x+ сайжирна

---

## Phase 3 — Advanced AI (2-3 сар)

VLM-р verification нэмж, active learning feedback loop-ыг сэргээнэ.

### Sprint 3.1 — VLM Verification (3 долоо хоног)

- [ ] **Ollama + Qwen2.5-VL 7B setup**
  - Docker service
  - Model download + quantization (Q4_K_M → ~5GB VRAM)
  - API wrapper: `shoplift_detector/ai/vlm_client.py`

- [ ] **VLM prompt template**
  - Монгол + англи prompt template
  - Input: 3-5 keyframe crop + pose sequence text description
  - Output schema: `{is_suspicious: bool, confidence: 0-1, reason: str}`
  - Test set: 50+ pilot clip дээр accuracy хэмжинэ

- [ ] **VLM verification step integrate**
  - RAG-аар suppress болоогүй case → VLM
  - VLM confidence < 0.5 → alert дарангал
  - Latency: p95 < 1000ms
  - Acceptance: End-to-end FP rate rule-only-оос 70%+ буурна

### Sprint 3.2 — Active Learning UI (2 долоо хоног)

- [ ] **Uncertainty scoring**
  - Case бүрт uncertainty score: |VLM_confidence - 0.5|-ын инверс
  - High-uncertainty event-ийг "needs label" queue-д оруулна

- [ ] **Label UI (React)**
  - "Shuud label" mobile-friendly page
  - 1-click: Thief / Not thief / Not sure / Skip
  - 5-10 second clip + keyframe preview
  - Route: `/labels/pending`
  - Acceptance: Харилцагч 1 харилцагч 5 мин дээр 20+ label өгч чадна

- [ ] **Feedback → retrain pipeline**
  - Weekly cron: `scripts/retrain.py`
  - Per-store weight tuning (bayesian optimization)
  - Hard negative mining: FP clip-ийг "seed negative" болгож Qdrant-д
  - Sync pack generation: `{store_id}_sync_{timestamp}.tar.gz`

### Sprint 3.3 — TensorRT Optimization (1-2 долоо хоног)

- [ ] **YOLO TensorRT export**
  - `model.export(format="engine", half=True)`
  - Edge box-д cached TRT engine build
  - Acceptance: Inference 2x+ хурдан болно

- [ ] **OSNet TensorRT**
  - ONNX → TensorRT conversion
  - Acceptance: Re-ID latency 50% буурна

- [ ] **Benchmark doc**
  - Before/after table all камер count-ээр
  - Artifact: `docs/benchmarks/phase3.md`

---

## Phase 4 — Edge Migration + Scale (3-4 сар)

Centralized архитектураас Hybrid edge-д шилжинэ. Linear scale боломж.

### Sprint 4.1 — Edge Box Specification (2 долоо хоног)

- [ ] **Hardware BOM lock**
  - RTX 5060 8GB / Ryzen 5 / 32GB RAM / 1TB NVMe / Mini-ITX case
  - Target BOM cost: < 2.2 сая₮
  - Vendor: 2-3 өрсөлдөгч сонголт
  - Doc: `docs/04-EDGE-DEPLOYMENT.md`

- [ ] **Edge OS image**
  - Ubuntu 22.04 Server base
  - NVIDIA driver + CUDA + Docker
  - Pre-installed containers (YOLO, Qdrant, Ollama, ingest)
  - WireGuard VPN client pre-configured
  - Acceptance: Шинэ edge box-ийг 30 мин дотор provision хийнэ

### Sprint 4.2 — Edge-Central Communication (3 долоо хоног)

- [ ] **Protocol design**
  - WireGuard VPN tunnel (харилцагч internet → төв)
  - gRPC эсвэл REST (зөвөлж REST: simpler)
  - Messages:
    - Edge → Central: alert, metrics, health
    - Central → Edge: sync_pack, config_update
  - Doc: `docs/api/edge-central-protocol.md`

- [ ] **Offline-first mode**
  - Edge internet тасрахад: local queue-д alert хадгална
  - Reconnect-д батч upload
  - Acceptance: 24h offline-ийг тогтонс даана

- [ ] **Sync pack pull**
  - Edge: weekly cron
  - HTTPS download + verify signature
  - Rolling update (YOLO model, weights, Qdrant snapshot)
  - Acceptance: Sync-ийн үед alert ажил тасралтгүй

### Sprint 4.3 — Migration Tool (2 долоо хоног)

- [ ] **Migration script**
  - Current store → Edge box deployment
  - Camera stream-ийг LAN-руу re-point
  - 24h dual-write (центр + edge both process)
  - Validation: event count тааж байна уу
  - Cutover: edge-г primary болгоно
  - Doc: `docs/05-MIGRATION-PLAN.md`

- [ ] **Harilтsagch handbook**
  - "Edge box-ийг яаж суулгах" PDF
  - Video tutorial: 10 мин
  - Acceptance: Харилцагчдын IT гишүүд өөрсдөө суулгаж чадна

### Sprint 4.4 — Federated Learning (3 долоо хоног)

- [ ] **Privacy-safe aggregation**
  - Face/body не сгоняются төвд, зөвхөн embedding
  - Differential privacy epsilon = 1.0
  - Doc: `docs/privacy/federated-spec.md`

- [ ] **Cross-store pattern DB**
  - Төв Qdrant-д shared collection: `global_patterns`
  - "Монголын 20 дэлгүүрт түгээмэл хулгайлах pattern"
  - New store join хийхэд этот seed болгоно

---

## Мөрдөх indicator-ууд (metrics)

Phase бүрийн төгсгөлд дараах хэмжилтүүдийг бодит дата дээр баталгаажуулна:

| Metric | Baseline | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|---|
| False positive rate | ~30% | 25% | 15% | 7% | 5% |
| Missed theft rate | Unknown | hэмж | <20% | <10% | <5% |
| GPU load (avg) | 80-90% | 70% | 50% | 40% | 30% (per edge) |
| Alert latency (p95) | ~2s | 1.5s | 1.2s | 1.5s (VLM-тэй) | 1s (edge) |
| Cameras per GPU | 5-10 | 8-12 | 15-20 | 20-25 | N/A (edge/store) |
| Bandwidth/камер | 2-5 Mbps | 2-5 Mbps | 2-5 Mbps | 2-5 Mbps | <100 kbps |
| Onboard time (new store) | Days | Days | Hours | Hours | < 2 цаг |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| VLM latency too high | Med | High | Quantization + async queue, fallback to rule-only |
| Edge hardware supply | Med | High | 2-3 vendor, buffer stock 5 box |
| Харилцагчийн internet тогтворгүй | High | Med | Offline-first edge design |
| Federated learning privacy regression | Low | Critical | DP + lawyer review |
| Qwen Монгол хэл accuracy чанар багатай | Med | Med | Prompt tuning + fallback English |

---

## Resource allocation

**Team size ишлэл:**
- 1-2 AI/ML engineer (Phase 2, 3)
- 1 DevOps/Infra engineer (Phase 1, 4)
- 1 Full-stack engineer (UI, API — бүх phase)
- Product/founder (prioritization, pilot feedback)

**Budget ишлэл** (Phase 4 хүртэл):
- Hardware (central GPU RTX 5090): ~3-4 сая₮
- Edge box prototype (3 ширхэг): ~6-7 сая₮
- Software (бүгд open source): 0
- Cloud (optional S3 backup): ~$20-50/сар

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) — Архитектур дэлгэрэнгүй
- [03-TECH-SPECS.md](./03-TECH-SPECS.md) — Компонент спец
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md) — Edge BOM
- [05-MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md) — Migration алхмууд

---

Updated: 2026-04-17
