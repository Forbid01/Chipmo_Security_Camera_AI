# 10 — Pricing & Business Strategy (Internal)

**Анхааруулга:** Энэ документ нь дотоод хэрэглээнд зориулагдсан. Public
шэар хийх бус. Pricing өөрчлөгдөх бүрт update хийнэ.

---

## 1. Business model

**Type:** B2B SaaS + Hardware (hybrid)

**Revenue streams:**
1. **Setup / Hardware fee** (one-time) — edge box худалдах
2. **Monthly subscription** (recurring) — камер тоон дахь tier-ээр
3. **Professional services** (project) — custom integration, onsite training
4. **Expansion** — нэмэлт камер / шинэ store
5. **API access** (future) — third-party integration

**Why hybrid (not pure SaaS):**
- Hardware margin cost-ийг эргүүлэн нөхөж margin сайжруулна
- Харилцагч өөр хаана ч явахгүй (edge box нь Chipmo стакд lock хийгдсэн)
- Upfront cash эхний 6 сарын ops-г нөхнө

---

## 2. Pricing tiers (2026 шинэчлэгдсэн)

### 2.1 Starter — Жижиг дэлгүүр

**Target:** 1-4 камертай, 1 дэлгүүр

| Зүйл | Үнэ |
|---|---|
| Setup + Edge Box (compact) | 2,900,000₮ |
| Monthly (4 камер багтана) | 350,000₮/сар |
| Нэмэлт камер (5-аас дээш) | 60,000₮/сар |
| Гэрээний хугацаа (minimum) | 12 сар |

**Features:**
- Rule-based + RAG detection
- Telegram alerts
- Dashboard access (1 user)
- 30-хоногийн clip retention
- Email support (business hours)

**Target margin:** 40% on hardware, 65% on monthly

### 2.2 Business — Дундаж дэлгүүр / жижиг chain

**Target:** 4-10 камертай, 1-3 дэлгүүр

| Зүйл | Үнэ |
|---|---|
| Setup + Edge Box (standard) | 4,500,000₮ |
| Monthly (8 камер багтана) | 600,000₮/сар |
| Нэмэлт камер | 55,000₮/сар |
| Гэрээний хугацаа | 12 сар |

**Features:**
- Everything in Starter
- VLM verification layer
- SMS + Telegram alerts
- Dashboard (up to 5 users)
- Mobile app access
- Phone support (12 цагийн дотор хариу)
- Monthly analytics report

**Target margin:** 45% on hardware, 70% on monthly

### 2.3 Enterprise — Том chain

**Target:** 10+ камертай эсвэл 3+ дэлгүүртэй chain

| Зүйл | Үнэ |
|---|---|
| Setup + Edge Box (high-end) | 7,500,000₮ |
| Monthly | 45,000₮/камер/сар |
| Гэрээний хугацаа | 24 сар (volume discount) |

**Features:**
- Everything in Business
- Cross-store dashboard
- Custom behavior rules
- API access (webhook + REST)
- SLA: 99.5% uptime, 4-цагийн phone response
- Dedicated account manager
- Quarterly business review
- On-site annual maintenance

**Target margin:** 50% on hardware, 75% on monthly

### 2.4 Add-ons

| Add-on | Үнэ | Description |
|---|---|---|
| Additional edge box | 2,900,000₮-7,500,000₮ | Шинэ store |
| Face blur opt-out | 50,000₮/сар | Хэрэв хууль зөвшөөрнө |
| Custom behavior rule | 1,500,000₮ | One-time development |
| Onsite training | 500,000₮/сессийн | Харилцагчийн team-д |
| Priority support (24/7) | 200,000₮/сар | Non-enterprise-д |
| Extended clip retention (90 хоног) | 100,000₮/сар | Default 30 хоног |

---

## 3. Unit economics

### 3.1 Per-customer (Business tier, 8 камер)

**Эхний жилийн revenue:**
- Setup: 4,500,000₮
- Monthly: 600,000₮ × 12 = 7,200,000₮
- **Total Y1: 11,700,000₮**

**Эхний жилийн cost:**
- Hardware BOM: 3,450,000₮
- Install labor (4 цаг × 2 хүн): 160,000₮
- Хүргэлт: 50,000₮
- **Total one-time: 3,660,000₮**
- Ops (per month):
  - Central GPU (25% of RTX 5090 = 1/4 share): 40,000₮
  - Server / hosting: 25,000₮
  - Support (10% of 1 engineer): 200,000₮
  - **Monthly: 265,000₮/сар = 3,180,000₮ жил**

**Y1 Gross profit:**
- 11,700,000 - 3,660,000 - 3,180,000 = **4,860,000₮**
- Gross margin Y1: 41.5%

**Y2+ (no setup):**
- Revenue: 7,200,000₮
- Cost: 3,180,000₮ + hardware amortization (1,150,000₮/жил × 3 жил)
- Gross profit: **2,870,000₮**
- Gross margin Y2+: 39.9%

**LTV (5 жил):** 4.86 + 2.87 × 4 = **16.34M₮**

**CAC target:** < 3M₮ (LTV/CAC ratio 5:1+)

### 3.2 Break-even analysis

**Fixed monthly costs (assumed):**
- 1 Founder salary: 0₮ (equity)
- 1 Engineer: 4,000,000₮/сар
- Office + misc: 500,000₮
- Marketing: 1,000,000₮
- **Total: 5,500,000₮/сар = 66,000,000₮/жил**

**Break-even харилцагчийн тоо (Business tier):**
- Жилийн per-customer gross: 4,860,000₮
- **66M / 4.86M = 14 харилцагч** (эхний жилдээ)

**Mk:** 14 paying харилцагчид хүрсний дараа profitable.

---

## 4. Customer segmentation

### 4.1 Ideal customer profile (ICP)

**Priority 1: Medium supermarket chains**
- 3-10 branch
- 20-100 ажилтан
- Хулгайлалтаар мэдэгдэхүйц loss-тай (жилд 20M₮+)
- IT-тэй ажилладаг хүн байна
- Decision maker: operations director / owner

**Жишээ:** Regional supermarket, gas station chain, pharmacy chain

**Priority 2: Gas stations**
- Өндөр хулгайлалт risk
- 24/7 ажилладаг (night mode чухал)
- Олон branch
- Standard format (camera installation хялбар)

**Priority 3: Electronics / jewelry stores**
- Өндөр value inventory
- Fewer stores but higher-stakes
- Willing to pay premium

**Priority 4: Independent grocery**
- Volume play
- Lower margin per customer
- Requires self-serve onboarding

### 4.2 NOT ideal

- Одоогоор IT infrastructure огт байхгүй (install time ↑)
- < 4 камертай микро shop (ROI тодорхойгүй)
- Харилцагч дотоодын dispute-тэй (video ашиглалт complicated)
- Hardware ашиглах цахилгаан тогтворгүй газар

---

## 5. Sales playbook

### 5.1 Lead generation

**Channel 1: Outbound sales (primary)**
- LinkedIn + email outreach to retail chain ops directors
- Industry conference (Retail Mongolia, etc.)
- Cold calling (Mongol retail нь relationship-based)

**Channel 2: Referrals**
- Existing customer referral program: 1 сарын discount per successful referral
- Partner с security integrators

**Channel 3: Content (SEO + social)**
- Блог: "Retail-д хулгайлалт яаж багасгах вэ?"
- YouTube: demo videos
- Facebook Ads (Монгол retail owner-ууд)

**Channel 4: Partnership**
- Insurance companies (discount policy-д intergrated)
- POS provider-тэй bundle

### 5.2 Sales funnel stages

```
Lead (cold) → Qualified → Demo → Pilot → Negotiation → Closed Won
  100%         40%         25%      15%      10%           7%
```

**Target:**
- 100 leads / сар
- 7 closed / сар (Business tier average)
- Revenue / сар: 7 × 4.5M (setup) + 7 × 600k (monthly) = ~35.7M + recurring

### 5.3 Sales cycle

**Starter:** 2-4 долоо хоног
**Business:** 4-8 долоо хоног
**Enterprise:** 2-6 сар

### 5.4 Objection handling

| Гол эргэлзээ | Хариулт |
|---|---|
| "Үнэтэй" | ROI тооцоо: average store 2M₮/сар хулгайлалт, систем 1 сарын дотор мөнгөө буцаана |
| "Ажилтнууд эсэргүүцнэ" | Audit log, privacy guarantee, AI нь staff-ын productivity хэмжихгүй |
| "Одоогийн камер таараа" | RTSP дэмжвэл тааруулана, 95% таараа |
| "Интернет тасрах" | Edge-first архитектур, offline-д ажиллана |
| "Хувийн нууцлал" | Video never leaves store, GDPR-ready, Mongol хуульд нийцтэй |
| "Бидний адилхан гэж өөр company захиалсан" | Демо, pilot 2 долоо хоног (бидэнд итгэлтэй) |

### 5.5 Pilot program

**Zero-risk pilot:**
- 2 долоо хоног
- 1 store, 4 камер
- Setup fee 50% discount
- Харилцагч сэтгэл ханамжгүй бол full refund + hardware буцаана
- Pilot-ын дараа standard contract

**Pilot success criteria (харилцагчаас):**
- Target false positive rate < 15%
- Target detected theft events > 2 (2 долоо хоногт)
- Target alert response time < 2 мин (Telegram-аас Security-д)

---

## 6. Competitive positioning

### 6.1 Competitors

**Global:**
- **Veesion** (France) — $100-200/камер/сар, cloud-based, English only
- **Everseen** (Ireland) — Enterprise, хуучин bulkless
- **Trigo** — POS-integrated, expensive

**Mongol:**
- **Hikvision / Dahua** + хувь хүний custom integration — хямд ч standalone
- ** local CCTV integrator** — hardware гол, AI biz model сул

### 6.2 Positioning

**Chipmo нь:**
- Хямд: Veesion-ийн 1/3 үнэ
- Мongol-ийн зах зээлд адаптагдсан (хэл, support)
- Self-hosted (privacy)
- Edge-first (internet outage-д резилиент)
- Self-improving (тохиолдол нэмэгдэх тусам сайжирна)

**Tagline:** "Таны дэлгүүрийн AI нүд — Монголд бүтээсэн, таны серверт
ажиллана."

---

## 7. Growth plan

### 7.1 Year 1 targets

| Quarter | Customer count | MRR | Cumulative Revenue |
|---|---|---|---|
| Q1 | 3 | 1.8M | 15M (setup + first MRR) |
| Q2 | 8 | 4.8M | 45M |
| Q3 | 14 | 8.4M | 85M |
| Q4 | 22 | 13.2M | 140M |

**Y1 ARR exit:** ~160M₮
**Y1 total revenue:** ~140M₮

### 7.2 Year 2 targets

- 50-70 customers
- ARR: 400-500M₮
- Team: 3-4 engineers + 2 sales/support
- Federated learning moat established

### 7.3 Year 3 targets

- 150-200 customers
- ARR: 1.2-1.5B₮
- Expand: Уул уурхай, логистик, бусад retail vertical
- International pilot (Казакстан, Киргиз)

---

## 8. Funding plan (if needed)

### 8.1 Bootstrap (preferred)

- Эхний 14 харилцагчийг (break-even) revenue-ээр санхүүжүүлнэ
- Minimal external funding
- Founder-дэнд 100% equity хадгалагдана

### 8.2 Seed round (if needed)

**Ask:** $200k-400k (700M-1.4B₮)
**Purpose:**
- Edge box bulk inventory (50+ units)
- Sales team build (2 sales reps)
- Marketing / brand
- 18 months runway

**Investor profile:**
- Retail/tech interesting
- Mongol-CEE regional angle
- Better strategic (retail operator) than pure financial

### 8.3 Series A (Y3)

**Ask:** $2-5M
**Purpose:** International expansion
**Profile:** Asia retail-tech funds

---

## 9. KPI dashboard

Founder-д харуулах гол KPI (weekly):

| KPI | Target | Current |
|---|---|---|
| Active customers | TBD | TBD |
| MRR | TBD | TBD |
| Churn rate (monthly) | < 2% | TBD |
| NPS | > 40 | TBD |
| CAC | < 3M₮ | TBD |
| LTV | > 15M₮ | TBD |
| Sales cycle (average) | < 6 долоо хоног | TBD |
| Pilot-to-paid rate | > 60% | TBD |
| False positive rate (system-wide) | < 10% | TBD |
| Edge uptime (system-wide) | > 99.5% | TBD |

---

## 10. Monthly review rituals

### Sales & Marketing (weekly)

- Pipeline review (Friday)
- Demo outcome tracking
- Lead source attribution

### Operations (weekly)

- All customer health check
- Edge box fleet status
- Support ticket backlog

### Strategy (monthly)

- KPI dashboard review
- Pricing experiment results
- Competitor watchlist

### Board / advisor (quarterly)

- P&L
- Product roadmap review
- Funding status

---

## 11. Exit / scenarios

### 11.1 Strategic acquirer profile

Потенциал exit acquirer-ууд (5+ жилийн дараа):

- Hikvision / Dahua (video + AI bundle)
- Retail POS provider (Solar POS, Unimart tech arm)
- Regional security chain
- Global AI security (Verkada, Ambient.ai)

### 11.2 IPO path (10+ жил)

- Зарим дэлгэрэнгүй benchmark: Verkada ($3B valuation)
- Монголд IPO нь realistic бус, харин UK/US path боломжтой

### 11.3 Lifestyle / profitable SMB

- 50-100 customers, $2-3M ARR
- Profitable, owner-operator model
- No exit, long-term cash flow

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) (differentiation: edge-first, self-hosted)
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md) (hardware BOM)
- [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md) (customer agreement)

---

Updated: 2026-04-17
