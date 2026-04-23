# 01 — Architecture: Одоогийн байдал болон Target state

> **Note (2026-04-21):** Энэхүү документ нь
> [`decisions/2026-04-21-centralized-saas-no-customer-hardware.md`](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md)
> ADR-ын дагуу шинэчлэгдсэн. Өмнөх "Hybrid edge" болон "Single-server on-prem"
> төслийг хоёуланг нь superseded болгосон. On-prem SKU-ийн спец
> [`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`](./decisions/2026-04-21-drop-edge-box-hybrid-architecture.md)-т
> тусгагдсан бөгөөд optional product variant хэвээр үлдэнэ.

## Зорилго

Системийн архитектурын өнөөгийн байдал болон target state-ийг тодорхойлж,
гол design decision-уудыг хамтын зөвшилцөлд оруулах.

---

## 1. Одоогийн ажиллаж буй байдал (AS-IS)

### 1.1 Overview

Төвлөрсөн (centralized) архитектур. Харилцагчийн камерууд RTSP-аар
Chipmo сервер рүү stream илгээж, төв дээр inference + storage +
management гүйцэтгэгдэнэ.

```
┌─────────────────────────────────────────────────────────────┐
│                   ХАРИЛЦАГЧИЙН ДЭЛГҮҮР                       │
│                                                              │
│   [Камер 1]  [Камер 2]  [Камер 3]  [Камер 4]               │
│        │         │         │         │                      │
│        └─────────┴─────────┴─────────┘                      │
│                       │ RTSP stream (WAN, no VPN yet)        │
└───────────────────────┼──────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                 CHIPMO ТӨВ СЕРВЕР (single host)              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI (async)                                     │   │
│  │  ├─ Auth (JWT + cookies)                            │   │
│  │  ├─ Org / Store / Camera CRUD                       │   │
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

**6 signal weighted scoring** (v1-ээс өөрчлөгдөөгүй):

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

| Хязгаарлалт | Нөлөө | Хариу арга (target architecture) |
|---|---|---|
| RTSP WAN өндөр bandwidth | Харилцагчийн internet-д ачаалал | Sub-stream 480p/5fps + VPN tunnel |
| Per-camera serial inference | 1 GPU → 5-10 камер | Batched NVDEC + tensor batch |
| Re-ID байхгүй | Multi-camera ID алдагдана | OSNet per-tenant Re-ID |
| Rule-based only | Context байхгүй → FP ↑ | + RAG + VLM layered |
| Night-mode адаптаци байхгүй | Шөнөдөө accuracy унана | Adaptive threshold |
| Alert dedup найдваргүй | Spam эрсдэл | Per-person cooldown |
| Observability хязгаарлагдмал | Production issue хожуу илрэнэ | Prometheus + Grafana + Loki |
| Shared cross-tenant learning ❌ | Харилцагч нэмэгдэхэд систем ухаалаг болохгүй | Behavior taxonomy shared collection |
| Customer onboarding удаан | Sales cycle уртасна | VPN appliance-тай self-service onboarding |

---

## 2. Target architecture (TO-BE)

### 2.1 Overview

**Centralized SaaS, hardware-free for the customer.** Chipmo нь зөвхөн
VPN appliance (40-60 ам.долларын router эсвэл Raspberry Pi)-г
харилцагчид суулгана. Камер, NVR зэрэг одоо байгаа infrastructure-д
ямар нэг өөрчлөлт хийхгүй. Inference, storage, learning бүгд
Chipmo-ийн cloud / owned server-т ажиллана.

```
┌──────────── Харилцагчийн дэлгүүр (N ширхэг) ────────────┐
│                                                          │
│   [Камер 1]  [Камер 2]  [Камер 3]  [Камер 4]           │
│       │         │          │         │                  │
│       └─────────┴──────────┴─────────┘                  │
│                    │                                      │
│                    │ RTSP sub-stream (480p/5-10fps, LAN)  │
│                    ▼                                      │
│          ┌─────────────────────────┐                      │
│          │ Chipmo VPN appliance    │ ← Chipmo-ийн ганц   │
│          │ (WireGuard peer)        │   ачигддаг төхөөрөмж│
│          │ + 24h ring buffer      │  ($40-60 BOM)        │
│          │ + ONVIF re-config tool │                      │
│          └──────────┬──────────────┘                      │
│                     │                                     │
└─────────────────────┼─────────────────────────────────────┘
                      │ WireGuard tunnel over internet
                      │ (upload: ~1-3 Mbps / дэлгүүр @ 4 cam sub-stream)
                      ▼
┌──────────── Chipmo төв (Phase A / B / C infra) ──────────┐
│                                                           │
│  ┌──────────────── Ingest layer ────────────────┐        │
│  │  RTSP demuxer → NVDEC batch decode           │        │
│  │  Per-tenant isolation (namespace + Postgres) │        │
│  │  Dynamic FPS governor (bandwidth-aware)      │        │
│  └────────────────────┬─────────────────────────┘        │
│                       ▼                                    │
│  ┌──── Detection pipeline (per tenant) ────┐              │
│  │  YOLO11s-pose → ByteTrack                │              │
│  │  → OSNet Re-ID (per-tenant gallery)      │              │
│  │  → Behavior scorer (per-store weights)   │              │
│  │  → Alert dedup (cooldown per person_id)  │              │
│  └────────────────────┬─────────────────────┘              │
│                       │ сэжигтэй event (~2-5%)            │
│                       ▼                                    │
│  ┌─────────────── Layered filter ──────────────┐          │
│  │  Layer 2: RAG check (Qdrant per-tenant)     │          │
│  │  Layer 3: VLM verification (Qwen2.5-VL)     │          │
│  │           via vLLM continuous batching      │          │
│  └────────────────────┬─────────────────────────┘        │
│                       ▼                                    │
│  ┌──── Persistence (minimal, stateless by default) ────┐  │
│  │  Postgres + TimescaleDB                             │  │
│  │    → events, feedback, audit_log                    │  │
│  │  Qdrant                                             │  │
│  │    → per-tenant: Re-ID gallery, case memory         │  │
│  │    → shared: behavior_taxonomy (anonymized)         │  │
│  │  S3/MinIO                                           │  │
│  │    → ≤10 сек alert clip + thumbnail (retention policy)│ │
│  └────────────────────┬─────────────────────────────────┘  │
│                       ▼                                    │
│  Notification dispatcher → Telegram / SMS / email / push  │
│                                                           │
│  Observability: Prometheus + Grafana + Loki               │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 2.2 Detection pipeline (layered)

**3 давхарга** — эхний layer-аас сүүлчийнх рүү багасч, хүнд loadтой
layer-т хүрэх frame тоо ~100% → ~0.3%-1% болж багасна.

```
Layer 1: Rule-based scoring
  (every frame, ~100% of input)
            │
            ▼
   Threshold exceeded?
            │
   ┌────────┴────────┐
   │ No              │ Yes (~2-5% of frames)
   │                 ▼
   │        Layer 2: RAG similarity check
   │        (Qdrant top-5 similar past cases — per tenant
   │         + shared behavior taxonomy)
   │                 │
   │        Match "confirmed false positive" pattern?
   │                 │
   │         ┌───────┴───────┐
   │         │ Yes           │ No (~50% pass)
   │         │               ▼
   │         │      Layer 3: VLM verification
   │         │      (Qwen2.5-VL via vLLM, ~300-600ms)
   │         │               │
   │         │      Confirm as suspicious?
   │         │               │
   │         │      ┌────────┴────────┐
   │         │      │ No              │ Yes (~30-40% pass)
   │         ▼      ▼                 ▼
   └───→ SUPPRESS ALERT         SEND ALERT + save ≤10s clip
```

**Үр дүн:** Rule-based layer-ийн ~2-5% нь Layer 2 руу очно. Тэндээс
~50% RAG-ээр шүүгдэж, үлдсэн ~50% VLM-д хүрнэ. VLM-ын ~30-40% confirm.
**Харилцагч руу очих final alert = rule-based-ийн 0.3-1%.** False
positive огцом буурна.

### 2.3 Cross-customer learning model

Харилцагч нэмэгдэхэд систем ухаалаг болох бизнесийн moat-г хадгалахын
тулд Qdrant-д хоёр төрлийн collection байна:

```
┌──────────────── Per-tenant (isolated) ────────────────┐
│                                                        │
│  tenant_{id}_reid_gallery                              │
│    → хүн бүрийн OSNet embedding (identity-тай)         │
│                                                        │
│  tenant_{id}_case_memory                               │
│    → confirmed alert-ийн case embedding + label        │
│      (тухайн tenant-д эргэж хандана)                   │
│                                                        │
└────────────────────────────────────────────────────────┘

┌──────────────── Shared taxonomy (anonymized) ─────────┐
│                                                        │
│  behavior_taxonomy_v1                                  │
│    → pose trajectory + temporal signal embedding       │
│      (хүний identifying info агуулдаггүй)              │
│    → label: "loitering_theft", "distraction_team",     │
│             "staff_restocking", ...                    │
│    → tenant_contribution_count (тенантуудын тоо)       │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**Яагаад safe:**
- Re-ID embedding нь биометрийн feature тул tenant-ыг даваж гардаггүй.
- Shared таксономи-д **identity биш, үйлдлийн хэв маяг** л орно.
- `audits/multi-tenant-isolation-2026-04-21.md`-т тусгагдсан
  isolation guarantees load-bearing болж ажиллана.

### 2.4 Auto-learning pipeline

```
                ┌──────────────────────────┐
                │  Alert feedback          │
                │  (user labels in UI)     │
                └────────────┬─────────────┘
                             ▼
           ┌─────────────────────────────────┐
           │  Central DB: labels hypertable  │
           │  (tenant-scoped)                │
           └────────────┬────────────────────┘
                        ▼
      ┌─────────────────────────────────────────┐
      │  Weekly Retrain Job                     │
      │  ├─ Per-store weight tuning             │
      │  ├─ Hard negative mining (FP clips)     │
      │  ├─ Active learning (uncertain → UI)    │
      │  └─ Cross-tenant taxonomy aggregation   │
      │     (anonymized pose trajectories only) │
      └─────────────────┬───────────────────────┘
                        ▼
         ┌──────────────────────────────────┐
         │  Applied directly in central     │
         │  → updated weights.json          │
         │  → new Qdrant entries            │
         │  → refreshed VLM prompts         │
         │  (No sync pack needed — central) │
         └──────────────────────────────────┘
```

Edge box синc-тэй холбогдсон complexity (sync pack, offline queue,
fleet management) **устсан** — систем cloud-д төвлөрсөн тул
update бүр instant.

---

## 3. Харьцуулалт (AS-IS vs TO-BE)

| Хэсэг | ОДОО | TARGET | Нөлөө |
|---|---|---|---|
| **Customer deploy** | Шууд WAN RTSP (VPN-гүй) | VPN appliance + RTSP sub-stream | Privacy + bandwidth ↑ |
| **Customer CAPEX** | — | ~$40-60 VPN appliance (optional) | Zero-CAPEX onboarding |
| **Ingest** | 1080p main-stream full FPS | 480p sub-stream 5-10fps | Bandwidth ~75% ↓ |
| **Decode** | CPU / per-stream | NVDEC batch decode | Decode throughput 5-10x ↑ |
| **Inference** | Serial per camera | Batched + TensorRT FP16 | GPU throughput 3-4x ↑ |
| **FPS** | Fixed 30 | Dynamic 3/10/30 | GPU load 60-70% ↓ |
| **Detection** | YOLO-pose only | + ByteTrack (tuned) + OSNet Re-ID | Multi-camera ID ✓ |
| **Decision** | Rule-based | Rule → RAG → VLM (3 layers) | FP rate 50-80% ↓ |
| **VLM runtime** | — | vLLM continuous batching | VLM throughput 3-5x ↑ |
| **Learning** | Weight tune only | Weight + Hard-neg + Active + **Shared taxonomy** | Network effect |
| **Memory** | PostgreSQL | PG + TimescaleDB + Qdrant (2-tier) | Context-aware + cross-tenant taxonomy |
| **Alerts** | Telegram basic | Dedup + priority + multi-channel | Зохион байгуулалт ↑ |
| **Night mode** | ❌ | Adaptive threshold | FP ↓ шөнөдөө |
| **Observability** | Logs only | Prometheus + Grafana + Loki | Бодит SLA |
| **Privacy** | JWT + hashing | + VPN + per-tenant isolation + **no-recording default** + DPIA | Хуулийн дагуу |
| **Scale unit** | 1 сервер ~5-10 камер | Phase B 1 GPU ~200 камер, Phase C 1 сервер ~1000 камер | Linear + phase-scaled |
| **Customer SKU** | Нэг төрөл | Default SaaS + Optional on-prem | Choice |

---

## 4. Гол design decision-ууд

### 4.1 Яагаад centralized SaaS?

**Оролт:** Сонголтууд — (A) Hybrid edge + central, (B) Single-server
on-prem, (C) Centralized SaaS with VPN ingress.

**Шийдэл (C):**
- Харилцагч өөрийн камер, NVR-аа үлдээнэ. Setup 1-2 цагт.
- Chipmo-ийн improvement бүх харилцагчид нэгэн зэрэг хүрнэ
  (SaaS деплой загвар).
- Cross-customer learning нь shared behavior taxonomy-оор
  хуулийн хүрээнд боломжтой.
- Unit economics: Phase B-д 1 GPU-д 40-50 tenant багтана → MRR
  хөдөлгөх.

**Trade-off:** Харилцагчийн internet drop нь service drop гэсэн үг.
VPN appliance 24h ring buffer + 4G fallback router option-оор
зөөллөнө.

**Exception:** Том chain, банк, төрийн байгууллагад on-prem SKU
(`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`)
санал болгоно.

### 4.2 Яагаад RTSP sub-stream (main-stream биш)?

**Оролт:** Main stream = 1080p/25fps, ~2-4 Mbps. Sub-stream =
480p/5-10fps, ~0.3-0.8 Mbps.

**Шийдэл:** AI detection-д 480p/5fps бараг л хангалттай. Sub-stream
сонгосноор:
- Харилцагчийн upload bandwidth эзэлдэггүй (UB-ээс гадуур 5 Mbps upload
  realistic).
- 1 GPU-ийн NVDEC чадвар 100+ sub-stream даах боломжтой (vs. 20-30
  main-stream).
- Бичлэгийн main-stream customer-ын өөрийн NVR-д үлдэх тул legal-ын
  хувьд "Chipmo бичдэггүй" тайлбар цэвэр.

### 4.3 Яагаад layered detection (rule → RAG → VLM)?

Rule-based ганцаараа → FP 20-40%. Гурван давхарга:
- **Layer 1 (rule):** 100% frame × ~1ms
- **Layer 2 (RAG):** 2-5% frame × ~50ms
- **Layer 3 (VLM):** ~1% frame × ~500ms (batched ~150-200ms amortized)

GPU total compute = mostly Layer 1. VLM нь зөвхөн сэжигтэй дээр л
ажиллана, тэгээд ч continuous batching-аар амортжинa.

### 4.4 Яагаад Qwen2.5-VL?

- Монгол, Хятад, Англи зэрэг multi-lingual response.
- Vision-Language чадвар Llama 3.1-ээс илүү.
- 7B size → RTX 4090/5090-д vLLM-тэй оптимал.
- Apache 2.0 license → commercial use OK.

### 4.5 Яагаад Qdrant?

- Production-grade (Chroma-нь POC-д тохиромжтой).
- Multi-tenant collection native support.
- Rust-ын performance.
- gRPC + filtering + hybrid search.
- CLIP/image embedding multimodal дэмжинэ (үе шаттайгаар нэвтрүүлнэ).

### 4.6 Яагаад WireGuard (OpenVPN биш)?

- Kernel-space performance — Raspberry Pi 4 дээр ~300 Mbps.
- Config файл 10 мөртэй, онбординг автоматжуулахад хялбар.
- Peer key-based → credential rotation cleaner.
- Хятад, Монгол улсын ISP-ийн DPI-д OpenVPN-ээс илүү тэсвэртэй.

### 4.7 Яагаад 3-phase infrastructure?

**Үндэс:** Customer count 0 → 1000 болох travelд GPU capex-г эрт
хөрөнгөжүүлэх нь эрсдэлтэй. Phase гарц үе шаттай:
- **Phase A (Railway):** Dev + 1-3 pilot customer. Zero DevOps.
- **Phase B (Rented cloud GPU):** 10-50 customer. Elastic, бодит
  load-аас суралцана.
- **Phase C (Owned GPU):** 50+ customer. Economics favor ownership.

Дэлгэрэнгүйг
[`04-INFRASTRUCTURE-STRATEGY.md`](./04-INFRASTRUCTURE-STRATEGY.md)-с үзнэ.

---

## 5. Холбоотой документ

- [02-ROADMAP.md](./02-ROADMAP.md) — Хэрэгжүүлэх үе шатууд (target-д тааруулсан)
- [03-TECH-SPECS.md](./03-TECH-SPECS.md) — Компонент бүрийн дэлгэрэнгүй
- [04-INFRASTRUCTURE-STRATEGY.md](./04-INFRASTRUCTURE-STRATEGY.md) — 3 үе шатны infra төлөвлөгөө
- [05-ONBOARDING-PLAYBOOK.md](./05-ONBOARDING-PLAYBOOK.md) — Харилцагчийг онбординг хийх playbook
- [06-DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md) — DB + Qdrant schema
- [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md) — Хувийн нууц, DPIA
- [10-PRICING-BUSINESS.md](./10-PRICING-BUSINESS.md) — Pricing tier, unit economics
- [decisions/2026-04-21-centralized-saas-no-customer-hardware.md](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md) — Энэ архитектурын шийдвэрийн ADR

### Archived (superseded but кept as prior art / optional SKU)

- `04-EDGE-DEPLOYMENT.md` — Hybrid edge BOM (архивласан)
- `05-MIGRATION-PLAN.md` — Hybrid → центр migration (архивласан)
- `decisions/2026-04-21-drop-edge-box-hybrid-architecture.md` — On-prem SKU spec хэвээр хүчинтэй

---

Updated: 2026-04-21
