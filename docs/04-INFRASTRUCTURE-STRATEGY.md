# 04 — Infrastructure Strategy: 3-phase server growth

> **Note (2026-04-21):** This document replaces the retired
> [`04-EDGE-DEPLOYMENT.md`](./04-EDGE-DEPLOYMENT.md) (hybrid edge-box
> BOM). That file is archived prior art, still valid for the optional
> **on-prem SKU** defined in
> [`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`](./decisions/2026-04-21-drop-edge-box-hybrid-architecture.md).
> This doc covers the **default product** (centralized SaaS).

## Зорилго

Customer count 0 → 1000 камер хүрэх үе шатанд Chipmo-ийн серверийн
infrastructure-ийг хэрхэн хэмжиж, хэзээ шилжих, ямар cost-ийг хүлээж
авах талаарх стратегийн тодорхойлолт.

---

## 1. High-level phase map

| Phase | Infra | Capacity | MRR range | Duration (planning) |
|---|---|---|---|---|
| **A — Railway** | Railway.app (app + Postgres + Redis). VLM API-р дуудах эсвэл small GPU add-on. | ~20 камер / 3-5 pilot | ₮0 – ₮1M/сар | 1-3 сар |
| **B — Rented cloud GPU** | 1 dedicated GPU server (RunPod / Vast / Hetzner / Lambda). RTX 4090 / A6000 class. | **~200 камер / 40-50 tenant** | ₮1M – ₮15M/сар | 6-18 сар |
| **C — Owned GPU** | 1-2 owned GPU servers (colo эсвэл офис). RTX 5090 / L40S / H100-grade. | **~1000 камер / 200-250 tenant** | ₮15M+/сар | 12+ сар |

**Phase change = infrastructure migration ONLY.** App stack (FastAPI,
Postgres, Redis, Qdrant, Ollama/vLLM) нэгэн адил. Docker Compose →
optionally K3s/Swarm зөвхөн Phase C-д.

---

## 2. Phase A — Railway (MVP + pilot)

### 2.1 Зорилго

- Founder өөрөө deploy хийж, инфра time-н ачаалал минимум.
- 1-3 pilot customer дээр рул engine + dashboard + feedback loop-ийг
  polish хийх.
- Payment + tenant onboarding UX tune хийх.

### 2.2 Railway-ийн бүтэц

```
Railway Project: chipmo-prod
├── Service: api             (FastAPI)
├── Service: worker          (inference + alert worker)
├── Service: web             (React dashboard)
├── Service: postgres        (managed)
├── Service: redis           (managed)
└── Service: qdrant          (Docker image-тай)
```

**Зардал (estimated):**

| Service | Plan | $/сар |
|---|---|---|
| api | Hobby / Starter | $5-20 |
| worker | Starter + volume | $10-25 |
| web | Hobby | $5 |
| postgres | Starter (1 GB) | $10 |
| redis | Starter | $5 |
| qdrant | self-Docker | vol $5 |
| **TOTAL** | | **$40-70** |

### 2.3 GPU стратеги (Phase A-д)

Railway өөр GPU instance санал болгохгүй тул сонголтууд:

**Option 1 (санал болгож буй): External VLM API дамжуулах**
- YOLO CPU-д 3-5 FPS/stream (~2-3 камер)
- VLM-ийг OpenRouter / Modal / Replicate-ээр дуудах ($0.001-0.01 / call)
- Pilot-д хангалттай, real-time алдагдана — **асинхрон alerts**.

**Option 2: Modal / Beam.cloud GPU serverless**
- YOLO + VLM-ийг GPU function-д wrap хийж Railway worker-аас дуудах.
- Cold start 5-15 сек → pilot-д OK.
- Зардал: $0.00015/sec GPU → ~$50-150/сар 2-3 tenant дээр.

**Option 3: Self-managed external GPU VM (Hetzner cheapest GPU or Vast.ai spot)**
- $100-200/сар, 1 RTX 4090 share — Railway-ээс ssh tunnel.
- Phase B-д smooth transition.

**Зөвлөмж:** Option 1-ээр эхэлж, 2 дахь paid customer-д Option 3 рүү
шилжинэ (Phase A → B bridge).

### 2.4 Phase A exit criteria

- ≥1 paid customer (>₮300,000/сар).
- Real-time latency requirement үүснэ (alerts < 5 секундэд).
- Railway-ийн 24/7 GPU load үнэгүй app tier-ыг дүүргэж эхэлнэ.

---

## 3. Phase B — Rented cloud GPU (200 камер хүртэл)

### 3.1 Зорилго

- Реалтайм inference 24/7 үйлчилгээ боломжтой болгох.
- Ямар load pattern бодитоор үүсэж байгааг суралцах (FPS ачаалал,
  peak hour, VLM trigger rate).
- Hardware худалдан авахын оронд elastic-оор scale хийх.

### 3.2 GPU provider сонголт

| Provider | GPU | Pricing (reserved) | Network | Тохиромжтой үе |
|---|---|---|---|---|
| **RunPod** | RTX 4090 | $0.34-0.50/hr (~$250-360/сар) | 1-10 Gbit | 2026 Q2-Q3 (one box) |
| **Vast.ai** | RTX 4090 (consumer) | $0.25-0.40/hr (~$180-290/сар) | Variable | Cost-sensitive, experimentation |
| **Hetzner** | GPU server EX130 (RTX 4000 SFF) | €199/сар | 1 Gbit | EU pilot, DPA ready |
| **Lambda Labs** | A6000 (48 GB VRAM) | $0.80/hr (~$580/сар) | 10 Gbit | VLM-heavy workload |
| **Oracle** | A10 free tier (limited) | ~$0 (trial) | 1 Gbit | POC |

**Санал болгож буй эхний сонголт:** RunPod RTX 4090 reserved ~$300/сар
+ Hetzner CX21 ($5/сар) нэмэлт орчин (Postgres/Redis/VPN hub).

### 3.3 Capacity planning (RTX 4090 reference)

**Нэг RTX 4090-д (24 GB VRAM, 2x NVDEC):**

| Resource | Limit | Realistic sustained |
|---|---|---|
| NVDEC decode (480p H.264) | ~40-60 concurrent | ~30-40 |
| YOLO11s-pose inference | 400+ FPS batched | 250-300 FPS |
| Qwen2.5-VL 7B via vLLM | ~3-5 req/sec batched | ~2-3 req/sec |
| OSNet Re-ID | ~1000 embed/sec | ~500 embed/sec |

**Camera budget:** 5 fps/sub-stream × ~40 streams = 200 inference
frames/sec. YOLO 250 FPS-д 200 FPS fit хийнэ. VLM ~1% frame × 200 FPS =
2 VLM req/sec → vLLM даана.

**Тестээр баталгаажуулах (Phase B-ийн эхний долоо хоногт):** 10 mock
stream → бодит FPS, GPU utilization хэмжих.

### 3.4 Phase B bottleneck scenario + mitigation

| Bottleneck | Sign | Mitigation |
|---|---|---|
| NVDEC dekod | GPU idle, decode 100% | Force 480p/5fps, sub-stream fallback |
| VLM throughput | VLM queue grow | vLLM continuous batching; increase max_num_seqs |
| VRAM | OOM at 40 stream | Swap YOLO11s → YOLO11n for some tenants (SLA-based) |
| Network in | Uplink >800 Mbit | Move peers to closer region, or upgrade to 10 Gbit plan |

### 3.5 Phase B exit criteria (→ C)

Phase C-д шилжих trigger нь эдгээр нэгтээ тохиолдохоос **аль нэг**:

1. Monthly GPU rent >$1000 2 сар дараалан.
2. Customer count >50 эсвэл камер >200 болов.
3. Cloud provider зөвлөсөн pricing жил бүр >15% өсөх.
4. Өгөгдөл нутагших (data sovereignty) шаардлага хууль зүйн ялгаа үүсгэх.

Break-even тооцоо:
```
Owned server (RTX 5090 class): $5,500 CAPEX + $200/сар colo
= $5,500 / 24 сар + $200 = ~$430 / сар амортжсан
Rent RTX 4090: $300-360/сар (1 box)
```
Rent ~$500-650/сар болох үед (2 box rent эсвэл бага бичлэгт ахисан)
own-ийн эдийн засаг ялгарна.

---

## 4. Phase C — Owned GPU server (1000 камер хүртэл)

### 4.1 Зорилго

- Unit economics-ийг сайжруулан margin-ийг 15-25% ↑.
- Network control → latency <5ms харилцагчийн VPN peer-ээс.
- Privacy posture: "Chipmo-ийн өөрийн хөдөлгөөнгүй серверт" commitment.

### 4.2 Recommended BOM (1 production box)

| Component | Model | Юу хэрэглэх вэ | Үнэ (USD, 2026 Q2 estim.) |
|---|---|---|---|
| GPU | NVIDIA RTX 5090 (32 GB) эсвэл L40S (48 GB) | Inference + VLM | $2,000-5,000 |
| CPU | AMD Ryzen 9 7950X эсвэл EPYC 7443 | RTSP demux, orchestration | $500-1,200 |
| RAM | 128 GB DDR5 ECC | Postgres, Redis, Qdrant cache | $500 |
| Storage | 2× 4 TB NVMe (RAID1) + 1× 8 TB HDD | Hot + warm data | $700 |
| NIC | 2× 10 GbE (Intel X710) | Uplink redundancy | $300 |
| PSU | 1000W 80+ Platinum Redundant | Uptime | $400 |
| Chassis | 2U rackmount | Colo-д тавих | $400 |
| UPS (site-optional) | APC SMT1500RMI2U | Brownout protection | $500 |
| **Total hardware** | | | **~$5,300 - $9,000** |

### 4.3 Colo vs office placement

| Option | Pros | Cons |
|---|---|---|
| **Колoc зоорь (UB)** | Лоукал latency, DPO review shorter | Пол reliability маш чухал, uplink redundancy бага |
| **Офис дээр** | Тохируулалтад маш хялбар, дотоод access | Power/cooling амжилт, SLA-ийн хувьд эрсдэлтэй |
| **Ulaanbaatar datacenter (MCS/Mobicom/Gmobile)** | ₮500k-1M/сар rack + 100 Mbps, Mongolian jurisdiction | SLA шалгуур тохиролцоо хэрэгтэй |
| **Regional hyperscaler (Singapore/Tokyo)** | Дэлхий талийсан tier 3, 99.99% uptime | Монголын data sovereignty hard |

**Phase C-ийн анхдагч байршил:** Ulaanbaatar datacenter (e.g. MCS
Datapro, DataMax). Хоёрдахь box нь availability-д regional hyperscaler.

### 4.4 Phase C operational readiness checklist

- [ ] Hardware purchase order approved + lead time (4-8 долоо хоног)
- [ ] Colo contract, rack U, power, uplink SLA (99.9%+)
- [ ] IPMI / iLO remote management with OOB network
- [ ] Backup stratgy: nightly Postgres pg_dump + Qdrant snapshot → S3-compatible
- [ ] On-call rotation (Founder + 1 engineer minimum)
- [ ] Phase B → Phase C migration plan (см `docs/06-DATABASE-SCHEMA.md` migration section)
- [ ] DR (Disaster Recovery) runbook: 4-hour RPO, 12-hour RTO минимум

### 4.5 Multi-region (Phase C+)

Phase C хоёр дахь box-г secondary region-д (Singapore эсвэл Эрээн) —
active/passive replica. Phase C-д хангалттай болсоны дараа
(>500 камер) зэрэгцүүлэн идэвхжүүлэх.

---

## 5. Cost per camera (planning estimate)

Амортжсан GPU + infra зардлыг per-camera-per-month дээр тогтоох нь
pricing-д хэрэгтэй:

| Phase | GPU / infra зардал/сар | Камер тоо | Cost per camera/сар |
|---|---|---|---|
| A (Railway + external VLM) | $100-200 | 10-20 | $5-20 |
| B (RunPod RTX 4090) | $350 + $50 infra = $400 | 150 камер | **~$2.7** |
| C (owned RTX 5090) | $430 амортжсон + $200 colo + $100 power = $730 | 800 камер | **~$0.9** |

**Замын map-аас харахад:** Phase C-д cost-per-camera зөвхөн ~$0.9.
Харин pricing tier-ийн per-camera $30-70 → **gross margin >90%** Phase
C-д. Энэ нь Phase B-д ~$2.7 / camera → margin ~85%. Phase A-д margin
нимгэн, учир нь pilot.

Дэлгэрэнгүй [10-PRICING-BUSINESS.md](./10-PRICING-BUSINESS.md)-т
тусгагдсан.

---

## 6. Observability infrastructure

Бүх phase-д нэгэн адил stack:

```
  app (api, worker)
       │
       ▼
  Prometheus (scrape)      Loki (log)
       │                      │
       └──────────┬───────────┘
                  ▼
              Grafana
                  │
          Alertmanager
                  │
         Telegram / Email
```

- **Phase A:** бүгд Railway-д 1 service-т багтана.
- **Phase B:** Grafana Cloud-ийн free tier ашигла (10k series, 50 GB log).
- **Phase C:** self-hosted Grafana + Prometheus + Loki owned box дээр.

Alert rules: GPU utilization >85% 10 мин, VLM queue >50, decode fps
drop, tenant uplink <1 Mbit.

---

## 7. VPN ingress infrastructure

WireGuard hub:

- Phase A: Railway дээр WireGuard sidecar container, 1 CPU-ийн.
- Phase B/C: GPU server-ын CPU дээр native kernel WireGuard (kernel 5.6+).

Peer config generation automation:

```bash
# Tenant онбординг үед
./scripts/provision-vpn-peer.sh --tenant-id <id> --cameras <n>
# Output: wg0.conf + QR code + peer IP in 10.100.<tenant_octet>.2/32
```

Бүх peer нь **per-tenant /32** subnet-т байна, inter-peer communication
default deny (iptables rule). Harilцаа зөвхөн tenant peer ↔ Chipmo hub.

---

## 8. Operational costs summary (Phase-ээр)

| Зардлын зүйл | Phase A | Phase B | Phase C |
|---|---|---|---|
| App + DB hosting | $40-70 | $50-100 | $0 (owned) |
| GPU | $100-200 (serverless) | $300-400 (rent) | $430 (amort) + $100 power |
| Network | incl. | $50 (uplink) | $100-200 (colo uplink) |
| Observability | Grafana Cloud free | Free | Self-host $20 storage |
| Backups | Railway incl. | $10-20 (B2/Wasabi) | $20 |
| VPN (routers) | Customer CAPEX | Customer CAPEX | Customer CAPEX |
| **TOTAL INFRA/сар** | **~$150-300** | **~$430-570** | **~$770-850** |

Phase change trigger = Phase A→B: эхний paid real-time customer.
Phase B→C: §3.5 шалгуур.

---

## 9. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Railway-ийн pricing доошлол эсвэл GPU өгсөнгүй | Phase A extend | Modal / Lambda Cloud backup plan |
| Cloud GPU provider-ийн 1 instance down (Phase B) | Service outage бүх tenant-д | Dual-provider (RunPod primary + Vast fallback), DNS failover |
| Owned server hardware failure (Phase C) | RPO/RTO outage | Multi-region replica, warm standby |
| Mongolian datacenter power/network | Regional outage | International colo (Singapore) DR site |
| Customer internet outage (all phases) | Tenant-d service drop | VPN appliance 24h local ring buffer, 4G fallback router optional |
| GPU capacity misplanned | Tenant SLA break | Dynamic FPS governor, tenant SLO tier (best-effort vs. guaranteed) |

---

## 10. Related documents

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) — Architecture overview
- [02-ROADMAP.md](./02-ROADMAP.md) — Phase хөгжүүлэлтийн task
- [03-TECH-SPECS.md](./03-TECH-SPECS.md) — Ingest + VLM spec
- [05-ONBOARDING-PLAYBOOK.md](./05-ONBOARDING-PLAYBOOK.md) — Customer VPN setup
- [10-PRICING-BUSINESS.md](./10-PRICING-BUSINESS.md) — Unit economics

### Superseded / archive

- `04-EDGE-DEPLOYMENT.md` — hybrid edge BOM (on-prem SKU-д үлдсэн)

---

Updated: 2026-04-21
