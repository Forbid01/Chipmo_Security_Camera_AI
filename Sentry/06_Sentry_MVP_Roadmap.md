# Sentry — Cloud-Only SaaS Roadmap
## Chipmo → Sentry v1.1 Transformation Plan

**Баримтын дугаар:** DOC-06
**Хувилбар:** 1.0
**Огноо:** 2026-04-22
**Статус:** Active planning (pilot-ын явцад шинэчлэгдэнэ)
**Холбогдох:** `01_Sentry_PRD_v1.1.md`, `03_Sentry_Pricing_Business_Model.md`, `04_Sentry_Onboarding_Flow.md`, `05_Sentry_Multi_Tenancy_Architecture.md`

---

## 1. Товч танилцуулга

Одоогийн Chipmo codebase нь **Sentry v1.1 PRD-ийн ~35–45%-ийг** биелүүлж байна. Энэ roadmap нь одоогийн FastAPI монолит + YOLO11 detection engine-ээс **cloud-only multi-tenant SaaS** хүрэх замыг **3 phase, ~12 сарын дотор** тодорхойлж байна.

### 1.1 Одоогийн төлөв (baseline)

✅ **Бэлэн зүйлс:**
- YOLO11-pose + ByteTrack detection pipeline
- Feedback-based auto-learner (per-store threshold + weights)
- Multi-tenant row-level isolation (organization_id + Postgres RLS)
- Pricing calculator endpoint (29K platform + tiered per-camera)
- Telegram notification (snapshot + HTML caption)
- Prometheus + Grafana + Loki observability stack
- Audit log + cross-tenant regression tests
- Edge architecture артефакт арилгагдсан (cloud-only focus)

❌ **Дутуу зүйлс (Sentry v1.1 шаардсан):**
- Self-service onboarding (15-мин flow)
- QPay + Stripe billing + invoice pipeline
- Per-tenant API key + rotation + 2FA
- Resource quotas + tenant lifecycle (trial/active/suspended/grace/churned)
- Cross-camera Re-ID runtime (OSNet)
- VLM scoring (Qwen2.5-VL) runtime
- 4-level GREEN/YELLOW/ORANGE/RED scoring
- ONVIF auto-discovery + RTSP auto-detect
- WebRTC live stream (<2s latency)
- Docker agent installer + ONVIF wizard
- Telegram bot commands + inline acknowledge buttons
- Customer portal (billing, team, audit, usage)
- Status page, PostHog analytics, Resend email

### 1.2 Guiding principles

1. **Cloud-only.** On-premise / edge box хувилбар **хамаарахгүй**. Бүх inference нь Sentry-ийн GPU pool дээр.
2. **Tenant-first.** Шинэ бүх API, репозитор, worker нь `tenant_id`-ээр шүүгдэнэ. `get_current_tenant` FastAPI dependency заавал дамжина.
3. **Additive migrations.** Data destructive migration байхгүй. Дата алдалгүйгээр rollback хийх боломжтой.
4. **Feature-flag first.** Бүх шинэ pipeline (Re-ID, VLM, WebRTC) `settings`-д гарсан flag-ээр асаана.
5. **Mongolian-first.** UI, Telegram алерт, invoice бүгд монгол хэл default.
6. **Test-driven.** FR бүр rollout-оос өмнө pytest + contract-тэй.

---

## 2. Phase 1 — MVP (Months 1–3)

**Зорилго:** 1 pilot харилцагчтай production deploy, self-service signup → first detection <15 мин, Telegram bot амжилттай, QPay live.

### 2.1 Milestones

| Week | Milestone |
|---|---|
| W1–2 | Tenant UUID + API key schema migration |
| W3–4 | Self-service signup + OTP verification |
| W5–6 | QPay checkout + webhook + tenant lifecycle |
| W7–8 | Docker agent installer + ONVIF auto-discovery |
| W9–10 | 4-level scoring + Telegram bot commands + inline buttons |
| W11 | Pilot onboarding rehearsal |
| W12 | Pilot go-live + P0 bugfix |

### 2.2 Workstreams

#### WS-1: Tenant foundation (FR-11, FR-14)
- UUID-base `tenants` table (legal_name, plan, status, resource_quota JSONB)
- `organization_id` → `tenant_id` migration layer (backward-compat view)
- Per-tenant API key (`sk_live_*`, SHA-256 hash, rotatable)
- Resource quotas enforced at write path (max_cameras, max_stores, max_api_calls)
- Tenant lifecycle state machine (pending → active → suspended → grace → churned)
- 90-day grace period + data wipe job

#### WS-2: Self-service onboarding (FR-12)
- `/signup` + email OTP + phone verification
- `/plan` picker (Starter/Pro/Enterprise auto-recommend based on camera count)
- `/checkout` (QPay + Stripe fallback)
- 14-day trial (no credit card required)
- Email verification + welcome email sequence (Resend)
- PostHog onboarding funnel tracking

#### WS-3: Billing & subscription (FR-13)
- QPay integration (Mongolia) — checkout session, webhook receiver, invoice URL
- Stripe integration (international) — checkout, subscription, customer portal
- НӨАТ-тай invoice PDF generation (Mongolian template)
- Failed payment retry schedule (day 3, 7, 14) → suspension
- Plan upgrade/downgrade self-service

#### WS-4: Docker agent + ONVIF (FR-1, FR-12)
- Agent Dockerfile + config.yaml template with signed API key
- Windows `.exe` + Linux `.sh` installer bundles
- ONVIF WS-Discovery probe + common RTSP URL patterns
- Camera test connection (decode 1 frame, return preview)
- Agent heartbeat to `api.sentry.mn` every 60s
- WebSocket `/api/onboarding/status` for real-time installer updates

#### WS-5: Alerting v1.1 (FR-7)
- 4-level classification: GREEN (0–40) / YELLOW (40–70) / ORANGE (70–85) / RED (85–100)
- Telegram bot command handler: `/start`, `/status`, `/today`, `/alerts`, `/help`
- Inline acknowledge button (acknowledge / view / dismiss)
- Multiple manager subscribe per store
- Email alerts (Resend)
- Push notification (FCM) for ORANGE/RED
- SMS (Twilio) for RED

#### WS-6: Observability & status
- Status page at `status.sentry.mn` (Better Stack / Statuspage)
- Onboarding funnel dashboard (`/admin/onboarding-funnel`)
- Per-tenant GPU usage metric + alert on quota breach
- Sentry SDK tenant tag (already wired up, add tenant_id context)

### 2.3 Acceptance criteria

- [ ] 1 pilot customer production deploy
- [ ] 8–12 камер simultaneously, 1 store
- [ ] Self-service signup → first detection median **<15 мин**
- [ ] QPay payment success rate **>95%**
- [ ] Telegram bot live, inline acknowledge тест ажиллаж байна
- [ ] False positive rate **<15%**
- [ ] 14-day trial → paid conversion нь mechanism-тай
- [ ] Tenant data isolation pen test OK (IDOR attempt блоклогдох)
- [ ] Onboarding funnel PostHog-т хэмжигдэж байна

### 2.4 Risk & mitigation

| Risk | Mitigation |
|---|---|
| QPay integration delay | Stripe хамт хөгжүүлэх, parallel implementation |
| 15-мин setup-т ONVIF discovery амжихгүй | Manual RTSP fallback, Calendly support call |
| Pilot drop-out | 30-day money-back, hands-on onboarding |
| Tenant data leak (multi-tenancy bug) | RLS + application layer double check, weekly pen test |

---

## 3. Phase 2 — Growth (Months 4–9)

**Зорилго:** 10 paying customers, MRR ₮3–5 сая, false positive <10%, mobile app, cross-camera Re-ID.

### 3.1 Milestones

| Month | Milestone |
|---|---|
| M4 | Cross-camera Re-ID (OSNet) runtime + Qdrant |
| M5 | VLM verifier (Qwen2.5-VL 4-bit) deployed |
| M6 | Mobile app beta (iOS + Android, React Native) |
| M7 | Multi-store owner view + team management |
| M8 | Feedback loop retraining pipeline |
| M9 | 10 paying customers, case study launch |

### 3.2 Workstreams

#### WS-7: Cross-camera Re-ID (FR-3)
- OSNet 512-dim embedding extractor in inference worker
- Qdrant per-tenant collection: `reid_tenant_{uuid}`
- Cosine similarity >0.75 threshold, 5s handoff window
- Person ID format: `P-{store}-{date}-{seq}`
- 30-min state persist in Redis (`tenant:{uuid}:store:{id}:person:{pid}`)
- Bie biLeg (gait) + height fallback (P1 priority)

#### WS-8: VLM verification (FR-4) ✅ **DONE** (Apr 2026)
- ✅ Qwen2.5-VL 7B on `transformers` (vLLM 4-bit quant deferred to GPU deploy ops)
- ✅ Alert-д action description generate (`vlm_service.describe_alert` → caption + structured JSON)
- ✅ `rag_decision` + `vlm_decision` columns бичигдэж байна (`ai_service._dispatch_alert`)
- ✅ Suppression pipeline: YOLO → RAG (`rag_retriever` on pgvector) → VLM verify (`vlm_service`) → alert (`rag_vlm_pipeline`)
- ⚠️ VLM latency <500ms target — current 1-5s on single GPU; achievable with vLLM batching (P2 follow-up)
- ➕ Bonus: RAG corpus CRUD API (`/api/v1/stores/{id}/rag-corpus`) + frontend (`RagVlmSettings`, `AlertVlmDetail`, `AlertVerdictBadges`)
- ➕ Migration `20260427_01` (`rag_corpus`, `vlm_annotations`) + Qdrant compose service + `Dockerfile.gpu`

#### WS-9: Mobile app (FR-6, FR-8)
- React Native codebase
- Live multi-camera grid (1/4/9/16)
- Alert queue with severity filter
- Push notification (FCM)
- Offline queue when network drop
- iOS App Store + Android Play Store launch

#### WS-10: Live streaming v2 (FR-6.1)
- MediaMTX ingest layer
- RTSP → WebRTC converter
- Peer-to-peer live view (<2s latency)
- TURN server fallback for NAT traversal
- Bandwidth optimize: sub-stream (640x480) for grid view, main-stream for single-camera

#### WS-11: Customer portal (FR-14)
- Sidebar nav: Dashboard / Cameras / Alerts / Team / Billing / Settings
- Team member invite (Owner/Manager/Viewer/Billing roles)
- Billing history + invoice PDF download
- Payment method update
- Usage stats (cameras, alerts, GPU time) with quota gauge
- 2FA setup
- API key management + rotation UI
- Audit log viewer

#### WS-12: Retraining pipeline (FR-10)
- Weekly cron: export feedback-labeled clips
- Fine-tune per-store threshold + weights (already exists)
- Fine-tune YOLO11-pose на aggregated labeled dataset (anonymized)
- A/B test new weights against production on 10% traffic
- Rollback automation if precision drops

### 3.3 Acceptance criteria

- [ ] 10 paying customers
- [ ] MRR ₮3–5M
- [ ] Cross-camera Re-ID accuracy **>85%**
- [ ] VLM false positive suppression **>30%** improvement
- [ ] Mobile app 4.0+ rating in stores
- [ ] Monthly churn **<5%**
- [ ] Trial-to-paid conversion **>20%**

---

## 4. Phase 3 — Scale (Months 10–12)

**Зорилго:** 50+ customers, MRR ₮20–30 сая, Enterprise tier launch, 99.5% uptime.

### 4.1 Milestones

| Month | Milestone |
|---|---|
| M10 | Enterprise tier (dedicated GPU, SSO/SAML, custom DPA) |
| M11 | Sharded DB + multi-region fallback (Korea) |
| M12 | 50+ customers, SOC 2 Type 1 kickoff |

### 4.2 Workstreams

#### WS-13: Enterprise tier
- Dedicated GPU instances (no shared quota)
- SSO/SAML integration (Okta, Azure AD)
- Custom action weight fine-tuning
- Custom DPA contracts
- 24/7 phone support
- SLA contract (99.5%+)

#### WS-14: Scale infrastructure
- Sharded PostgreSQL per region (tenant_id-based sharding)
- Multi-region deploy (Mongolia primary, Korea fallback)
- GPU pool auto-scaler (add RTX 5090 when queue >10)
- Read replica for analytics
- Archive cold alerts to S3 Glacier

#### WS-15: Compliance & audit
- SOC 2 Type 1 readiness
- Penetration test (external vendor)
- Mongolian privacy law full compliance audit
- Right-to-be-forgotten automation (30-day SLA)
- Customer data export tool

#### WS-16: Analytics & heatmap (Phase 2 overflow)
- Customer flow heatmap per store
- Peak hour analysis
- Demographic insights (anonymized, opt-in)
- Weekly auto-report (Mongolian + English)

### 4.3 Acceptance criteria

- [ ] 50+ paying customers
- [ ] MRR ₮20–30M
- [ ] 99.5% uptime achieved
- [ ] Enterprise tier 1+ customer live
- [ ] SOC 2 Type 1 audit passed
- [ ] Average customer ROI <30 days
- [ ] Net Revenue Retention >110%

---

## 5. Технологийн дутуу бүрэлдэхүүн хэсгүүдийн map

| Sentry spec component | Current state | Phase added | Notes |
|---|---|---|---|
| **Edge agent (Docker)** | ❌ | P1 WS-4 | Replaces manual RTSP config |
| **MediaMTX + WebRTC** | ❌ MJPEG only | P2 WS-10 | Needed for <2s latency |
| **OSNet / FastReID** | ❌ | P2 WS-7 | Cross-camera tracking |
| **ByteTrack** | ✅ Бэлэн | — | Already in inference worker |
| **Qwen2.5-VL (vLLM)** | ✅ transformers runtime + RAG pipeline | P2 WS-8 | `vlm_service.py`, `rag_vlm_pipeline.py`, `Dockerfile.gpu`. vLLM 4-bit quant — GPU deploy ops. |
| **Qdrant** | ❌ Replaced by pgvector | — | RAG corpus moved into Postgres via pgvector (migration `20260427_02`). One service instead of two. Re-ID still maps to a separate vector store when WS-7 ships. |
| **pgvector** | ✅ rag_corpus.embedding column wired | P2 WS-8 | `intfloat/multilingual-e5-small` (384-dim) + HNSW cosine index. Lives in the same Postgres as the rest of app data. |
| **MinIO** | ⚠️ S3/Cloudinary | P2 WS-11 | Migrate clip storage to MinIO |
| **PostgreSQL + TimescaleDB** | ✅ Optional hypertable | — | Opt-in flag |
| **Redis Streams** | ⚠️ Redis container байгаа, Streams pattern байхгүй | P1 WS-1 | Tenant state + rate limit bucket |
| **QPay / Stripe** | ❌ | P1 WS-3 | Checkout + webhook |
| **Telegram Bot API** | ⚠️ Notify only | P1 WS-5 | Command handler + inline buttons |
| **Twilio (SMS)** | ❌ | P1 WS-5 | RED alerts only |
| **FCM (push)** | ❌ | P1 WS-5 | ORANGE/RED alerts |
| **Resend (email)** | ⚠️ SMTP контакт email байгаа | P1 WS-2 | Transactional email, templates |
| **Clerk / Auth.js (2FA)** | ⚠️ JWT custom | P2 WS-11 | OAuth2 + 2FA roll-in |
| **PostHog** | ❌ | P1 WS-2 | Onboarding funnel |
| **Better Stack / Statuspage** | ❌ | P1 WS-6 | Public status page |

---

## 6. Зардалын Өсөлт (MRR/Gross Margin)

| Phase | Customers | MRR target | GPU cost | Gross margin |
|---|---|---|---|---|
| P1 (pilot) | 1 | ₮0 (free pilot) | ₮0 (dev GPU) | N/A |
| P2 end | 10 | ₮3–5M | ~₮400K (shared 1 RTX 5090) | ~55% |
| P3 end | 50+ | ₮20–30M | ~₮3–5M (5 RTX 5090 pool) | ~65% |

---

## 7. Execution order (ерөнхий)

Дараах дараалалтай 12 долоо хоног MVP явуулна:

```
W1-W2  → [WS-1] Tenant UUID + API key schema
W2-W3  → [WS-2] Signup + OTP + plan picker
W4-W5  → [WS-3] QPay/Stripe checkout + invoice PDF
W5-W6  → [WS-2] 14-day trial activation
W6-W7  → [WS-4] Docker agent Dockerfile + config embed
W7-W8  → [WS-4] ONVIF discovery + camera test API
W8-W9  → [WS-5] 4-level scoring + Telegram bot commands
W9-W10 → [WS-5] Inline buttons + FCM + SMS
W10    → [WS-6] Status page + onboarding funnel
W11    → Pilot onboarding rehearsal (end-to-end дамжуулж туршилт)
W12    → Pilot go-live + hotfix capacity
```

---

## 8. Cross-cutting concerns

### 8.1 Security
- Бүх API endpoint `get_current_tenant` dependency-тэй
- SQL query линтер: `tenant_id` WHERE condition байгаа эсэхийг шалгах (T02-26-ийн pattern)
- Weekly pen test scenario: IDOR, API key brute force, SQL injection
- Secret rotation policy: API key 90 хоногт нэг удаа

### 8.2 Data retention
- Event clip max 90 хоног (Privacy Law)
- Person state Redis-д 30 мин expire
- Cancelled tenant: 90-day grace → full data wipe
- Audit log: 1 жил (TimescaleDB retention policy)

### 8.3 Migration playbook
- `tenant_id` UUID-ийг `organization_id` integer-тэй parallel-ээр нэмэх (backward-compat view)
- 2-sprint dual-write window
- `organization_id` deprecation → `tenant_id` primary
- Сонгосон хүснэгтэнд PostgreSQL RLS идэвхжүүлэх (feature-flag нь T02-25-д бичигдсэн)

### 8.4 Monitoring & alerting
- Prometheus rule: per-tenant GPU usage >80% → warn
- Prometheus rule: tenant API call rate >quota → throttle
- Loki query: cross-tenant query attempt → critical alert
- Alert fatigue гаргахгүй: SRE-ийн burn-rate SLO ашиглана

---

## 9. Related documents

- `01_Sentry_PRD_v1.1.md` — Product requirements (FR, NFR, UC)
- `02_Sentry_Architecture_v3.0.html` — System architecture diagram
- `03_Sentry_Pricing_Business_Model.md` — Pricing, ARPU, unit economics
- `04_Sentry_Onboarding_Flow.md` — 15-minute setup flow UX
- `05_Sentry_Multi_Tenancy_Architecture.md` — Tenant isolation, quotas, billing data
- `07_Sentry_Tasks.md` — Detailed task list with IDs, priorities, DoD

---

**Note:** Энэ roadmap нь pilot харилцагчийн feedback, QPay integration-ы бодит timeline, GPU capacity availability-ээс хамаарч сар бүр шинэчлэгдэнэ.
