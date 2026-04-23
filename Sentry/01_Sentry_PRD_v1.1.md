# Sentry — AI Security Camera SaaS
## Бүтээгдэхүүний Шаардлагын Баримт (PRD)

**Баримтын дугаар:** DOC-01
**Хувилбар:** 1.1
**Огноо:** 2026-04-22
**Эзэмшигч:** Lil
**Статус:** Draft (pilot-ын дараа шинэчлэгдэнэ)
**Өөрчлөлт v1.0 → v1.1:** SaaS focus, Telegram channel, self-service onboarding, snapshot in alerts, ONVIF P0 болгосон, on-premise хассан, multi-tenancy + billing + customer portal нэмсэн

---

## 1. Бүтээгдэхүүний тойм

### 1.1 Зорилго
Sentry нь Монголын retail салбарын (дэлгүүр, супермаркет, хувцасны дэлгүүр) **хулгайн алдагдлыг бууруулах AI хяналтын SaaS систем**. Харилцагчийн одоо ашиглаж буй IP камеруудаас шууд stream авч, олон камер дамжуулан хүн бүрийн зан үйлийг анализ хийж, бодит цаг хугацаанд сэжигтэй хүнийг manager-т мэдэгдэнэ.

### 1.2 Бизнес загвар
**SaaS subscription** — сар бүрийн төлбөртэй self-service платформ.
- Self-service signup → онлайн төлбөр → Docker installer татах → 15 минутын дотор анхны detection
- Pricing: Platform fee + per-camera tiered (см. `03_Sentry_Pricing_Business_Model.md`)

### 1.3 Зорилтот хэрэглэгч (Persona)
| Хэрэглэгч | Хэрэгцээ | Гол метрик |
|---|---|---|
| **Эзэмшигч (Owner)** | Total алдагдлын ROI, billing | Saved $/сар, MRR |
| **Manager** | Бодит цаг хугацааны хяналт | Alert response time |
| **Худалдагч/Cashier** | Шууд UI харахгүй | N/A (manager-ээр дамжина) |
| **Нягтлан** | Сар бүрийн тайлан, нэхэмжлэх | Incident report, invoice |

### 1.4 Үнэт цэнэ (Value Proposition)
- ✅ **Hardware install хэрэггүй** — Docker agent only
- ✅ **15 минутын setup** — self-service, technician хэрэггүй
- ✅ **Existing IP камертай compatible** — RTSP/ONVIF auto-discovery
- ✅ **Cross-camera tracking** — хүн дэлгүүр дотор дамжих бүрд detect
- ✅ **Монгол хэлээр UI ба Telegram алерт** — local market fit
- ✅ **2-4 долоо хоногт ROI** — 1 хулгайч барих ≈ subscription зардлыг нөхөнө

---

## 2. Үндсэн Use Case-ууд

### UC-1: Хулгайч илрүүлэх (PRIMARY)
**Trigger:** Хүн дэлгүүрт орох
**Flow:**
1. Камер бүрт хүн detect хийнэ (YOLO11-pose)
2. Person ID үүсгэж олон камер дамжуулан track хийнэ (Re-ID, Phase 1-ээс)
3. Action бүрийг scoring моделд оруулна (VLM + rules)
4. Score >70% болоход manager dashboard-д alert + Telegram + snapshot
5. Score >85% болоход push notification + sound alert
6. Касс дэргэдүүр төлбөргүй гарвал → CRITICAL alert

**Success criteria:** 80%+ recall, <15% false positive (MVP), <10% (Phase 2)

### UC-2: Cross-Camera Tracking (Phase 1-д орсон)
**Trigger:** Хүн камераас гарч өөр камерт орох
**Flow:**
1. Person Re-ID embedding extract (OSNet, 512-dim)
2. Идэвхтэй person state-тэй cosine similarity харьцуулах
3. >0.75 → ижил хүн, action history merge
4. Person ID, action log, score persist (Redis)

**Success criteria:** 85%+ accuracy in 5-second handoff window (MVP)

### UC-3: Live Monitoring (Manager)
**Goal:** Real-time camera view in office/mobile
**Flow:**
1. Web app нээх → multi-camera grid (1/4/9/16 view)
2. Хүн бүр дээр анонимизсан Person ID + risk level overlay
3. Сэжигтэй болсон үед камер автоматаар highlight
4. Тухайн хүн дээр click → бүх камер дамжсан замналыг харах

### UC-4: Self-Service Onboarding (NEW v1.1)
**Goal:** 15 минутын дотор signup-аас first detection
**Flow:**
1. Landing page → "Үнэгүй туршиж үзэх" → email + store info
2. Email verify → plan сонгох → онлайн төлбөр (QPay/Stripe)
3. Dashboard руу нэвтрэх → Docker installer татах (.exe / .sh)
4. Installer ажиллуулах → ONVIF autodiscovery → камер list
5. "Холбох" дарах → агент сервер рүү TLS tunnel үүсгэнэ
6. Анхны хүн detect хийгдсэн үед "🎉 Setup амжилттай" мэдэгдэл

**Success criteria:** 80%+ users reach first detection within 15 минут

### UC-5: Incident Review & Feedback
**Goal:** Өнгөрсөн incident-ийг шалгах + ML model сайжруулах
**Flow:**
1. Alert queue-ээс incident сонгох
2. Action timeline + бүх camera clip харах
3. Manager: "Confirm" / "False alarm" сонгох
4. Feedback model retraining-д ашиглагдана

### UC-6: Billing & Subscription Management (NEW v1.1)
**Goal:** Customer өөрөө subscription удирдах
**Flow:**
1. Customer portal → Billing tab
2. Plan upgrade/downgrade, камер тоо нэмэх
3. Invoice татах (PDF)
4. Payment method update
5. Cancel subscription (90-хоног data export grace period)

---

## 3. Функциональ Шаардлагууд (FR)

### FR-1: Камер интеграц
| ID | Шаардлага | Приорит | Өөрчлөлт |
|---|---|---|---|
| FR-1.1 | RTSP protocol дэмжих | P0 | — |
| FR-1.2 | **ONVIF auto-discovery** | **P0** ⭐ | P1 → P0 (15-мин setup-ийн тулд) |
| FR-1.3 | H.264, H.265 codec decode | P0 | — |
| FR-1.4 | Sub-stream сонгох (bandwidth optimize) | P0 | — |
| FR-1.5 | 1-32 камер 1 харилцагч дээр | P0 | — |
| FR-1.6 | Камер offline 30сек дотор detect | P1 | — |
| FR-1.7 | RTSP URL auto-detect (common camera brands) | P0 ⭐ | NEW |

### FR-2: Хүн detect ба tracking (Single camera)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-2.1 | YOLO11-pose >95% precision | P0 |
| FR-2.2 | ByteTrack frame-frame ID | P0 |
| FR-2.3 | 17 keypoint pose | P0 |
| FR-2.4 | 1 frame-д 20 хүртэл concurrent | P0 |
| FR-2.5 | Children/staff filter (uniform-base) | P1 |

### FR-3: Cross-Camera Re-Identification ⭐ (Phase 1-д орсон)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-3.1 | OSNet/FastReID 512-dim embedding | P0 |
| FR-3.2 | 5сек window дотор камер хооронд match | P0 |
| FR-3.3 | Embedding 30 минут persist | P0 |
| FR-3.4 | Cosine similarity >0.75 threshold | P0 |
| FR-3.5 | Person ID format: `P-{store}-{date}-{seq}` | P0 |
| FR-3.6 | Bie biLeg (gait) + height fallback | P1 |

### FR-4: Зан Үйл Таних (Action Recognition)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-4.1 | VLM (Qwen2.5-VL 7B) action description | P0 |
| FR-4.2 | Заавал танигдах action: бараа авах, нуух, эргэн харах, кассаар өнгөрөх, гарах | P0 |
| FR-4.3 | Action бүрд timestamp + camera + confidence | P0 |

### FR-5: Suspicion Scoring Engine ⭐
(Хувирал v1.0-аас нэгэн адил, action weight library 12-ыг үлдээсэн)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-5.1 | Action бүрт pre-defined weight (0.0-1.0) | P0 |
| FR-5.2 | Time decay (10 минутын өмнөх × 0.5) | P0 |
| FR-5.3 | Negative actions (касст төлсөн) score буулгана | P0 |
| FR-5.4 | 4 түвшний классификаци: GREEN/YELLOW/ORANGE/RED | P0 |
| FR-5.5 | Threshold-уудыг харилцагч customize | P1 |

### FR-6: Realtime Live Overlay
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-6.1 | WebRTC <2сек latency | P0 |
| FR-6.2 | Bounding box + Person ID + Risk level | P0 |
| FR-6.3 | 4 түвшний color coding | P0 |
| FR-6.4 | Multi-camera grid (1/4/9/16 view) | P0 |
| FR-6.5 | Person follow mode (auto camera switch) | P1 |

### FR-7: Анхааруулга / Escalation (Telegram, Snapshot нэмэгдсэн)
| Score | Action | Channel |
|---|---|---|
| **GREEN (0-40%)** | Зөвхөн log | — |
| **YELLOW (40-70%)** | Dashboard notification + Telegram | Web + Telegram |
| **ORANGE (70-85%)** | Manager screen pop-up + Telegram + email | Web + sound + Telegram + email |
| **RED (85-100%)** | Push notification + SMS + Telegram + sound + auto full-screen | All channels |

| ID | Шаардлага | Приорит | Өөрчлөлт |
|---|---|---|---|
| FR-7.1 | Alert acknowledge workflow | P0 | — |
| FR-7.2 | Escalation log (хэн, хэзээ хүлээн авсан) | P0 | — |
| FR-7.3 | Manager assignment | P1 | — |
| FR-7.4 | **Telegram bot integration** (Mongolia preference) | **P0** ⭐ | NEW |
| FR-7.5 | **Snapshot attached to ALL alerts** (зурагтай) | **P0** ⭐ | NEW |
| FR-7.6 | Alert acknowledge via Telegram inline button | P1 | NEW |

### FR-8: Manager Dashboard
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-8.1 | Live multi-camera grid view | P0 |
| FR-8.2 | Active person list (одоо дэлгүүрт) | P0 |
| FR-8.3 | Alert queue (sorted by severity) | P0 |
| FR-8.4 | Today's stats (зочин, alert, баталгаажсан) | P0 |
| FR-8.5 | Quick filters (risk level) | P1 |
| FR-8.6 | Долоо хоногийн тайлан (landing-д амласан) | P0 ⭐ |

### FR-9: Incident History & Search
(v1.0-той ижил)

### FR-10: Feedback Loop (ML сайжруулах)
(v1.0-той ижил)

### FR-11: Multi-tenancy ⭐ (бэхжүүлсэн)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-11.1 | Store бүр data isolation (tenant_id-аар бүх query namespace-лагдсан) | P0 |
| FR-11.2 | Owner олон store удирдах | P0 |
| FR-11.3 | Role-based access (Owner/Manager/Viewer/Billing) | P0 |
| FR-11.4 | Per-tenant resource quota (camera count, GPU time) | P0 ⭐ NEW |
| FR-11.5 | Per-tenant API key & rotation | P0 ⭐ NEW |
| FR-11.6 | Tenant deletion → 90-хоног grace, дараа нь бүх data wipe | P0 ⭐ NEW |

### FR-12: Self-Service Onboarding (NEW)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-12.1 | Email/phone signup без кредит карт | P0 |
| FR-12.2 | Plan picker + checkout (QPay, Stripe) | P0 |
| FR-12.3 | Email verification | P0 |
| FR-12.4 | Docker installer (.exe Windows, .sh Linux/Mac) | P0 |
| FR-12.5 | Installer auto-config: tenant API key, server URL pre-filled | P0 |
| FR-12.6 | ONVIF auto-discovery wizard | P0 |
| FR-12.7 | Test camera connection button | P0 |
| FR-12.8 | First-detection celebration UI | P0 |
| FR-12.9 | Onboarding email sequence (5 ширхэг 7 хоногийн дотор) | P1 |
| FR-12.10 | "Get help" → live chat / WhatsApp | P1 |

### FR-13: Subscription & Billing (NEW)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-13.1 | QPay integration (Mongolia local) | P0 |
| FR-13.2 | Stripe integration (international card) | P0 |
| FR-13.3 | Plan tier: Starter / Pro / Enterprise | P0 |
| FR-13.4 | Per-camera tiered pricing (см. 03_Pricing) | P0 |
| FR-13.5 | Setup fee (one-time) | P0 |
| FR-13.6 | НӨАТ-тай invoice generation (PDF) | P0 |
| FR-13.7 | Failed payment retry (3 udaa, 7 хоногтой) | P0 |
| FR-13.8 | Plan upgrade/downgrade self-service | P0 |
| FR-13.9 | Camera count auto-adjust billing | P0 |
| FR-13.10 | Cancellation flow + 90-хоног data export | P0 |
| FR-13.11 | Trial period (14 хоног free) | P0 |

### FR-14: Customer Portal (NEW)
| ID | Шаардлага | Приорит |
|---|---|---|
| FR-14.1 | Account settings (имэйл, нууц үг, 2FA) | P0 |
| FR-14.2 | Team member invite (role-based) | P0 |
| FR-14.3 | Billing history & invoice download | P0 |
| FR-14.4 | Payment method update | P0 |
| FR-14.5 | Usage stats (камер тоо, alert тоо, GPU time) | P0 |
| FR-14.6 | Subscription management UI | P0 |
| FR-14.7 | API key management | P1 |
| FR-14.8 | Audit log viewer (security) | P1 |

---

## 4. Non-Functional Шаардлагууд (NFR)

### NFR-1: Performance
| Metric | Target |
|---|---|
| Detection latency (frame → score) | <500 ms |
| Live stream latency (camera → web) | <2 sec |
| Alert latency (event → notification) | <3 sec |
| Re-ID matching | <100 ms |
| Web dashboard load | <2 sec |
| Onboarding signup → first detection | **<15 минут** ⭐ |
| Telegram alert delivery | <2 sec |

### NFR-2: Capacity
- **1 RTX 5090 → 6-8 харилцагч** (12 камертай дунджаар, Re-ID + VLM ажиллахад)
- **1 харилцагч → 32 камер max**
- **Concurrent active person tracking:** 100/store
- **Concurrent tenants per server:** 8 (resource quota enforcement)

### NFR-3: Bandwidth
- Customer upload: <10 Mbps дунджаар
- Sub-stream + motion filter: ~1 ТБ/сар/харилцагч
- Live view: WebRTC peer-to-peer (server bypass)

### NFR-4: Reliability
- Uptime: **99.5% SLA** (sar бүрийн SLA баталгаа)
- Camera offline detect: <30 sec
- Auto-reconnect on network failure
- Local agent buffer: 5 минут (network drop үед)
- Status page (status.sentry.mn) public

### NFR-5: Security
- TLS 1.3 бүх connection
- **Per-tenant API key, монтхли rotation сонголт** ⭐
- AES-256 at-rest encryption (event clip)
- Authentication: OAuth2 + 2FA (manager+)
- Audit log: бүх admin action
- SOC 2 Type 1 readiness (Phase 3)

### NFR-6: Privacy ⚠️ ХАМГИЙН ЧУХАЛ
- Видео clip: зөвхөн event-related (max 90 хоног)
- **Биометрийн өгөгдөл хадгалахгүй** — embedding нь cosine vector only, нүүр биш
- 30 минутын дараа person state expire
- Mongolian privacy law нийцэх
- Customer request → all data delete (right to be forgotten, 30 хоногийн дотор)
- DPA template бэлэн (Enterprise tier)

### NFR-7: Scalability
| Phase | Customers | Infrastructure |
|---|---|---|
| 1 (MVP) | 1-10 | 1 GPU |
| 2 | 10-50 | 5-7 GPU + horizontal scale |
| 3 | 50+ | Sharded DB, multi-region (Korea fallback) |

### NFR-8: Localization
- UI Монгол хэл бүрэн (default)
- Алерт мессеж Монгол хэл (Telegram, SMS)
- Огноо/цаг Mongolian format
- Орос/Англи toggle (Phase 2)

### NFR-9: Deployment Model (NEW)
- **Cloud-only SaaS** — on-premise option хассан
- Multi-tenant shared GPU pool (Standard plan)
- Phase 3-т dedicated tenant option (Enterprise plan)

---

## 5. UI/UX Шаардлагууд

### UI-1: Live Monitor Page
- Multi-camera grid (1/4/9/16)
- Камер бүрд: name, time, status indicator
- Person bounding box: 4 түвшний цвет
- Auto-highlight on high risk

### UI-2: Person Detail View
- Бүх камер дамжсан timeline
- Action history chronologically
- Score evolution (line chart)
- "Confirm" / "False alarm" button

### UI-3: Alert Dashboard
- Active alerts queue (severity + time sorted)
- Quick actions: Acknowledge / Escalate / Dismiss
- 1-click camera switch

### UI-4: ⚠️ Хууль зүйн UI Guidelines (CRITICAL)
**❌ Хориглох:** "Хулгайч", "Гэмт хэрэгтэн", customer-д харагдах score
**✅ Зөвшөөрөх:** "Анхаарах хэрэгтэй", "Шалгах шаардлагатай", staff-only screens
**Disclaimer footer заавал:** *"Энэ систем нь анхаарал татах зорилготой бөгөөд буруутгал биш"*

### UI-5: Onboarding Wizard (NEW)
- 5-step progress: Plan → Pay → Install → Connect cameras → Test
- Inline help, video tutorials embedded
- "Stuck?" → live chat button always visible

### UI-6: Customer Portal (NEW)
- Sidebar nav: Dashboard / Cameras / Alerts / Team / Billing / Settings
- Mobile-responsive

### UI-7: Telegram Bot UX (NEW)
- Bot commands: `/start`, `/status`, `/today`, `/alerts`, `/help`
- Alert format: photo + text + inline buttons (Acknowledge / View / Dismiss)
- Multiple manager subscribe to same store

---

## 6. Системийн Constraint

### C-1: Customer side hardware
- ❌ Шинэ hardware install **хориотой**
- ✅ Existing PC дээр Docker container (4 CPU, 8GB RAM, 50GB)
- ✅ Existing IP камер ашиглах

### C-2: Network
- Upload bandwidth minimum 10 Mbps
- **Outbound only** (NAT/firewall friendly)
- 5 минут local buffer

### C-3: Хууль зүй
- Хувийн нууцлалын тухай хууль
- Хадгалалт max 90 хоног
- Биометрийн нэрсийн (face→name) бүртгэл хориглол
- ToS, Privacy Policy, DPA template бэлэн

### C-4: Cloud-only (NEW)
- On-premise deployment устгасан — managed cloud SaaS only
- Энэ нь support, infra, security simplification

---

## 7. Out of Scope (Phase 1-д БАЙХГҮЙ)

- ❌ Нүүрээр танилт + name lookup (биометрийн хууль)
- ❌ "Blacklist" — өмнөх хулгайч хадгалах
- ❌ Cashier theft monitoring (employee хяналт — separate product)
- ❌ Inventory tracking
- ❌ Customer demographics (нас, хүйс)
- ❌ Heatmap, customer flow analytics → Phase 2
- ❌ On-premise deployment (хассан)
- ❌ SSO/SAML → Phase 3 (Enterprise tier)

---

## 8. Acceptance Criteria

### Phase 1 — MVP (3 сар)
- [ ] 1 pilot customer production deploy
- [ ] 8-12 камер simultaneously
- [ ] **Cross-camera Re-ID >85% accuracy** ⭐
- [ ] Live stream latency <3 sec
- [ ] False positive rate <15%
- [ ] **Self-service signup → first detection <15 минут** ⭐
- [ ] **Telegram bot live** ⭐
- [ ] Manager dashboard daily active
- [ ] QPay payment processing live
- [ ] 14-day free trial mechanism live

### Phase 2 — Growth (6 сар)
- [ ] 10 paying customers
- [ ] False positive rate <10%
- [ ] Mobile app (iOS, Android)
- [ ] Multi-store owner view
- [ ] Feedback loop training pipeline
- [ ] **MRR ₮3-5 сая** (~10 customer × ₮300-500K)
- [ ] **Churn <5%/month**

### Phase 3 — Scale (12 сар)
- [ ] 50+ customers
- [ ] 99.5% uptime achieved
- [ ] Average customer ROI <30 days
- [ ] Enterprise tier launch (dedicated GPU)
- [ ] **MRR ₮20-30 сая**

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| False positive нь staff-customer conflict үүсгэх | High | High | UI guidelines, manager-only alert, no public display |
| Re-ID accuracy зимний хувцастай үед | High | Medium | Gait + height + temporal context, Mongolian dataset training |
| Хууль зүйн challenge (privacy law) | Medium | High | Хуульчтай эрт зөвлөлдөх, GDPR-style compliance |
| GPU capacity insufficient at scale | Medium | High | Horizontal scaling, 4-bit quantization |
| Customer internet drop | Medium | Medium | Local buffer, graceful degradation |
| Pilot customer drop out | Low | High | 30-day money-back, hands-on onboarding |
| **Self-setup wizard нь 15 минутад багтахгүй** ⭐ | Medium | High | Onboarding analytics, drop-off измерение, inline help |
| **QPay integration delay** ⭐ | Medium | Medium | Stripe fallback ready |
| **Tenant data leak (multi-tenancy bug)** ⭐ | Low | Critical | Strict tenant_id filtering, audit, security review |

---

## 10. Тех Stack Summary (Updated)

| Layer | Technology | Өөрчлөлт |
|---|---|---|
| Edge agent | Python + OpenCV + Docker | — |
| Streaming | RTSP → MediaMTX → WebRTC | — |
| Detection | YOLO11-pose (Ultralytics) | — |
| Re-ID | OSNet / FastReID | — |
| Tracking | ByteTrack | — |
| VLM | Qwen2.5-VL 7B (4-bit quantized) | — |
| Person state | Redis | — |
| Vector DB | Qdrant (embeddings) | — |
| Event DB | PostgreSQL | — |
| Object storage | MinIO (event clips) | — |
| Backend API | FastAPI | — |
| Frontend | Next.js + Tailwind | — |
| Mobile | React Native (Phase 2) | — |
| Infrastructure | Self-hosted (RTX 5090) | — |
| **Notifications** | **Telegram Bot API + Twilio (SMS) + FCM (push)** | NEW ⭐ |
| **Billing** | **QPay (Mongolia) + Stripe (intl)** | NEW ⭐ |
| **Auth** | **Clerk / Auth.js (OAuth2 + 2FA)** | NEW ⭐ |
| **Email** | **Resend (transactional)** | NEW ⭐ |
| **Status page** | **Better Stack / Statuspage.io** | NEW ⭐ |
| **Analytics** | **PostHog (product analytics, onboarding funnel)** | NEW ⭐ |

---

## 11. Холбогдох баримтууд

- `02_Sentry_Architecture_v3.0.html` — Системийн архитектурын диаграм (SaaS layer нэмэгдсэн)
- `03_Sentry_Pricing_Business_Model.md` — Үнийн загвар, бизнес метрик
- `04_Sentry_Onboarding_Flow.md` — 15-мин setup UX flow
- `05_Sentry_Multi_Tenancy_Architecture.md` — Tenant isolation, billing data flow

---

**Энэ document нь pilot харилцагчтай хамтран шинэчлэгдэх живой draft.**
