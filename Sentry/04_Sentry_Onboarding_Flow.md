# Sentry — Self-Service Onboarding Flow
## 15-Minute Setup UX Specification

**Баримтын дугаар:** DOC-04
**Хувилбар:** 1.0
**Огноо:** 2026-04-22
**Эзэмшигч:** Lil
**Холбоотой:** `01_Sentry_PRD_v1.1.md` (FR-12), `03_Sentry_Pricing_Business_Model.md`

---

## 1. Зорилго

Хэрэглэгч landing page-ээс **15 минутын дотор анхны хулгайч detection-д** хүрэх.

**Success metric:** 80%+ users complete signup → first detection ≤15 минут.

---

## 2. Бүрэн Onboarding Flow (5-Step)

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 1. Sign  │ → │ 2. Plan  │ → │ 3. Pay   │ → │ 4. Inst  │ → │ 5. Test  │
│   up     │   │  pick    │   │  +verify │   │  Docker  │   │ camera   │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
   2 мин         1 мин          2 мин          5 мин          5 мин
                                                              ━━━━━━━━━
                                                              Total: ~15 мин
```

---

## 3. Step 1 — Signup (Target: 2 минут)

### URL: `/signup`

**UI:**
```
┌────────────────────────────────────┐
│  🛡️ Sentry                          │
│                                    │
│  Үнэгүй 14 хоног туршиж үзэх       │
│  Кредит карт хэрэггүй              │
│                                    │
│  [ Имэйл хаяг             ]       │
│  [ Утасны дугаар          ]       │
│  [ Дэлгүүрийн нэр         ]       │
│                                    │
│  [  ҮРГЭЛЖЛҮҮЛЭХ  →  ]            │
│                                    │
│  Аль хэдийн бүртгэлтэй юу? Нэвтрэх │
└────────────────────────────────────┘
```

**Required fields:**
- Email (verified via OTP)
- Phone (Mongolia, +976)
- Store name

**Optional fields:**
- Store address
- Камер тоо (estimate)

**Backend actions:**
1. Create tenant record (status = `pending_verification`)
2. Send 6-digit OTP to email
3. Optionally: SMS OTP to phone

**Validation:**
- Email format check
- Mongolian phone format (+976 XXXX-XXXX)
- Store name uniqueness (per tenant scope only)

---

## 4. Step 2 — Plan Picker (Target: 1 минут)

### URL: `/plan`

**UI:**
```
┌─────────────────────────────────────────────────────────┐
│  Хэдэн камертай вэ?  [- 5 +]                            │
│  Хэдэн салбартай вэ? [- 1 +]                            │
│  Байршил: ⦿ Улаанбаатар  ◯ Орон нутаг                  │
│  Тохируулга: ⦿ Өөрөө  ◯ Sentry техник                  │
└─────────────────────────────────────────────────────────┘

┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  STARTER    │  │  PRO ⭐     │  │  ENTERPRISE │
│  ₮129K/сар  │  │  ₮233K/сар  │  │  Холбогдоно │
│             │  │             │  │             │
│  ✓ 5 cam    │  │  ✓ 12 cam   │  │  ✓ 50+ cam  │
│  ✓ Telegram │  │  ✓ Re-ID    │  │  ✓ Dedicated│
│  ✓ 7хон clip│  │  ✓ 30хон   │  │    GPU      │
│             │  │  ✓ All chan │  │  ✓ 90хон    │
│             │  │             │  │  ✓ 24/7     │
│             │  │             │  │             │
│  [ Сонгох ] │  │  [ Сонгох ] │  │  [ Холбоо ] │
└─────────────┘  └─────────────┘  └─────────────┘

[ 14 хоног үнэгүй туршиж үзэх → ]
```

**Logic:**
- Камер тоо нэмэгдэхэд auto plan recommendation
- Trial click → bypass payment, go to Step 4 directly
- Annual prepay toggle (10% off)

**Backend:**
- Save plan selection to tenant record
- Generate trial token (14-day expiry)

---

## 5. Step 3 — Payment + Verification (Target: 2 минут)

### URL: `/checkout`

**UI:**
```
┌────────────────────────────────────────┐
│  Pro Plan — 12 камер                   │
│                                        │
│  Сарын төлбөр:        ₮233,000        │
│  Setup fee:           ₮12,000         │
│  Эхний сар нийт:      ₮245,000 (+НӨАТ)│
│                                        │
│  Төлбөрийн арга:                       │
│  ⦿ QPay  (хамгийн хурдан)             │
│  ◯ Stripe (visa/master)               │
│  ◯ Bank transfer (manual confirm)     │
│                                        │
│  [  ТӨЛӨХ  →  ]                        │
│                                        │
│  💚 30-хоног мөнгө буцаах баталгаа    │
└────────────────────────────────────────┘
```

**Trial path:** Skip this step entirely. Go to Step 4.

**Backend:**
1. QPay/Stripe checkout session create
2. Webhook receive → confirm payment
3. Tenant status `pending_verification` → `active`
4. Generate API key (per-tenant)
5. Generate Docker installer signed URL with embedded API key
6. Send "🎉 Bayarlalaa" email + Telegram link

---

## 6. Step 4 — Docker Installer (Target: 5 минут)

### URL: `/install`

**UI:**
```
┌──────────────────────────────────────────────┐
│  ✅ Бүртгэл амжилттай                        │
│                                              │
│  Дараагийн алхам: Sentry Agent суулгах      │
│                                              │
│  Үйлдлийн систем сонго:                      │
│  [ 🖥️ Windows ]  [ 🐧 Linux ]  [ 🍎 macOS ] │
│                                              │
│  ⬇ татах: sentry-agent-installer.exe         │
│                                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━                │
│                                              │
│  📋 Заавар (3 алхам):                        │
│  1. Татсан файлыг ажиллуулна                │
│  2. Анхны бичсэн зөвшөөрлийг өгнө           │
│  3. Автоматаар сервертэй холбогдоно         │
│                                              │
│  [ Видео заавар үзэх ]                       │
│                                              │
│  💬 Туслалцаа хэрэгтэй юу? [ Чат нээх ]     │
└──────────────────────────────────────────────┘
```

**Installer багц багтаах зүйл:**
- Docker Desktop (хэрэв байхгүй бол install хийнэ)
- Sentry Agent docker image (~500 MB)
- Pre-configured config.yaml:
  ```yaml
  tenant_id: "tenant_abc123"
  api_key: "sk_live_xxx"  # signed
  server_url: "https://api.sentry.mn"
  store_id: "store_42"
  ```
- Windows service / systemd unit (auto-start on boot)

**Installer flow:**
1. User runs `.exe`
2. UAC prompt (admin зөвшөөрөл)
3. Check Docker installed → install if missing
4. Pull Docker image (progress bar)
5. Start container with config
6. Test connection to api.sentry.mn → ✅
7. Open browser to Step 5 (`/connect-cameras`)

**Web UI parallel update:**
- Real-time status: "Татаж байна..." → "Суулгаж байна..." → "Холбогдлоо!"
- Powered by WebSocket polling

---

## 7. Step 5 — Camera Auto-Discovery (Target: 5 минут)

### URL: `/connect-cameras`

**UI:**
```
┌──────────────────────────────────────────────┐
│  Камераа нэмэх                               │
│                                              │
│  Сүлжээгээ автоматаар scan хийх үү?          │
│  [ ✓ Камер хайх ] (~30 сек)                  │
│                                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━                │
│                                              │
│  Олдсон камерууд (ONVIF):                    │
│                                              │
│  ☑ 192.168.1.10  Hikvision DS-2CD2T  ✓ live │
│  ☑ 192.168.1.11  Dahua DH-IPC-HFW   ✓ live │
│  ☐ 192.168.1.12  Unknown camera      ⚠ test │
│                                              │
│  + RTSP URL гараар оруулах                   │
│                                              │
│  [ 2 камер холбох → ]                        │
└──────────────────────────────────────────────┘
```

**Auto-discovery technology:**
- ONVIF WS-Discovery probe (UDP multicast)
- Common RTSP URL patterns хайх (Hikvision/Dahua/Axis defaults)
- Manufacturer detection by MAC OUI

**Per-camera test:**
1. Connect to RTSP URL
2. Decode 1 frame
3. Show preview thumbnail
4. ✅ "Live"

**Manual fallback:**
```
RTSP URL: rtsp://admin:password@192.168.1.20:554/Streaming/Channels/101
[ Test ]
```

**Common camera credentials hint** (Mongolia popular brands):
- Hikvision default: admin / 12345
- Dahua default: admin / admin
- Axis default: root / pass

---

## 8. Final Step — First Detection 🎉

### URL: `/dashboard?onboarding=true`

**UI:**
```
┌──────────────────────────────────────────────┐
│  🎉 Бэлэн боллоо!                            │
│                                              │
│  ┌─────────────────────────────┐            │
│  │  [Live preview image]       │            │
│  │  ┌────┐                     │            │
│  │  │ 👤 │ P-1 detected!       │            │
│  │  └────┘                     │            │
│  └─────────────────────────────┘            │
│                                              │
│  Анхны хүн илэрлээ! 2 камер ажиллаж байна.  │
│                                              │
│  Дараах алхмууд:                             │
│  ☐ Telegram bot холбох (1 мин)              │
│  ☐ Бусад manager invite (2 мин)             │
│  ☐ Demo бичлэг үзэх (5 мин)                 │
│                                              │
│  [ Үндсэн dashboard руу → ]                  │
└──────────────────────────────────────────────┘
```

**Backend trigger:**
- First successful YOLO detection
- Send celebration push + email
- Trigger onboarding email sequence (Day 1)

---

## 9. Edge Cases & Drop-off Mitigation

### Drop-off point analysis (estimated)
| Step | Drop-off rate target | Mitigation |
|---|---|---|
| Signup → Plan | <10% | Минимал form, social proof |
| Plan → Payment | <20% | Trial option (skip pay) |
| Payment → Install | <5% | Clear next-step CTA |
| Install → Camera | <30% ⚠️ | Live chat, video tutorial |
| Camera → Detection | <15% | Auto-discovery, common defaults |

### "Stuck on install" fallback
Хэрэв 15 минутын дотор камер connect хийгдээгүй бол:
1. Auto-popup: "Туслалцаа хэрэгтэй юу?"
2. WhatsApp / Telegram support button
3. Free 30-min onboarding call schedule (Calendly link)
4. "Sentry technician suulgaad ogno уу?" — convert to paid setup

---

## 10. Onboarding Email Sequence (7-Day)

| Day | Subject | Content |
|---|---|---|
| 0 | 🎉 Sentry-д тавтай морил! | Welcome, Docker installer link |
| 1 | Анхны detect хийсэн үү? | If no detection: troubleshoot guide |
| 2 | Telegram bot холбосон уу? | Setup instructions |
| 3 | Дэлгүүрийн зураглал зурах | Camera placement best practices |
| 5 | False alarm-ыг мэдэгдэх | Feedback loop introduction |
| 7 | Анхны 7 хоногийн тайлан | Auto-generated insights report |
| 12 | Trial дуусахад 2 хоног үлдлээ | Convert to paid CTA |

---

## 11. Analytics Tracking Events (PostHog)

```javascript
// Critical funnel events
posthog.capture('signup_started')
posthog.capture('signup_completed', { plan_intent: 'pro' })
posthog.capture('plan_selected', { plan: 'pro', cameras: 12 })
posthog.capture('payment_started', { method: 'qpay', amount: 245000 })
posthog.capture('payment_completed', { revenue: 245000 })
posthog.capture('installer_downloaded', { os: 'windows' })
posthog.capture('agent_connected', { time_to_connect_seconds: 180 })
posthog.capture('camera_discovered', { count: 5, method: 'onvif' })
posthog.capture('camera_connected', { count: 2 })
posthog.capture('first_detection', { time_total_seconds: 720 })  // ~12 мин ✅
posthog.capture('onboarding_completed', { duration_seconds: 720 })
```

**Funnel dashboard:** `/admin/onboarding-funnel`

---

## 12. Technical Requirements (Engineering)

### Frontend (Next.js)
- `/signup`, `/plan`, `/checkout`, `/install`, `/connect-cameras`, `/dashboard`
- Real-time WebSocket для installer status
- QPay SDK integration
- Stripe Elements integration

### Backend (FastAPI)
- `POST /api/auth/signup`
- `POST /api/auth/verify-otp`
- `POST /api/billing/checkout-session`
- `POST /api/billing/webhook` (QPay, Stripe)
- `GET /api/installer/download` (signed URL)
- `POST /api/agents/register` (called by Docker agent on first start)
- `WS /api/onboarding/status` (real-time updates)

### Agent (Docker)
- Auto-update mechanism
- Telemetry: heartbeat to api.sentry.mn every 60s
- Local config validation
- ONVIF auto-discovery library

---

## 13. Acceptance Criteria

- [ ] Median signup → first detection time < 15 минут
- [ ] 80%+ users reach first detection
- [ ] <10% support tickets in first 24 hours
- [ ] QPay + Stripe payment success rate >95%
- [ ] Installer success rate >90% (Windows + Linux)
- [ ] ONVIF auto-discovery finds camera in >70% of networks

---

## 14. Холбогдох баримтууд

- `01_Sentry_PRD_v1.1.md` — FR-12 Self-Service Onboarding
- `03_Sentry_Pricing_Business_Model.md` — Plan tiers + pricing
- `05_Sentry_Multi_Tenancy_Architecture.md` — Per-tenant API key
