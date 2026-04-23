# 02 — Development Roadmap (3-phase infrastructure aligned)

> **Note (2026-04-21):** This roadmap is aligned to the 3-phase
> infrastructure strategy defined in
> [`04-INFRASTRUCTURE-STRATEGY.md`](./04-INFRASTRUCTURE-STRATEGY.md)
> and the centralized SaaS architecture in
> [`decisions/2026-04-21-centralized-saas-no-customer-hardware.md`](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md).
> Previous 4-phase edge-box roadmap is retired.

## Зорилго

Одоогийн rule-based / центрлэсэн MVP-аас target state-руу шилжих
хөгжүүлэлтийн төлөвлөгөө. Engineering phase (0-4) + infrastructure
phase (A/B/C) хоёрыг параллель бичнэ.

---

## 0. Нэр томъёо

- **Engineering Phase (0-4):** Код, модел, feature хөгжил (нэг
  phase = хэд хэдэн sprint).
- **Infra Phase (A/B/C):** Сервер инфраструктурын үе
  (Railway → Cloud GPU → Owned GPU).
- Хоёр phase нь өөр хугацаанд цуваа: engineering phase 2-ийг
  infrastructure phase B-д ажиллуулахад оновчтой гэх мэт.

Дараах хүснэгт хоёр phase-ын холбоог харуулна:

| Eng. phase | Feature mass | Infra phase required |
|---|---|---|
| 0 — Current pilot (rule-based) | AS-IS | A (Railway) |
| 1 — Quick wins + VPN onboarding | Alert dedup, ByteTrack tune, metrics, night-mode, VPN peer automation | A |
| 2 — Batched inference + RAG | NVDEC batching, Qdrant per-tenant, layer-2 filter | **A → B gate** |
| 3 — VLM + Re-ID + auto-learn | vLLM Qwen2.5-VL, OSNet, weekly retrain, shared taxonomy | B |
| 4 — Scale + HA + multi-region | K3s, owned box migration, DR, regional replica | **B → C gate** |

---

## 1. Engineering Phase 0 — Current state (AS-IS)

**Status:** Shipped. Pilot-д ажиллаж байна.

- FastAPI + Postgres + Redis + React dashboard
- YOLO11m-pose + 6-signal rule-based + 150-frame accumulator
- Weight-only auto-learning (20+ feedback-тэй үед)
- Telegram basic alerts
- Multi-tenant isolation (2026-04-21 audit — passed)

**Хязгаарлалт:** [`01-ARCHITECTURE.md`](./01-ARCHITECTURE.md) §1.3

---

## 2. Engineering Phase 1 — Quick wins + VPN onboarding (2-3 долоо хоног)

**Infra:** Railway-д (Phase A).

Яаралтай засах ёстой, өндөр impact-тай шинэчлэлүүд + харилцагчийн
онбординг automation. Одоогийн pilot-ын чанарыг шууд сайжруулна.

### Sprint 1.1 (1 долоо хоног) — Alert quality

- [ ] **Alert dedup fix** — Per-person cooldown 60 сек, `alert_state`
  table. Acceptance: нэг event 1 Telegram.
- [ ] **ByteTrack параметр tune** — `track_high_thresh 0.5 → 0.6`,
  `track_buffer 30 → 60`. Acceptance: ID алдагдал <5%.
- [ ] **Metrics endpoint** — Prometheus format `/metrics`. Counters:
  alerts_total, false_positives_total. Histograms: inference_latency.
  Acceptance: Grafana dashboard-д FP rate / store.
- [ ] **Night mode adaptive threshold** — Frame brightness detect,
  <60 lumens = night mode (threshold ×1.3). Acceptance: night FP
  ≤ day FP × 1.2.
- [ ] **Clip retention policy** — 48h normal, 30 хоног alert clip,
  unlimited labeled clip. Daily cron cleanup.

### Sprint 1.2 (1 долоо хоног) — VPN + onboarding automation

- [ ] **WireGuard hub на Railway** — sidecar container, udp port
  51820 exposure. Static config template.
- [ ] **Peer provision script** — `provision-vpn-peer.sh`: tenant_id
  оролт, `wg0.conf` + QR code output.
- [ ] **ONVIF sub-stream auto-config tool** — Script (`onvif-config.py`)
  камерын creds оролттойгоор sub-stream-ийг 480p / 5-10fps-д тохируулна.
  Supported vendor: Hikvision, Dahua, TP-Link, EZVIZ (ONVIF Profile S).
- [ ] **Bandwidth monitor** — Ingest worker-т `tenant_uplink_bitrate`
  gauge. Alert <1 Mbit/60s.
- [ ] **Camera disconnect handling** — RTSP reconnect exponential
  backoff, 5+ мин = alert. `camera_health` heartbeat table.

### Sprint 1.3 (optional, 0-1 долоо хоног) — Foundational gaps

- [ ] **Feedback labelling UI** — Dashboard-д "True / False / Unclear"
  button, notes field, `event_feedback` table. (Tier 1 moat work.)
- [ ] **Tenant MSA + DPIA template draft** — Legal (Mongolian).
  [`09-PRIVACY-LEGAL.md`](./09-PRIVACY-LEGAL.md)-т тусна.

### Phase 1 exit criteria

- Harилцагч VPN onboarding 1-2 цагт ажиллана (manual оролцоо <10 мин).
- FP rate хэмжигдэж байна + Grafana dashboard-д харагдана.
- Night mode-д FP огцом өсөхгүй болно.
- Feedback loop data цуглуулж эхэлсэн.

---

## 3. Engineering Phase 2 — Batched inference + RAG (4-6 долоо хоног)

**Infra:** Phase A → Phase B шилжинэ (Phase 2-ын середина).

### Sprint 2.1 (2 долоо хоног) — Ingest + decode optimization

- [ ] **NVDEC batched decoder** — PyAV + CUDA decoder, 8-стрийм batch.
  Acceptance: single RTX 4090-д 40 concurrent 480p stream decode.
- [ ] **Dynamic FPS governor** — Per-tenant FPS тохиргоо (3/10/30).
  SLA tier-д хамаарна. Идлэ тенант → 3 FPS, active → 10 FPS.
- [ ] **Async Ingest pipeline** — Redis Streams, ingest worker shard
  per tenant. Pod autoscale (Phase B-д).
- [ ] **VPN hub production deployment** — Railway-ээс cloud GPU-руу
  WireGuard migrate. Tenant peer re-issue automation.

### Sprint 2.2 (2 долоо хоног) — RAG foundation

- [ ] **Qdrant setup per-tenant** — `tenant_{id}_case_memory` collection.
  CLIP embedding for alert clip + text summary.
- [ ] **Event ⇒ embedding pipeline** — Confirmed alert → 10 sec clip →
  CLIP vector → Qdrant write.
- [ ] **Layer 2 filter: RAG similarity check** — Threshold-ээс хэтэрсэн
  event-ыг өмнөх case-тай top-5 compare. Cos sim > 0.85 + label=FP =
  auto-suppress. Acceptance: FP rate нэмэлт 15-25% drop.
- [ ] **Shared taxonomy collection (foundational)** — `behavior_taxonomy_v1`
  collection үүсгэх. Pose trajectory embedding schema. Anonymization
  layer (remove face crop, remove tenant_id metadata).
  [`06-DATABASE-SCHEMA.md`](./06-DATABASE-SCHEMA.md).

### Sprint 2.3 (1-2 долоо хоног) — Phase A → B migration

- [ ] **Cloud GPU provisioning** — RunPod RTX 4090 reserved 1 box.
  Docker Compose stack.
- [ ] **Data migration** — Railway Postgres → cloud Postgres (
  `pg_dump` + `pg_restore`). Downtime <30 min. Schema migration lock
  applies ([`07-SCHEMA-MIGRATION-LOCK.md`](./07-SCHEMA-MIGRATION-LOCK.md)).
- [ ] **VPN hub migration** — Static peer config-ийг tenant-аас re-issue
  хийхгүйгээр нүүлгэж чадах endpoint rotation procedure.
- [ ] **Phase B smoke test** — 5-10 mock tenant, 20-40 concurrent streams,
  48h soak test.

### Phase 2 exit criteria

- RAG layer-2 shipped, FP rate drop бодитоор хэмжигдсэн.
- Batched NVDEC-оор 1 GPU 30+ stream sustained.
- Phase B infra-д 1 week stable.
- Shared taxonomy collection structure locked (even if empty).

---

## 4. Engineering Phase 3 — VLM + Re-ID + auto-learning (6-10 долоо хоног)

**Infra:** Phase B (stable).

### Sprint 3.1 (2 долоо хоног) — VLM integration

- [ ] **vLLM Qwen2.5-VL 7B deployment** — Continuous batching, `max_num_seqs=32`.
  GPU share with YOLO (MPS or separate CUDA stream).
- [ ] **Layer 3 VLM verification** — RAG-ээс pass хийсэн event clip →
  Qwen2.5-VL → prompt: "Энэ хүн хулгайлах үйлдэл хийж байна уу?
  Шалтгаанаа тайлбарла. Яаралтай байдал 1-10." → parse structured response.
- [ ] **Prompt library** — Монгол + Англи prompt templates.
  Per-store customization (e.g. "Чэлэнэй банк бол..." context).
- [ ] **VLM latency budget** — P95 <2 сек, P50 <800ms.
- [ ] **Fallback** — VLM down / timeout бол rule+RAG score-ыг ашиглах.

### Sprint 3.2 (2 долоо хоног) — OSNet Re-ID

- [ ] **OSNet per-tenant gallery** — Re-ID embedding 512-dim, Qdrant
  `tenant_{id}_reid_gallery`. New person detect → embed → gallery write.
  Existing match (cos > 0.75) → ID reuse.
- [ ] **Cross-camera tracking** — Нэг tenant доторх олон camera дахь
  ID holbolt. Acceptance: 2-camera setup-д person ID 90%+ хадгалагдана.
- [ ] **Night mode тохируулалт Re-ID-д** — Лом light-д feature drift
  issue → data augmentation.
- [ ] **Re-ID GDPR-safe retention** — 30 хоногт автоматаар purge, tenant
  opt-in only. [`09-PRIVACY-LEGAL.md`](./09-PRIVACY-LEGAL.md).

### Sprint 3.3 (2-3 долоо хоног) — Auto-learning v2

- [ ] **Hard-negative mining** — Labeled FP clip → training set → weekly
  YOLO finetune (LoRA). Per-tenant adapter.
- [ ] **Active learning queue** — VLM low-confidence (0.4-0.6) → label
  UI-д priority нэмнэ.
- [ ] **Shared behavior taxonomy writer** — Confirmed alert-ын pose
  trajectory → anonymized embedding → shared collection.
  Tenant opt-in default ON. Opt-out tenant никогда не contribute.
- [ ] **Weekly retrain cron** — Kubernetes CronJob (эсвэл Phase B-д
  Docker cron container). Output: updated weights.json + Qdrant new entries.
- [ ] **A/B harness** — Шинэ weight vs. хуучин weight сонголтыг 20/80
  traffic split дээр 3 хоног хэмжих.

### Sprint 3.4 (1-2 долоо хоног) — Observability + SLA hardening

- [ ] **Full Grafana dashboards** — Per-tenant: FP rate, alert volume,
  alert-to-confirm latency, GPU util, VLM queue.
- [ ] **Loki log aggregation** — Structured logging (JSON), tenant_id
  tag бүх log line-д.
- [ ] **Alertmanager rules** — P1 (service down, VLM queue >100), P2
  (FP rate spike, camera disconnect >10 min), P3 (storage 80%).
- [ ] **SLO documentation** — Tenant-facing SLA: 99% alert delivery, P95
  latency < 5 sec end-to-end.

### Phase 3 exit criteria

- VLM Layer 3 shipped, FP rate rule-only-аас 50-80% buured.
- OSNet cross-camera Re-ID 90%+ accuracy (2-camera-тай tenant-д).
- Weekly retrain cronjob successful 4 хоногийн турш.
- Shared taxonomy collection-д 500+ anonymized pattern (первый 3 active tenant).

---

## 5. Engineering Phase 4 — Scale + HA + Phase C migration (8-12 долоо хоног)

**Infra:** Phase B → Phase C (owned GPU).

### Sprint 4.1 (2 долоо хоног) — Phase C hardware procurement

- [ ] **Final BOM lock** — GPU sku choice (RTX 5090 vs L40S),
  CPU/RAM/NIC combo.
- [ ] **Colo contract** — Ulaanbaatar datacenter rack U, 100 Mbps
  uplink, 99.9% SLA.
- [ ] **Server build + burn-in** — 7-хоногийн soak test.
- [ ] **IPMI / OOB network config.**
- [ ] **Backup infra** — S3-compatible (Wasabi / Backblaze B2) storage
  account, cron backup scripts.

### Sprint 4.2 (2-3 долоо хоног) — Orchestration uplift

- [ ] **Docker Compose → K3s (optional)** — Tenant count >50 бол K3s
  уудахад утга учиртай. Node affinity per-tenant шаардлагтай бол.
- [ ] **Horizontal ingest scaling** — Ingest worker-г stateless болгоод
  Deployment-д хувиргана. Load balancer шаардлагатай.
- [ ] **Postgres HA** — Patroni + etcd, primary + 1 warm standby.
- [ ] **Qdrant cluster mode** — 3-node cluster, replica 2.
- [ ] **Redis Sentinel** — 3-node, automatic failover.

### Sprint 4.3 (2-3 долоо хоног) — Phase B → C migration

- [ ] **Data migration runbook** — pg_dump + Qdrant snapshot → ownned
  box restore. Downtime budget ≤ 2 hours (weekend).
- [ ] **VPN hub move** — Tenant peer-д endpoint rotation 48-hour
  notice. Dual-active window.
- [ ] **DNS + TLS cutover** — Low TTL 24 hours prior, cutover window
  late-night weekend. Rollback plan committed.
- [ ] **Smoke test on owned box** — 48h parallel traffic shadowing
  (mirrored traffic) before cutover.

### Sprint 4.4 (2-3 долоо хоног) — Disaster Recovery + Multi-region option

- [ ] **DR runbook** — RPO 4h, RTO 12h. Hot standby in secondary
  datacenter (Singapore эсвэл Hetzner FSN).
- [ ] **Multi-region replication** — Postgres streaming replication,
  Qdrant replication to standby.
- [ ] **Tested failover** — Quarterly DR drill.
- [ ] **Status page** — status.chipmo.mn public page.

### Phase 4 exit criteria

- Owned box production-д 30+ хоног stable, 99.9% SLA met.
- DR drill passed.
- Customer count 50+, cloud rent sunset-гүйгээр paid off.

---

## 6. Cross-phase horizontal tracks

### 6.1 Product / dashboard (continuous)

Sprint-ийн нэмэлт 10-20%-г дараах work-д зарцуулна:

- Dashboard UX improvements (founder feedback + customer request)
- Report generation (weekly PDF per tenant)
- Multi-user permission (manager vs staff)
- Mobile app (Flutter) — Phase 3-р уухаасаа

### 6.2 Business / commercial (continuous)

- Sales pitch, pricing tier adjustments (see [10-PRICING-BUSINESS.md](./10-PRICING-BUSINESS.md))
- Customer success playbook
- Testimonial / case study хүртээл

### 6.3 Legal / compliance (continuous)

- DPIA finalize (before first paid customer)
- MSA / DPA template finalized
- Mongolian хувийн нууцын хуулийн дагуу audit trail
- See [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md)

---

## 7. Timeline illustration (aggressive planning estimate)

```
Week 1-3  [Phase 1 — Quick wins + VPN]         Infra A
Week 4-10 [Phase 2 — Batch + RAG]              Infra A → B (mid-phase)
Week 11-24 [Phase 3 — VLM + Re-ID + auto-learn] Infra B
Week 25-40 [Phase 4 — Scale + HA + Phase C]     Infra B → C
Week 40+   [Phase 5+ — Multi-region, fine-tune] Infra C
```

Ганц founder + 1 engineer load (2026). Bigger team-тэй бол timeline
хумигдана.

---

## 8. Risk tracking

| Risk | Phase impact | Mitigation |
|---|---|---|
| Founder bandwidth хязгаарлагдмал | Бүх phase | Phase 1-ийн scope-г уян хатан байлга |
| Phase 2-т mock stream дутагдал | Phase 2 gate | Simulator-тай тест, early customer stream capture |
| Cloud GPU availability | Phase B гацна | Dual-provider (RunPod + Vast) |
| Qdrant scale issue >10M vectors | Phase 3-4 | Sharding plan early, HNSW tuning |
| Mongolian data sovereignty regulation | Phase B-с эхлээд | Colo-гаа эхнээс Mongolian datacenter-д reserve |

---

## 9. Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) — Architecture overview
- [03-TECH-SPECS.md](./03-TECH-SPECS.md) — Component spec
- [04-INFRASTRUCTURE-STRATEGY.md](./04-INFRASTRUCTURE-STRATEGY.md) — Infra phase A/B/C
- [05-ONBOARDING-PLAYBOOK.md](./05-ONBOARDING-PLAYBOOK.md) — Customer onboarding
- [06-DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md) — DB + Qdrant schema
- [07-API-SPEC.md](./07-API-SPEC.md) — API contracts
- [07-SCHEMA-MIGRATION-LOCK.md](./07-SCHEMA-MIGRATION-LOCK.md) — DB change policy
- [TASKS.md](./TASKS.md) — Active task board

---

Updated: 2026-04-21
