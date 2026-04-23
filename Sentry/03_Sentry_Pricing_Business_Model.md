# Sentry — Үнийн Загвар ба Бизнес Метрик
## Pricing & Business Model

**Баримтын дугаар:** DOC-03
**Хувилбар:** 1.0
**Огноо:** 2026-04-22
**Эзэмшигч:** Lil
**Холбоотой баримтууд:** `01_Sentry_PRD_v1.1.md`, `02_Sentry_Architecture_v3.0.html`

> **Брэндийн тэмдэглэл:** Internal codename = Sentry. Public landing brand одоогоор Chipmo (chipmo.mn). Rebrand хийх эсэх шийдвэрлэгдэх хүртэл хоёуланг паралель ашиглана.

---

## 1. Үнийн загвар (Pricing Structure)

### 1.1 3 бүрэлдэхүүн

Landing page-д амласан загварыг хадгална:

```
┌──────────────────────────────────────────────────┐
│  Сарын төлбөр  =  Platform fee + (Camera × Rate) │
│  Нэг удаагийн  =  Setup fee + Dispatch fee       │
└──────────────────────────────────────────────────┘
```

### 1.2 Сарын захиалга (SaaS subscription)

**Platform fee:** ₮29,000 / салбар / сар (бүх plan-д ижил)

**Камер бүрийн tier-тэй үнэ:**

| Камер тоо | Үнэ / камер / сар | Жишээ нийт |
|---|---|---|
| 1–5 камер | ₮20,000 | 5 cam = ₮129,000/сар |
| 6–20 камер | ₮17,000 | 12 cam = ₮233,000/сар |
| 21–50 камер | ₮14,000 | 30 cam = ₮449,000/сар |
| 51+ камер | ₮11,000 | 60 cam = ₮689,000/сар |

### 1.3 Нэг удаагийн төлбөр

**Setup fee:**
| Камер тоо | Sentry technician | Self-setup |
|---|---|---|
| 1–5 cam | ₮30,000 | ₮15,000 |
| 6–20 cam | ₮25,000 | ₮12,000 |
| 21+ cam | ₮20,000 | ₮10,000 |

**Dispatch fee (Sentry technician сонгосон үед):**
| Байршил | Үнэ |
|---|---|
| УБ (эхний салбар) | ₮50,000 |
| УБ нэмэлт салбар | ₮30,000 / тус бүр |
| Орон нутаг | ₮20,000 / салбар |
| Self-setup | Үнэгүй |

---

## 2. Plan Tiers (NEW — landing-аас өргөтгөсөн)

Landing page нь flat pricing бол энэ нь tier-тэй болгох санал:

### Starter — Жижиг дэлгүүр
- 1-5 камер
- 1 store
- Standard alerts (Telegram + Web)
- 7-хоног event clip retention
- Email support
- **₮129K/сар** (5 cam-аар)

### Pro — Дунд хэмжээний дэлгүүр / сүлжээ
- 6-50 камер
- 1-10 store
- All alert channels (Telegram + SMS + Push + Email)
- 30-хоног event clip retention
- Priority support (4-цагт хариу)
- Cross-camera Re-ID
- Долоо хоногийн тайлан
- **₮233K-449K/сар**

### Enterprise — Том сүлжээ
- 51+ камер
- 10+ store
- 90-хоног event clip retention
- Dedicated GPU (Phase 3)
- 24/7 phone support, SLA contract
- Custom action weights, fine-tuning
- SSO/SAML
- DPA + custom contract
- **Custom pricing** (~₮800K+/сар)

---

## 3. Free Trial

- **14 хоног**, кредит карт хэрэггүй
- Бүх Pro feature нээлттэй
- 5 камер хүртэл
- Trial дуусахад: payment add → automatic conversion, эсвэл account suspend (data 30 хоног хадгалагдана)

---

## 4. Жишээ Тооцоо (Example Calculations)

### Жишээ 1: Жижиг convenience store (CU style)
- 5 камер, УБ, Sentry technician суулгана
- Setup: ₮30,000 + Dispatch ₮50,000 = **₮80,000 нэг удаа**
- Сар: ₮29,000 + (5 × ₮20,000) = **₮129,000/сар**
- **Эхний сар нийт: ₮209,000** (~$60)
- **Жилийн нийт: ₮1,628,000** (~$475)

### Жишээ 2: Дунд хэмжээний супермаркет (Номин style)
- 12 камер, УБ, Sentry technician
- Setup: ₮25,000 + Dispatch ₮50,000 = **₮75,000 нэг удаа**
- Сар: ₮29,000 + (12 × ₮17,000) = **₮233,000/сар**
- **Эхний сар: ₮308,000** (~$90)
- **Жилийн нийт: ₮2,871,000** (~$840)

### Жишээ 3: 5-салбартай retail сүлжээ
- 5 store × 10 cam = 50 камер total
- Self-setup, UB
- Setup: 5 × ₮12,000 = ₮60,000 (dispatch үнэгүй)
- Сар: (5 × ₮29,000) + (50 × ₮14,000) = ₮145,000 + ₮700,000 = **₮845,000/сар**
- **Жилийн нийт: ₮10,200,000** (~$3,000)

### Жишээ 4: Том сүлжээ (Emart style)
- 20 store × 15 cam = 300 cam total
- Sentry technician
- Setup: 20 × ₮20,000 = ₮400,000
- Dispatch: ₮50K (1st UB) + 19 × ₮30K = ₮620,000
- Сар: (20 × ₮29,000) + (300 × ₮11,000) = ₮580,000 + ₮3,300,000 = **₮3,880,000/сар**
- **Жилийн нийт: ₮47.6 сая** (~$14,000)

---

## 5. Unit Economics

### 5.1 ARPU (Average Revenue Per User)
- **Starter:** ₮129K/сар (~$38)
- **Pro:** ₮283K/сар дунджаар (~$83)
- **Enterprise:** ₮1.5М+/сар (~$440)
- **Blended ARPU target Phase 2:** ~₮350K/сар (~$100)

### 5.2 Зардлын бүтэц (Cost per customer)
| Item | Starter | Pro | Enterprise |
|---|---|---|---|
| GPU compute (1/8 of RTX 5090) | ₮40K | ₮40K | ₮200K (dedicated) |
| Bandwidth (S3, ingress) | ₮15K | ₮25K | ₮80K |
| Storage (event clips) | ₮5K | ₮20K | ₮100K |
| Telegram/SMS API | ₮3K | ₮8K | ₮30K |
| Support cost | ₮5K | ₮20K | ₮100K |
| **Total cost** | **₮68K** | **₮113K** | **₮510K** |
| **Gross margin** | 47% | 60% | 66% |

### 5.3 LTV/CAC Target
- **CAC (Customer Acquisition Cost):**
  - Self-service (organic/SEO): ₮100-300K
  - Sales-assisted (Pro/Enterprise): ₮500K-1.5M
- **LTV target:** 24 сар × Pro ARPU = ₮6.8M (~$2,000)
- **LTV/CAC ratio:** 5-10x (healthy SaaS)

---

## 6. Бизнес Метрик (KPI)

### Phase 1 (3 сар) — Pilot
| Metric | Target |
|---|---|
| Pilot customer | 1 |
| Camera installed | 8-12 |
| Daily active users | >2 |
| Critical bug count | 0 |
| Customer NPS | 8+ |

### Phase 2 (6 сар) — Growth
| Metric | Target |
|---|---|
| Paying customers | 10 |
| MRR (Monthly Recurring Revenue) | ₮3-5M (~$900-1,500) |
| Average ARPU | ₮300-500K |
| Trial-to-paid conversion | 20%+ |
| Monthly churn | <5% |
| Support tickets / customer / month | <2 |

### Phase 3 (12 сар) — Scale
| Metric | Target |
|---|---|
| Paying customers | 50+ |
| MRR | ₮20-30M (~$6,000-9,000) |
| Trial-to-paid conversion | 30%+ |
| Monthly churn | <3% |
| Average customer ROI | <30 days |
| Net Revenue Retention | >110% |

---

## 7. Зорилтот Сегмент (Customer Segmentation)

### Сегмент 1: SMB Convenience Stores ⭐ PRIMARY
- **Жишээ:** CU, Circle K, GS25, бие даасан жижиг дэлгүүр
- **Хэмжээ:** 1 store, 3-8 camera
- **Plan:** Starter
- **Acquisition:** Self-service signup, Facebook/Instagram ads, referral
- **Pain point:** Шөнийн ээлж дээр хулгай, manager-ийн уйтгар

### Сегмент 2: Mid-market Supermarkets ⭐ PRIMARY
- **Жишээ:** Номин, Минии, Sansar
- **Хэмжээ:** 1-5 store, 10-20 camera/store
- **Plan:** Pro
- **Acquisition:** Outbound sales, demo, case study
- **Pain point:** Олон камер шалгах хүн дутагдалтай

### Сегмент 3: Specialty Retail (Phase 2)
- **Жишээ:** Techzone, Goyol, цахилгаан барааны дэлгүүр
- **Хэмжээ:** 1-3 store, өндөр үнэтэй бараатай
- **Plan:** Pro
- **Pain point:** Үнэтэй бараа хулгайд гардаг

### Сегмент 4: Enterprise Chains (Phase 3)
- **Жишээ:** Emart, TNT, Nomin
- **Хэмжээ:** 20+ store, 200+ cam total
- **Plan:** Enterprise (custom)
- **Acquisition:** Direct sales, RFP, executive demo
- **Pain point:** Compliance, audit trail, multi-store visibility

---

## 8. Go-To-Market Strategy

### Phase 1 (Months 1-3) — Pilot Validation
1. **1 pilot customer** — өөрийн network-ээс (хайр сэтгэлтэй харилцагч)
2. Free + handhold deployment
3. Weekly user research interview
4. Case study бэлтгэх

### Phase 2 (Months 4-9) — Product-Led Growth (PLG)
1. Landing page launch (Chipmo брэндээр)
2. SEO content: "хулгайн алдагдал", "ухаалаг камер"
3. Facebook/Instagram retargeting ads
4. Pilot case study хуваалцах
5. Referral program (ах дүү харилцагч → 1 сар үнэгүй)

### Phase 3 (Months 10-12) — Sales-Led для Enterprise
1. Top 50 retail chain prospect list
2. Outbound email + cold call
3. Executive demo + ROI calculator
4. Custom pilot program (3 сар, дараа нь annual contract)

---

## 9. Pricing Defaults — Шийдэл шаардсан

Дараах асуудлыг pilot-аас өмнө шийдэх хэрэгтэй:

| Асуулт | Зөвлөмж | Шийдэгдсэн |
|---|---|---|
| Trial 14 хоног эсвэл 30 хоног? | 14 хоног (urgency) | ☐ |
| Trial-д кредит карт авах уу? | Үгүй (friction багасгах) | ☐ |
| Annual prepay discount? | Тийм, 10% off (cash flow) | ☐ |
| First-month money-back guarantee? | Тийм, 30 хоног | ☐ |
| Free tier байх уу? (1 камер forever free) | Үгүй (Phase 1 freemium буюу) | ☐ |
| НӨАТ үнэн нэмэгдсэн үү? | Тийм (B2B) | ☐ |
| Annual contract discount? | 15% off если 12 сар prepay | ☐ |

---

## 10. Холбогдох баримтууд

- `01_Sentry_PRD_v1.1.md` — FR-13 Subscription & Billing
- `02_Sentry_Architecture_v3.0.html` — Tier 5 SaaS Platform
- `04_Sentry_Onboarding_Flow.md` — Trial → paid conversion flow
- `05_Sentry_Multi_Tenancy_Architecture.md` — Per-tenant billing data flow
