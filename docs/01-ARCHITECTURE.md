# 01 — Architecture: Одоогийн vs Эцсийн

## Зорилго

Системийн архитектурын өнөөгийн байдал болон target state-ийг тодорхойлж,
гол design decision-уудыг хамтын зөвшилцөлд оруулах.

---

## 1. Одоогийн архитектур (AS-IS)

### 1.1 Overview

Централизованный архитектур. Харилцагч бүрийн камерууд RTSP-аар төв
сервер рүү stream хийж, төв дээр inference + storage + management хийгддэг.

```
┌─────────────────────────────────────────────────────────────┐
│                   ХАРИЛЦАГЧИЙН ДЭЛГҮҮР                       │
│                                                              │
│   [Камер 1]  [Камер 2]  [Камер 3]  [Камер 4]               │
│        │         │         │         │                      │
│        └─────────┴─────────┴─────────┘                      │
│                       │ RTSP stream (WAN)                    │
└───────────────────────┼──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                ТӨВ СЕРВЕР (self-hosted)                      │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI (async)                                     │   │
│  │  ├─ Auth (JWT + cookies)                            │   │
│  │  ├─ Store/Camera CRUD                               │   │
│  │  ├─ Alert API                                       │   │
│  │  └─ MJPEG streaming                                 │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  AI Inference (per-camera, serial)                   │  │
│  │  ├─ YOLO11m-pose → keypoints                        │  │
│  │  ├─ 6 behavior signals (weighted)                   │  │
│  │  ├─ 150-frame accumulator (0.98 decay)              │  │
│  │  └─ Threshold → ALERT                               │  │
│  └──────┬────────────────────────────┬──────────────────┘  │
│         ▼                            ▼                      │
│  ┌──────────────┐             ┌───────────────┐            │
│  │  PostgreSQL  │             │ Alert Worker  │            │
│  │  + Redis     │             │  → Telegram   │            │
│  └──────┬───────┘             └───────────────┘            │
│         ▼                                                   │
│  ┌────────────────────────────┐                            │
│  │  Auto-learning             │                            │
│  │  └─ Weight adjust only     │ ← 20+ feedback sample      │
│  └────────────────────────────┘                            │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  React frontend                                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Behavior detection дэлгэрэнгүй

**6 signal weighted scoring:**

| Signal | Weight | Тайлбар |
|---|---|---|
| `looking_around` | 1.5 | Эргэж харах давтамж |
| `item_pickup` | 15.0 | Барааны тавиураас зүйл авах |
| `body_blocking` | 3.0 | Камераас бүслүүрдэх байрлал |
| `crouching` | 1.0 | Бөхийх/эргэлдэх |
| `wrist_to_torso` | 5.0 | Гараа биед/халаасанд |
| `rapid_movement` | 1.5 | Хурдан хөдөлгөөн |

**Accumulator:**
- Window: 150 frame (~5 сек @ 30 FPS)
- Decay: 0.98 exponential
- Threshold-с хэтрэхэд alert

**Auto-learning:**
- 20+ sample цугласны дараа per-store weight adjust
- Feedback: "хулгайлсан" / "худал alert" label

### 1.3 Одоогийн архитектурын хязгаарлалт

| Хязгаарлалт | Нөлөө |
|---|---|
| RTSP WAN stream | Bandwidth их, internet outage-д эмзэг |
| Per-camera serial inference | Нэг GPU-д 5-10 камер л болно |
| Re-ID байхгүй | Multi-camera-д ID холбогдохгүй |
| Rule-based only | Context ойлгохгүй → false positive ↑ |
| Night-mode adaptation ❌ | Шөнөдөө accuracy унана |
| Alert dedup найдваргүй | Spam notification эрсдэл |
| Observability хязгаарлагдмал | Production issue-г хожигдон олно |
| Weight-only learning | Store-д тохируулалт хязгаарлагдмал |

---

## 2. Эцсийн архитектур (TO-BE)

### 2.1 Overview

**Hybrid edge architecture** — inference edge box дээр, management +
learning төв серверт. RTSP LAN дотор зогсоно → bandwidth 80%+ хэмнэнэ.

```
┌──────────────────────────────────────────────────────────────────┐
│                    ХАРИЛЦАГЧИЙН ДЭЛГҮҮР                           │
│                                                                   │
│   [Камер 1]  [Камер 2]  [Камер 3]  [Камер 4]                    │
│        │         │         │         │                           │
│        └─────────┴─────────┴─────────┘                           │
│                       │ RTSP (LOCAL LAN)                          │
│                       ▼                                           │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  EDGE BOX  (RTX 5060 / Jetson Orin NX)                  │     │
│  │                                                          │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  Ingest → Redis Streams (local)                   │  │     │
│  │  └────────────────────┬─────────────────────────────┘  │     │
│  │                       ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  Batched Inference (TensorRT + FP16)              │  │     │
│  │  │  ├─ YOLO11s-pose (batch 4-8 frames)              │  │     │
│  │  │  ├─ ByteTrack (tuned params)                     │  │     │
│  │  │  ├─ OSNet Re-ID → 512-dim embedding               │  │     │
│  │  │  ├─ Dynamic FPS (3/15/30)                         │  │     │
│  │  │  └─ Night-mode adaptive threshold                 │  │     │
│  │  └────────────────────┬─────────────────────────────┘  │     │
│  │                       ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  Behavior Engine v2                               │  │     │
│  │  │  ├─ Rule-based scorer (150-frame)                │  │     │
│  │  │  ├─ Per-store weights (synced from central)      │  │     │
│  │  │  └─ Alert dedup (cooldown per person_id)         │  │     │
│  │  └────────────────────┬─────────────────────────────┘  │     │
│  │                       │ сэжигтэй үед                   │     │
│  │                       ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  RAG Check (LOCAL Qdrant replica)                 │  │     │
│  │  │  └─ Pattern match өмнөх case-уудтай               │  │     │
│  │  └────────────────────┬─────────────────────────────┘  │     │
│  │                       │                                 │     │
│  │                       ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  VLM Verification (Qwen2.5-VL 7B via Ollama)      │  │     │
│  │  │  └─ Confirm/deny suspicious event                 │  │     │
│  │  └────────────────────┬─────────────────────────────┘  │     │
│  │                       ▼                                 │     │
│  │  ┌──────────────────────────────────────────────────┐  │     │
│  │  │  Local Buffer (48h clip) + SQLite meta            │  │     │
│  │  └──────────────────────────────────────────────────┘  │     │
│  └──────────────┬─────────────────────────────────────────┘     │
│                 │ Metadata + confirmed clips only (upload)       │
└─────────────────┼────────────────────────────────────────────────┘
                  │ HTTPS / WireGuard VPN
                  ▼
┌────────────────────────────────────────────────────────────────┐
│         ТӨВ СЕРВЕР (self-hosted, RTX 5090)                      │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI + React dashboard                                │  │
│  │  ├─ Multi-tenant: Org → Store → EdgeBox → Camera         │  │
│  │  ├─ Alert management + Active learning UI                │  │
│  │  ├─ Admin metrics (FP rate/store/day)                    │  │
│  │  └─ Billing/subscription                                  │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Central Qdrant                                           │  │
│  │  ├─ Per-store case memory (embeddings + labels)          │  │
│  │  ├─ Cross-store federated patterns (anonymized)          │  │
│  │  └─ Re-ID gallery (GDPR-safe)                            │  │
│  └──────────────────────┬───────────────────────────────────┘  │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Auto-Learning Engine v2                                  │  │
│  │  ├─ Per-store weight tuning                              │  │
│  │  ├─ Hard negative mining (FP → retrain)                  │  │
│  │  ├─ Active learning (uncertain → label UI)               │  │
│  │  ├─ Cross-store pattern aggregation                      │  │
│  │  └─ Weekly sync pack → edge boxes                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL + TimescaleDB                                 │  │
│  │  ├─ events (time-series hypertable)                      │  │
│  │  ├─ users, stores, edge_boxes, cameras                   │  │
│  │  ├─ feedback, labels                                      │  │
│  │  └─ audit_log (compliance)                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Observability: Prometheus + Grafana + Loki              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Notification Dispatcher                                  │  │
│  │  └─ Telegram / SMS / Push / Email (SLA-routing)          │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Detection Pipeline (layered)

**3 давхарга — эхний алгаас сүүлийн давхаргад ирэх тоо багасна:**

```
Layer 1: Rule-based scoring
  (every frame, ~100% of data)
            │
            ▼
   Threshold exceeded?
            │
   ┌────────┴────────┐
   │ No              │ Yes (~2-5% of frames)
   │                 ▼
   │        Layer 2: RAG similarity check
   │        (Qdrant top-5 similar past cases)
   │                 │
   │        Match "confirmed false positive"?
   │                 │
   │         ┌───────┴───────┐
   │         │ Yes           │ No (~50% pass)
   │         │               ▼
   │         │      Layer 3: VLM verification
   │         │      (Qwen2.5-VL, ~500ms latency)
   │         │               │
   │         │      Confirm as suspicious?
   │         │               │
   │         │      ┌────────┴────────┐
   │         │      │ No              │ Yes (~30-40% pass)
   │         ▼      ▼                 ▼
   └───→ SUPPRESS ALERT         SEND ALERT
```

**Нөлөө:** Rule-based стандарт гарцны ~2-5% нь Layer 2-д хүрнэ. Тэднийх
~50% нь RAG-аар шүүгдэнэ. Сүүлд VLM ~30-40%-ийг confirm хийнэ →
Харилцагч руу **final alert = rule-based-ийн 0.3-1%**. False positive
огцом буурна.

### 2.3 Auto-Learning Pipeline

```
                ┌──────────────────────────┐
                │  Alert feedback          │
                │  (user labels in UI)     │
                └────────────┬─────────────┘
                             ▼
           ┌─────────────────────────────────┐
           │  Central DB: labels hypertable  │
           └────────────┬────────────────────┘
                        ▼
      ┌─────────────────────────────────────────┐
      │  Weekly Retrain Job                     │
      │  ├─ Per-store weight tuning             │
      │  ├─ Hard negative mining (FP clips)     │
      │  ├─ Cross-store pattern extraction      │
      │  └─ Active learning queue refresh       │
      └─────────────────┬───────────────────────┘
                        ▼
         ┌──────────────────────────────────┐
         │  Sync Pack (per store)           │
         │  ├─ Updated weights.json         │
         │  ├─ Qdrant snapshot (new cases)  │
         │  └─ VLM prompt templates         │
         └────────────┬─────────────────────┘
                      ▼
              Edge boxes pull сард 1-2 удаа
```

---

## 3. Харьцуулалт (comparison table)

| Хэсэг | ОДОО | ЭЦСИЙН | Нөлөө |
|---|---|---|---|
| **Deployment** | Centralized (RTSP WAN) | Hybrid (Edge LAN + Central cloud) | Bandwidth 80% ↓ |
| **Inference** | Serial per camera | Batched + TensorRT FP16 | GPU throughput 3-4x ↑ |
| **FPS** | Fixed | Dynamic (3/15/30) | GPU load 60-70% ↓ |
| **Detection** | YOLO-pose only | + ByteTrack (tuned) + OSNet Re-ID | Multi-camera ID ✓ |
| **Decision** | Rule-based | Rule → RAG → VLM (3 layers) | FP rate 50-80% ↓ |
| **Learning** | Weight tune only | Weight + Hard-neg + Active + Federated | Systematic ↑ |
| **Memory** | PostgreSQL | PG + TimescaleDB + Qdrant | Context-aware |
| **Alerts** | Telegram basic | Dedup + priority + multi-channel | Зохион байгуулалт ↑ |
| **Night mode** | ❌ | Adaptive threshold | FP ↓ шөнөдөө |
| **Observability** | Logs only | Prometheus + Grafana + Loki | Бодит SLA хангана |
| **Privacy** | JWT + hashing | + Face blur + clip encryption + audit | GDPR-ready |
| **Scale** | ~5-10 камер/GPU | ~15-25 edge + central multiplex | Linear scale |

---

## 4. Гол design decision-ууд

### 4.1 Яагаад Edge-first архитектур вэ?

**Оролт:** Харилцагч бүрийн камер WAN-аар төв серверт стрим хийх байсан.

**Асуудлууд:**
- Харилцагч internet outage → систем ажиллахгүй
- Bandwidth төлбөр: 1 камер ~2-5 Mbps × 24/7
- Latency: alert confirm ~1-3 сек (WAN + inference)
- Privacy: raw video WAN дамжина → хууль зөрчих эрсдэл
- Scale bottleneck: төв GPU дүүрэх

**Шийдэл:** Inference-ийг дэлгүүр дээр гарга. Зөвхөн confirmed alert clip
+ metadata WAN-аар төвд илгээ.

**Үр дүн:**
- Bandwidth 80%+ хэмнэлт
- Internet outage-д resilient (local queue)
- Privacy: raw video never leaves store
- Horizontal scale: шинэ харилцагч = шинэ edge box, төв GPU нэмэгдэхгүй

### 4.2 Яагаад layered detection (rule → RAG → VLM)?

**Оролт:** Зөвхөн rule-based → false positive ~20-40%.

**Шийдэл:** Гурван давхарга. Rule хурдан (ms) бүх frame дээр, RAG дунд
(~50ms) зөвхөн сэжигтэй үед, VLM удаан (~500ms) зөвхөн үлдсэн case-д.

**Compute зардал:**
- Layer 1 (rule): 100% frame × ms
- Layer 2 (RAG): 2-5% frame × 50ms
- Layer 3 (VLM): ~1% frame × 500ms

Нийт GPU-с VLM дээр зарцуулах нь 1% × 500ms = 5ms/second (GPU load-д ач холбогдолгүй).

### 4.3 Яагаад Qwen2.5-VL (Llama биш)?

- Qwen Монгол хэл дэмжинэ (prompt, response)
- Vision-Language чадвар Llama 3.1-ээс илүү
- 7B size → RTX 5060-д ajilagdаж байна
- Apache 2.0 лиценз → commercial use OK

### 4.4 Яагаад Qdrant (Chroma биш)?

- Production-grade (Chroma more для POC)
- Multi-tenant collections native support
- Rust-д бичигдсэн → performance
- Filtering + hybrid search чадвар

### 4.5 Яагаад RTX 5060 edge-д?

- Зардал: ~$400-500 vs Jetson Orin NX ~$800
- FP16 performance: YOLO11s + Re-ID + Qwen 7B-ийг unison-д ажиллуулна
- Standard PCIe → mini-PC барилгад суулгана
- Jetson нь embedded нь тавтай боловч x86 stack-ийг дахин build хийхэд төвөгтэй

**Alternative:** Volume-д хүрэхэд Jetson Orin Nano (~$500 BOM, integrated power efficient) руу шилжих боломжтой.

---

## 5. Холбоотой документ

- [02-ROADMAP.md](./02-ROADMAP.md) — Хэрэгжүүлэх phase-үүд
- [03-TECH-SPECS.md](./03-TECH-SPECS.md) — Компонент бүрийн дэлгэрэнгүй
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md) — Edge box спец, BOM
- [05-MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md) — Шилжилтийн алхмууд

---

Updated: 2026-04-17
