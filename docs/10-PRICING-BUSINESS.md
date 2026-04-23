# 10 — Pricing & Business Strategy (Internal)

> **Note (2026-04-21):** Hardware-free centralized SaaS model-д
> шинэчлэгдсэн. Default SKU нь pure SaaS (setup fee минимум, monthly
> recurring). Edge-box hardware sale нь on-prem SKU-д ("Chipmo Server"
> branding) retained. See
> [`decisions/2026-04-21-centralized-saas-no-customer-hardware.md`](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md).

**Анхааруулга:** Энэ документ нь дотоод хэрэглээнд зориулагдсан. Public
шэар хийх бус. Pricing өөрчлөгдөх бүрт update хийнэ.

---

## 1. Business model

**Type:** B2B SaaS (default) + On-prem SKU (optional, premium tier)

**Default product — Centralized SaaS:**
- VPN appliance (~$40-60 hardware cost, customer keeps)
- Monthly recurring subscription per camera
- Zero-CAPEX onboarding for customer
- Chipmo scales infrastructure across all customers

**Optional product — On-prem ("Chipmo Server"):**
- Customer-owned server ($800-1500 hardware pass-through + margin)
- Monthly subscription (reduced)
- For customers who require data to stay on-premises
- See [`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`](./decisions/2026-04-21-drop-edge-box-hybrid-architecture.md)

### 1.1 Revenue streams (SaaS default)

1. **Onboarding fee** (one-time, minimal) — VPN appliance $80-150 margin
2. **Monthly subscription** (primary recurring) — per-camera tier pricing
3. **Professional services** (project) — custom integration, training
4. **Expansion** — additional cameras / new stores
5. **Add-ons** — priority support, extended retention, fine-tuned model
6. **API access** (Phase 3+) — third-party integration fee

### 1.2 Why SaaS default (not hardware-heavy)

- **Fast sales cycle:** VPN appliance setup in 1-2 цаг, no install visit
- **Scale moat:** Multi-tenant learning (shared behavior taxonomy) only
  works if Chipmo has the data
- **LTV:** Pure SaaS compounds ARPU vs. one-time hardware sale
- **Low CAPEX customer barrier:** Retail margin бага, upfront $3000+
  hardware purchase тодорхой дарангуйлагч

---

## 2. Pricing tiers (2026 шинэчлэгдсэн)

### 2.1 Starter — Жижиг дэлгүүр

**Target:** 1-4 камертай, 1 дэлгүүр

| Зүйл | Үнэ |
|---|---|
| Onboarding fee (VPN appliance + setup) | 290,000₮ (one-time) |
| Monthly base (up to 4 камер) | 280,000₮/сар |
| Нэмэлт камер (5-аас дээш) | 50,000₮/сар |
| Гэрээний хугацаа (minimum) | 12 сар |

**Features:**
- Rule-based + RAG detection
- Telegram alerts
- Dashboard access (1 user)
- 30-хоногийн alert clip retention
- Email support (business hours)
- No recording (live inference only)

**Per-camera effective cost:** ~70,000₮/сар (4 cam).
**Target margin:** ~80% on monthly (Phase B), ~90% on monthly (Phase C).

### 2.2 Business — Дундаж дэлгүүр / жижиг chain

**Target:** 4-10 камертай, 1-3 дэлгүүр

| Зүйл | Үнэ |
|---|---|
| Onboarding fee (VPN appliance + setup + tuning) | 450,000₮ (one-time) |
| Monthly base (up to 8 камер) | 480,000₮/сар |
| Нэмэлт камер | 45,000₮/сар |
| Гэрээний хугацаа | 12 сар |

**Features:**
- Everything in Starter
- VLM verification layer
- SMS + Telegram alerts
- Dashboard (up to 5 users)
- Mobile app access
- Phone support (12 цагийн дотор хариу)
- Monthly analytics report

**Per-camera effective cost:** ~60,000₮/сар (8 cam).
**Target margin:** ~82% on monthly (Phase B), ~92% on monthly (Phase C).

### 2.3 Enterprise — Том chain

**Target:** 10+ камертай эсвэл 3+ дэлгүүртэй chain

| Зүйл | Үнэ |
|---|---|
| Onboarding fee (multi-site, VPN mesh) | 1,200,000₮ (one-time) |
| Monthly | 38,000₮/камер/сар (volume-scaled) |
| Гэрээний хугацаа | 24 сар (volume discount) |

**Features:**
- Everything in Business
- Cross-store dashboard
- Custom behavior rules (per-tenant LoRA fine-tune future)
- API access (webhook + REST)
- SLA: 99.5% uptime, 4-цагийн phone response
- Dedicated account manager
- Quarterly business review
- Priority Re-ID and VLM compute lane

**Target margin:** ~85% on monthly (Phase B), ~93% on monthly (Phase C).

### 2.4 On-prem SKU (optional, premium)

For customers with strict data sovereignty requirements:

| Зүйл | Үнэ |
|---|---|
| Chipmo Server (hardware pass-through + margin) | 3,800,000₮ - 8,500,000₮ (spec dependent) |
| Installation + tuning | 800,000₮ (one-time) |
| Monthly (software + support) | 250,000₮/сар (flat, up to 8 камер) |
| Camera overage | 30,000₮/камер/сар |
| Гэрээний хугацаа | 24 сар minimum |

**Trade-off disclosed to customer:** On-prem-д shared behavior
taxonomy feature ажиллахгүй (no central). Model improvement slower.
Upgrade pull-based. Used ONLY when privacy/compliance demands it.

### 2.5 Add-ons

| Add-on | Үнэ | Description |
|---|---|---|
| Additional store (VPN appliance included) | 290,000₮ + tier base | Шинэ store |
| 4G fallback router | 250,000₮ (one-time) | Internet dropout insurance |
| Face blur opt-out | 50,000₮/сар | Хэрэв хууль зөвшөөрнө |
| Custom behavior rule | 1,500,000₮ | One-time engineering |
| Onsite training | 500,000₮/сессийн | Харилцагчийн team-д |
| Priority support (24/7) | 200,000₮/сар | Non-enterprise-д |
| Extended clip retention (90 хоног) | 100,000₮/сар | Default 30 хоног |
| Custom fine-tuned model (LoRA) | 2,000,000₮ setup + 150,000₮/сар | Enterprise + Business VIP |

---

## 3. Unit economics (SaaS default, per infra phase)

Per-camera-per-month ops cost нь
[`04-INFRASTRUCTURE-STRATEGY.md`](./04-INFRASTRUCTURE-STRATEGY.md) §5-д
тусгагдсан phase-ээс хамаарна:

| Phase | Per-camera ops cost (Chipmo) | Per-camera pricing (Business avg 60k₮) | Gross margin per camera |
|---|---|---|---|
| A (Railway + external GPU) | ~14,000₮/cam (USD $5) | 60,000₮ | ~77% |
| B (RunPod RTX 4090) | ~7,500₮/cam (USD $2.7) | 60,000₮ | ~87% |
| C (owned RTX 5090) | ~2,500₮/cam (USD $0.9) | 60,000₮ | ~96% |

### 3.1 Per-customer Y1 (Business tier, 8 камер, Phase B)

**Revenue:**
- Onboarding fee: 450,000₮
- Monthly: 480,000₮ × 12 = 5,760,000₮
- **Total Y1: 6,210,000₮**

**Cost:**
- VPN appliance BOM + shipping: 220,000₮ (resell margin included in onboarding fee)
- Setup labor (remote + 1h phone): 100,000₮
- Ops (Phase B, 8 камер × 7,500₮ × 12): 720,000₮
- Customer success (5% engineer time): 240,000₮
- **Total Y1: 1,280,000₮**

**Y1 Gross profit:** 6,210,000 - 1,280,000 = **4,930,000₮**
Gross margin Y1: **79.4%**

### 3.2 Per-customer Y2+ (no onboarding)

- Revenue: 5,760,000₮
- Cost (Phase B): 720,000 + 240,000 = 960,000₮
- Gross profit: **4,800,000₮**
- Gross margin Y2+: **83.3%**

**Phase C-руу шилжсэн үед:**
- Ops: 240,000₮ (vs. 720,000₮)
- Gross profit: **5,280,000₮ / year**
- Gross margin: **91.7%**

### 3.3 LTV + CAC (SaaS model)

**LTV (5 year estimate, Phase B → C transition at year 2):**
- Y1: 4.93M₮
- Y2-5 (Phase C): 5.28M × 4 = 21.12M
- **LTV = 26.05M₮**

**CAC target:** <4M₮ (LTV/CAC ratio 6.5:1+)

### 3.4 Break-even analysis (SaaS)

**Fixed monthly costs (Phase A-B, 2026 team size):**
- Founder salary: 0₮ (equity)
- 1 Engineer: 4,000,000₮/сар
- Office + misc: 500,000₮
- Marketing: 1,000,000₮
- Infra base (Phase B): 1,500,000₮
- **Total: 7,000,000₮/сар = 84,000,000₮/жил**

**Break-even (Business tier avg):**
- Per-customer Y1 gross: 4,930,000₮
- Annual margin per steady-state customer (Y2+, Phase B): 4,800,000₮
- Break-even = 84M / 4.8M = **~18 paying customers** steady-state

**Phase C transition** дээр infra base ~500,000₮/сар болох тул
break-even ~15 customers руу уруудна.

### 3.5 Revenue → MRR projection (planning)

| Month | Customers | MRR | Cumulative ARR | Phase |
|---|---|---|---|---|
| M3 | 1 | 0.48M | 5.76M | A |
| M6 | 3 | 1.44M | 17.28M | A→B |
| M12 | 12 | 5.76M | 69.12M | B |
| M18 | 30 | 14.4M | 172.8M | B |
| M24 | 60 | 28.8M | 345.6M | B→C |
| M36 | 150 | 72M | 864M | C |

Aggressive but achievable if 2026 Q2-Q3-д product-market fit баталгаажсан.

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

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) (differentiation: SaaS centralized, VPN ingress)
- [04-INFRASTRUCTURE-STRATEGY.md](./04-INFRASTRUCTURE-STRATEGY.md) (cost per camera per phase)
- [05-ONBOARDING-PLAYBOOK.md](./05-ONBOARDING-PLAYBOOK.md) (VPN appliance + camera config)
- [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md) (customer agreement, DPIA)
- [decisions/2026-04-21-centralized-saas-no-customer-hardware.md](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md)

---

Updated: 2026-04-21
