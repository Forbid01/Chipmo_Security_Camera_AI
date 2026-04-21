# Chipmo Security AI — Implementation Tasks

Энэ task list нь `docs/01-ARCHITECTURE.md` → `docs/06-DATABASE-SCHEMA.md`
баримтуудаас нэгтгэсэн хэрэгжүүлэлтийн дараалал. Одоогийн centralized
системээс hybrid edge + RAG + VLM + auto-learning архитектур руу эрсдэл
багатай шилжихээр phase/dependency-г барьсан.

> Scope: backend, AI pipeline, DB/schema, observability, edge deployment,
> frontend/admin UI, privacy, migration tooling.
>
> Updated: 2026-04-20

---

## Legend

| Талбар | Тайлбар |
|---|---|
| Priority | P0 = production critical, P1 = foundation, P2 = core feature, P3 = scale/optimization |
| Status | `todo`, `blocked`, `in_progress`, `done` |
| Dependency | Эхлэхээс өмнө дууссан байх ёстой task |

---

## Phase 0 — Baseline Stabilization

Docs дээрх target architecture руу орохоос өмнө одоогийн repo-г хэмжигдэхүйц,
testable, deploy-safe болгоно.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T00-01 | P0 | done | Python runtime/test environment тогтворжуулах | - | Python 3.11 runtime-аар `pytest` ажилладаг, heavy AI imports mock/guard хийгдсэн |
| T00-02 | P0 | done | Backend lint/type baseline засах | T00-01 | `ruff check .` pass эсвэл agreed ignore list-тэй |
| T00-03 | P0 | done | Frontend lint baseline засах | - | `npm run lint` pass |
| T00-04 | P0 | done | Smoke build pipeline баталгаажуулах | T00-01, T00-03 | `npm run build`, backend import smoke, Docker build command documented |
| T00-05 | P1 | done | Docs дахь path/schema naming-г repo-той нийцүүлэх | - | `shoplift_detector/app/...`, `alerts` vs future `alert_events` ялгаа тодорхой |
| T00-06 | P1 | done | Current AS-IS technical inventory document нэмэх | T00-05 | Current endpoints, tables, services, env vars, deployment assumptions documented |

---

## Phase 1 — Quick Wins / Production Critical

Одоогийн centralized систем дээр шууд чанар сайжруулах ажлууд.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T01-01 | P0 | done | Alert dedup state machine хийх | T00-01 | Нэг `(camera_id, person_track_id)` event дээр 1 alert; restart дараа cooldown хадгалагдана |
| T01-02 | P0 | done | `alert_state` DB migration/model/repository нэмэх | T01-01 | active/cooldown/resolved state хадгална, 60 сек cooldown test-тэй |
| T01-03 | P0 | todo | Alert pipeline-г dedup service-р дамжуулах | T01-01, T01-02 | Telegram spam үүсэхгүй; unit test coverage хангалттай |
| T01-04 | P1 | done | ByteTrack config файл нэмэх | T00-01 | `track_high_thresh=0.6`, `track_buffer=60`, `match_thresh=0.8` ашиглагдана |
| T01-05 | P1 | done | Camera disconnect handling сайжруулах | T00-01 | RTSP reconnect exponential backoff, max 60s |
| T01-06 | P1 | done | `camera_health` table + heartbeat update хийх | T01-05 | Offline camera 30 сек дотор илэрнэ, 5+ мин notification hook |
| T01-07 | P1 | done | Clip retention policy хэрэгжүүлэх | T00-01 | Normal 48h, alert 30d, labeled unlimited; daily cleanup job |
| T01-08 | P1 | todo | Store-level AI settings schema нэг мөр болгох | T00-05 | threshold/cooldown/night/FPS/notification config DB + API-аар хадгалагдана |

---

## Phase 2 — Infrastructure Foundation

Metrics, schema, observability, tenant isolation зэргийг AI/edge ажлын өмнө
суурь болгон бэлдэнэ.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T02-01 | P0 | done | New DB schema migration plan lock хийх | T00-05 | Current integer schema-аас future schema руу backward-compatible migration plan |
| T02-02 | P0 | todo | `edge_boxes` migration/model нэмэх | T02-01 | Edge box registration metadata хадгална |
| T02-03 | P0 | done | `cases` metadata table нэмэх | T02-01 | RAG/VLM case metadata PostgreSQL-д joinable |
| T02-04 | P0 | todo | `sync_packs` table нэмэх | T02-01 | Sync pack version/status/signature trace хийгдэнэ |
| T02-05 | P0 | todo | `inference_metrics` table нэмэх | T02-01 | Per-camera FPS/latency metrics хадгална |
| T02-06 | P1 | todo | `audit_log` table нэмэх | T02-01 | Clip view/download/label/config-change audit болно |
| T02-07 | P1 | todo | TimescaleDB integration spike | T02-01 | Hypertable feasibility, local/prod deployment decision documented |
| T02-08 | P1 | todo | Prometheus metrics module нэмэх | T00-01 | alerts, FP/TP, inference latency, GPU, camera FPS/online metrics exposed |
| T02-09 | P1 | todo | `/metrics` endpoint нэмэх | T02-08 | Prometheus format endpoint ажиллана |
| T02-10 | P1 | todo | Dev observability stack нэмэх | T02-09 | docker-compose Prometheus + Grafana + Loki service |
| T02-11 | P1 | todo | Grafana dashboard provisioning | T02-10 | Alert rate, FP rate, GPU, latency, camera uptime panels |
| T02-12 | P0 | todo | Multi-tenant isolation audit хийх | T00-06 | Бүх query org/store filter-тэй эсэх шалгагдсан |
| T02-13 | P1 | todo | RLS strategy / middleware design | T02-12 | PostgreSQL RLS эсвэл app-level guard-ийн decision record |

---

## Phase 3 — Core AI Accuracy

False positive бууруулах, multi-camera identity, context memory нэмэх үндсэн
AI ажлууд.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T03-01 | P1 | todo | Night mode brightness detector хийх | T00-01 | Mean luminance тооцно, threshold default 60 |
| T03-02 | P1 | todo | Adaptive detection config нэмэх | T03-01 | Night mode-д threshold x1.3, looking_around x0.7 |
| T03-03 | P1 | todo | AI pipeline-д night config integrate хийх | T03-02 | Шөнийн FP rate өдрийнхөөс 1.2x-аас ихгүй target |
| T03-04 | P2 | todo | Dynamic FPS controller хийх | T00-01 | idle 3 FPS, active 15 FPS, suspicious 30 FPS |
| T03-05 | P2 | todo | Camera ingest-д dynamic FPS холбох | T03-04 | GPU load average 50%+ буурах benchmark |
| T03-06 | P2 | todo | Batched inference engine хийх | T03-04 | Batch size 4-8, max wait 100ms |
| T03-07 | P2 | todo | AI inference-г batch engine-р дамжуулах | T03-06 | Throughput 3x+ target, latency overhead < 50ms |
| T03-08 | P1 | todo | Qdrant dev service нэмэх | T02-10 | Local Qdrant ажиллана, healthcheck-тэй |
| T03-09 | P1 | todo | Per-store Qdrant collection manager хийх | T03-08 | `store_{id}_reid`, `store_{id}_cases` collection create/query |
| T03-10 | P2 | todo | OSNet Re-ID extractor хийх | T03-09 | `osnet_x0_25`, 512-dim embedding, 1 crop < 10ms target |
| T03-11 | P2 | todo | Cross-camera ID merge хийх | T03-10 | Same-store person merge threshold 0.85 |
| T03-12 | P2 | todo | CLIP/keyframe encoder сонгох ба integrate хийх | T03-09 | 512-dim image embedding, 1 crop < 50ms target |
| T03-13 | P2 | todo | Case embedding builder хийх | T03-12 | pose 256 + CLIP 512 + behavior scores normalized |
| T03-14 | P2 | todo | RAG seed script хийх | T03-13 | Existing labeled feedback Qdrant-д орно |
| T03-15 | P2 | todo | RAG suppress check хийх | T03-14 | Top-3 дотор 2+ FP, sim > 0.8 бол alert дарагдана |
| T03-16 | P2 | todo | Alert decision pipeline v2 хийх | T01-03, T03-15 | Rule → RAG decision trace DB-д хадгалагдана |

---

## Phase 4 — VLM Verification + Active Learning

RAG-аар шүүгдээгүй high-risk case-уудыг VLM-р баталгаажуулж, user label-ээс
тасралтгүй сурах loop бүрдүүлнэ.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T04-01 | P2 | todo | Ollama service нэмэх | T03-16 | Local/dev compose-д Ollama service GPU support-той |
| T04-02 | P2 | todo | Qwen2.5-VL model setup/runbook бичих | T04-01 | Model pull, quantization, VRAM requirement documented |
| T04-03 | P2 | todo | VLM API client хийх | T04-02 | JSON schema verdict: suspicious/confidence/reason |
| T04-04 | P2 | todo | Монгол/English prompt template хийх | T04-03 | Stable JSON response, hallucination guard |
| T04-05 | P2 | todo | VLM verification-г alert pipeline-д холбох | T03-16, T04-04 | RAG pass хийсэн case дээр VLM confirm/suppress |
| T04-06 | P2 | todo | VLM latency/accuracy test set бэлдэх | T04-05 | 50+ pilot clip benchmark, p95 < 1000ms target |
| T04-07 | P2 | todo | Uncertainty scoring хийх | T04-05 | `abs(confidence - 0.5)` inverse queue score |
| T04-08 | P2 | todo | Pending label backend API хийх | T04-07 | `GET /labels/pending`, `POST /labels/{case_id}` |
| T04-09 | P2 | todo | Mobile-friendly label UI хийх | T04-08 | 5 мин-д 20+ label өгөх боломжтой |
| T04-10 | P2 | todo | Feedback → RAG update хийх | T04-09 | Label submit дараа case memory шинэчлэгдэнэ |
| T04-11 | P3 | todo | Weekly retrain job хийх | T04-10 | Weight tuning, hard negative mining, sync pack output |
| T04-12 | P3 | todo | Sync pack generator хийх | T04-11 | weights/config/qdrant/prompts/signature бүхий tar.gz |

---

## Phase 5 — Performance Optimization

Edge дээр олон камер тогтвортой ажиллуулах inference optimization.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T05-01 | P3 | todo | YOLO TensorRT export script хийх | T03-07 | `yolo11s-pose.engine`, FP16 export reproducible |
| T05-02 | P3 | todo | TensorRT runtime wrapper хийх | T05-01 | TRT engine load/infer abstraction |
| T05-03 | P3 | todo | OSNet ONNX export хийх | T03-10 | `osnet_x0_25.onnx` dynamic batch |
| T05-04 | P3 | todo | OSNet TensorRT conversion хийх | T05-03 | `osnet.trt`, Re-ID latency 50% буурах target |
| T05-05 | P3 | todo | Before/after benchmark document бичих | T05-02, T05-04 | `docs/benchmarks/phase3.md` FPS/latency/GPU table |

---

## Phase 6 — Privacy, Notifications, Backup

Production compliance болон customer-facing operations.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T06-01 | P1 | todo | Face blur component хийх | T02-06 | Per-store toggle, pose/keypoint-based blur |
| T06-02 | P1 | todo | Clip encryption at rest хийх | T02-06 | AES-256-GCM, store key strategy documented |
| T06-03 | P1 | todo | Audit log-г clip/config actions-д холбох | T02-06 | view/download/label/config_change бүр audit хийнэ |
| T06-04 | P2 | todo | Multi-channel notification dispatcher хийх | T01-03 | Telegram/SMS/Push/Email interface, priority routing |
| T06-05 | P2 | todo | Store settings admin UI хийх | T01-08 | 10+ config toggle/value хадгална |
| T06-06 | P2 | todo | PostgreSQL backup runbook/script | T02-01 | Daily full dump + WAL archival plan |
| T06-07 | P2 | todo | Qdrant snapshot backup хийх | T03-09 | Weekly snapshot, 4-week retention |
| T06-08 | P2 | todo | Privacy/federated spec document бичих | T06-01, T06-02 | `docs/privacy/federated-spec.md`, DP epsilon target |

---

## Phase 7 — Edge Deployment Foundation

Hybrid edge архитектурын central API, edge services, provisioning foundation.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T07-01 | P1 | todo | Edge hardware BOM lock хийх | T00-05 | Recommended/compact/high-end BOM, vendor shortlist, price target reconciled |
| T07-02 | P1 | todo | Edge-central protocol doc бичих | T04-12 | Register/heartbeat/alerts/sync/feedback endpoint contract |
| T07-03 | P1 | todo | Edge token auth design хийх | T07-02 | Token hash, rotation, revocation, WireGuard identity mapped |
| T07-04 | P1 | todo | Central `/api/edge/register` endpoint хийх | T02-02, T07-03 | Edge box бүртгэнэ, token/WG config буцаана |
| T07-05 | P1 | todo | Central `/api/edge/heartbeat` endpoint хийх | T07-04, T02-05 | Metrics/status DB-д хадгална |
| T07-06 | P1 | todo | Central `/api/edge/alerts` endpoint хийх | T07-04, T03-16 | Alert metadata + clip upload хүлээн авна |
| T07-07 | P1 | todo | Central `/api/edge/sync-pack` endpoint хийх | T04-12, T07-04 | Latest signed sync pack татна |
| T07-08 | P2 | todo | Central `/api/edge/feedback-upload` endpoint хийх | T07-04, T04-10 | Edge local labels central DB-д batch орно |
| T07-09 | P2 | todo | Edge ingest service хийх | T07-02 | RTSP → Redis Streams, reconnect, FPS throttle |
| T07-10 | P2 | todo | Edge inference service packaging хийх | T03-16, T04-05 | Rule/RAG/VLM local pipeline container |
| T07-11 | P2 | todo | Edge uploader service хийх | T07-06 | Local buffer → central upload |
| T07-12 | P2 | todo | Offline-first queue хийх | T07-11 | 24h offline alerts хадгалж reconnect-д batch upload |
| T07-13 | P2 | todo | Edge sync pull service хийх | T07-07 | Weekly pull, signature verify, atomic swap |
| T07-14 | P2 | todo | Edge docker-compose stack бичих | T07-09, T07-10, T07-11, T07-13 | redis/qdrant/ollama/inference/ingest/uploader healthy |
| T07-15 | P2 | todo | WireGuard central setup хийх | T07-04 | Edge бүр VPN IP авна, outbound-only model |
| T07-16 | P2 | todo | Edge SLA monitoring rules хийх | T02-11, T07-05 | GPU temp, disk, camera offline, edge offline alerts |
| T07-17 | P3 | todo | Edge management UI хийх | T07-05, T07-16 | Status, heartbeat, GPU/disk/camera health харна |
| T07-18 | P3 | todo | Remote management CLI хийх | T07-15 | `edge logs/restart/update` ажиллана |

---

## Phase 8 — Migration / Rollout

Centralized RTSP WAN architecture-аас hybrid edge рүү zero/low downtime
шилжүүлэх ажлууд.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T08-01 | P1 | todo | Edge OS image runbook хийх | T07-14, T07-15 | Ubuntu + CUDA + Docker + Chipmo stack install steps |
| T08-02 | P2 | todo | Provisioning script хийх | T08-01, T07-04 | Store ID/token → WG/config/sync/services up |
| T08-03 | P2 | todo | NTP/clock sync enforcement хийх | T08-02 | Edge-central drift < 1 sec |
| T08-04 | P2 | todo | Shadow mode / dual-run tooling хийх | T07-06 | Central vs Edge event/alert match rate хэмжинэ |
| T08-05 | P2 | todo | Migration script хийх | T08-04 | Store → edge sync pack, dual-run, cutover helpers |
| T08-06 | P2 | todo | Rollback procedure automate/document хийх | T08-05 | Edge disable, central re-enable < 15 min |
| T08-07 | P2 | todo | Customer communication templates finalize хийх | T08-05 | Pre-migration, daily check-in, completion templates |
| T08-08 | P2 | todo | Customer install handbook бэлдэх | T08-02 | IT ажилтан self-install хийх PDF/video outline |
| T08-09 | P2 | todo | Wave 1 pilot migration хийх | T08-04, T08-08 | 1 customer, 72h dual-run, postmortem |
| T08-10 | P3 | todo | Wave 2/3 rolling migration хийх | T08-09 | 2/week migration target, rollback < 5% |
| T08-11 | P3 | todo | Central inference retirement plan хийх | T08-10 | Migrated stores edge-primary, central management/sync only |

---

## Phase 9 — Federated Learning / Global Patterns

Олон дэлгүүрийн anonymized pattern-ийг privacy-safe байдлаар нэгтгэх урт
хугацааны ажил.

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| T09-01 | P3 | todo | Federated learning implementation design | T06-08, T04-11 | DP, anonymized embedding, lawyer-review checklist |
| T09-02 | P3 | todo | Global patterns Qdrant collection хийх | T09-01 | `global_patterns` collection + metadata schema |
| T09-03 | P3 | todo | Cross-store aggregation job хийх | T09-02 | Pattern aggregate, no raw face/body data |
| T09-04 | P3 | todo | New-store seed flow хийх | T09-03 | New store initial RAG memory global patterns-аас авна |

---

## Cross-Cutting DevOps

| ID | Priority | Status | Task | Dependency | Output / Acceptance |
|---|---|---|---|---|---|
| TD-01 | P1 | todo | GitHub Actions CI хийх | T00-01, T00-03 | Backend tests, ruff, frontend lint/build |
| TD-02 | P1 | todo | Docker image build/publish workflow хийх | TD-01 | Backend/frontend image reproducible |
| TD-03 | P2 | todo | Deployment rollback runbook бичих | TD-02 | Failed deploy rollback steps tested |
| TD-04 | P2 | todo | Benchmark data collection template хийх | T02-08 | FPS/latency/GPU/FP metrics standard form |

---

## Recommended Execution Order

| Window | Focus | Tasks |
|---|---|---|
| Week 0 | Baseline | T00-01 → T00-06 |
| Week 1-2 | Production critical | T01-01 → T01-08 |
| Week 3-4 | Infrastructure | T02-01 → T02-13 |
| Week 5-10 | Core AI | T03-01 → T03-16 |
| Month 3 | VLM + active learning | T04-01 → T04-12 |
| Month 3-4 | Performance | T05-01 → T05-05 |
| Month 4-5 | Privacy/ops | T06-01 → T06-08 |
| Month 5-7 | Edge foundation | T07-01 → T07-18 |
| Month 7+ | Migration/federated | T08-01 → T09-04 |

---

## Definition Of Done

Task бүрийн DoD:

- Implementation code merged
- Migration/backfill/rollback documented where needed
- Unit or integration tests added for changed behavior
- Metrics/logging added for production workflows
- Docs updated if public contract, schema, deploy flow, or architecture changes
- Acceptance criteria дээрх measurable target шалгагдсан эсвэл benchmark TODO-той үлдсэн
