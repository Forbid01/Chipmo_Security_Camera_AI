# 05 — Customer Onboarding Playbook

> **Note (2026-04-21):** This document replaces the retired
> [`05-MIGRATION-PLAN.md`](./05-MIGRATION-PLAY.md) (hybrid edge →
> central migration). That file is archived prior art. This doc
> covers the **default SaaS product** — how Chipmo brings a new
> customer online via VPN + RTSP without shipping edge hardware.

## Зорилго

Шинэ харилцагчийг нээж, камеруудыг Chipmo-ийн центр серверт холбож,
AI detection-г ажиллуулах 1-2 цагийн алхам-алхмын playbook.

---

## 1. Preconditions (контракт тал)

### Customer side

- [ ] **Сайн дурсан зөвшөөрөл** (DPIA + consent form) MSA-тэй хамт гарын үсэг зурсан.
- [ ] Дэлгүүрийн камерууд **ONVIF Profile S** дэмждэг байх (ихэнх
  Hikvision, Dahua, TP-Link, EZVIZ, Uniview 2018 онооск дэмжинэ).
- [ ] Upload bandwidth дор хаяж **2 Mbps sustained** (4 камер / 480p /
  5 fps).
- [ ] Static internal IP эсвэл DHCP reserve VPN appliance-д.
- [ ] Router-ийн WireGuard UDP 51820 outbound зөвшөөрсөн (ихэвчлэн
  default-оор нээлттэй).

### Chipmo side

- [ ] VPN hub endpoint running (Phase A: Railway service, Phase B+: GPU box).
- [ ] Tenant provisioning script ажиллагаатай.
- [ ] Customer-д зориулсан tenant slot (Postgres schema, Qdrant collection, dashboard user).

---

## 2. Onboarding sequence (1-2 hour walkthrough)

### Step 1 — Tenant үүсгэх (Chipmo side, 5 мин)

```bash
./scripts/provision-tenant.sh \
  --org-name "Дэлгүүрийн нэр" \
  --primary-contact "Бат-Эрдэнэ (+976 99112233)" \
  --tier "business" \
  --camera-count 4
```

**Автомат хийнэ:**
- Postgres schema: `tenant_{uuid}` + Row-Level Security policies.
- Qdrant collection: `tenant_{uuid}_case_memory`, `tenant_{uuid}_reid_gallery`.
- Dashboard user: admin + staff (password reset link email).
- WireGuard peer key-pair generate, IP subnet `10.100.{octet}.0/29`.
- Billing record initialize.

**Output:** `onboarding-pack-{tenant-id}.zip`
- `wg0.conf` (VPN config)
- QR code (WireGuard mobile app-д scan хийхэд)
- Dashboard URL + login
- Camera config template

### Step 2 — VPN appliance сонголт (Customer-тай хамт, 10 мин)

Гурван option:

| Option | BOM | Setup time | Best for |
|---|---|---|---|
| **A. Chipmo брэндтэй router** | GL.iNet Beryl AX ($90) preloaded | 15 мин | Self-service, standard |
| **B. Raspberry Pi 4** | Pi 4 + microSD ($55) | 30 мин | Cost-sensitive, dev-friendly |
| **C. Existing hardware** | Customer-ийн Linux box / OpenWrt router | 30-60 мин | Tech-savvy customer |

**Санал болгож буй:** Option A. ₮150,000-д (ачаа + margin) харилцагчид
зарна, өөрсдөө interest-free 12 сарын хугацаатай хуваарилна.

### Step 3 — VPN appliance install (On-site эсвэл remote guidance, 15-30 мин)

1. **Router-ыг customer LAN-д залгах** (WAN port → modem, LAN port → downstream switch).
2. **Initial SSH / web UI-д нэвтрэх.** (Factory credentials.)
3. **Chipmo firmware уншуулах** (GL.iNet-ийн хувьд `uci` config,
   Raspberry Pi-ийн хувьд `chipmo-gateway` Debian package).
4. **`wg0.conf`-г install:**
   ```bash
   scp wg0.conf root@<device>:/etc/wireguard/wg0.conf
   systemctl enable --now [email protected]
   ```
5. **Verify:** `wg show` → handshake ≤5 сек.
6. **Tunnel route:** Customer LAN side-аас Chipmo hub side (10.99.0.1)-д ping.

**Checklist autom:** `scripts/verify-vpn-peer.sh --tenant-id <id>` script
Chipmo side-ээс handshake + latency + bandwidth test. Acceptance:
RTT <150ms, jitter <30ms, sustained 2 Mbps.

### Step 4 — Камерын sub-stream тохируулах (20-40 мин)

```bash
./scripts/onvif-config.py \
  --tenant-id <id> \
  --camera-ip 192.168.1.100 \
  --username <...> \
  --password <...> \
  --profile sub \
  --resolution 640x480 \
  --fps 5 \
  --codec h264
```

**Автомат хийнэ:**
- ONVIF discovery + camera capabilities.
- Sub-stream profile-ыг 480p / 5fps / H.264 / 512kbps-д update.
- RTSP URL fetch: `rtsp://user:[email protected]:554/Streaming/Channels/102`.
- Chipmo DB-д camera record INSERT, `camera_health.last_seen = now()`.

**Supported vendors (tested):**
- Hikvision (DS-2CD, DS-7-series)
- Dahua (IPC-series, SD-series)
- TP-Link (Tapo C-series, VIGI C-series)
- EZVIZ (C-series)
- Uniview (IPC-series)
- Axis (M-series, P-series) — manual fallback

**Manual fallback:** Камер ONVIF дэмждэггүй бол camer-ын web UI-гоор
гараар sub-stream тохируулна. Бичлэгийн template:
[`runbooks/camera-configs/`](./runbooks/camera-configs/).

### Step 5 — Камер илрүүлэх (Camera discovery, 5 мин)

Dashboard-д `Settings → Cameras → Add camera`:

1. Tenant VPN peer IP subnet-с автомат scan.
2. Discovered камер жагсаагдана (ONVIF responses).
3. Camera-д нэр өгөх: "Тавиур #1", "Касс", "Гарц" гэх мэт.
4. Map уpload (optional): Дэлгүүрийн зургаа upload хийж камер байрлалыг
   тэмдэглэх. Detection zone setup-д хэрэгтэй.

### Step 6 — Detection baseline тохируулах (15-30 мин)

1. **Detection zone draw** — камер бүрт "мониторинг хийх хэсэг" polygon.
   Гадагшаа, касс, тавиур гэх мэт. Outside-ийг ignore.
2. **Threshold initial** — Default: business tier 45.0, starter tier 50.0.
3. **Active hours** — Алертын цагийн хүрээ (24/7 эсвэл 9-21).
4. **Notification channels** — Telegram chat ID, SMS (optional), email.

### Step 7 — Smoke test (15-30 мин)

Customer staff-тай хамт:

1. **Live view check** — Dashboard-д камер бүрийн live feed харагдана.
   Acceptance: <2 сек latency.
2. **Walk-through test** — Staff "хулгайлах зан байдал" mime. 1-2
   alert үүсэх ёстой.
3. **Feedback loop test** — Test alert-д "False alarm" label дарах.
   Dashboard-д feedback бүртгэгдэнэ.
4. **Telegram verification** — Real alert Telegram-д ирсэн эсэх.

### Step 8 — Handoff + тренинг (30 мин)

- Dashboard training video буюу onsite walkthrough.
- **Yes / No feedback** хичнээн чухал гэдгийг тайлбарлах (moat!).
- Alert шалгах workflow: ажилтан → staff panic button → staff team.
- Escalation contact: Chipmo support чат.
- 30-хоногийн "честный" grace period: FP rate бага бол threshold auto-tune хийнэ.

---

## 3. Post-onboarding: First 30 days

### Day 0 - 7 (calibration week)

- [ ] **Daily FP review** — Chipmo engineer харилцагч бүрийн FP rate
  харж, threshold tune хийх.
- [ ] **Night mode validation** — Шөнө 0:00-6:00 FP spike-гүй эсэхийг
  баталгаажуулах.
- [ ] **Camera disconnect audit** — Heartbeat лог, DHCP reset issue.

### Day 7 - 30 (auto-learn warmup)

- [ ] **20+ feedback sample сугалагдах** — Per-store weight auto-tune
  kick in.
- [ ] **Weekly customer success call** — FP rate тренд, staff friction.
- [ ] **Case memory populate** — Real confirmed alert-ууд Qdrant-д
  build up.

### Day 30 review

- [ ] **SLA review** — Delivered alerts / missed events (staff reported
  but Chipmo missed).
- [ ] **Customer NPS / retention** — Готов ли customer year-1 contract-ыг
  үргэлжлүүлэх.

---

## 4. Off-boarding (contract end эсвэл termination)

- [ ] VPN peer revoke — `./scripts/revoke-vpn-peer.sh --tenant-id <id>`.
  Wireguard hub-ын config-аас pubkey устгана.
- [ ] Customer data export — MSA-ийн дагуу Json export + S3
  presigned link 30 хоногоор.
- [ ] **Data deletion** — 30 хоногийн grace period-ийн дараа:
  - Postgres tenant schema DROP.
  - Qdrant collection DELETE.
  - Re-ID gallery DELETE.
  - S3 alert clip purge.
- [ ] **Shared taxonomy contribution** — Tenant-ын contribution
  anonymized хэлбэрээр үлдэх эсэх customer-аас сонголт.
  Default: retain (contribution already anonymized).

Off-boarding log: `audits/offboarding-{tenant-id}-{date}.md`.

---

## 5. Edge cases

### 5.1 Harилцагчийн internet хэт удаашрах (<2 Mbps sustained)

**Opt 1:** Sub-stream-ийг 360p / 3fps-д downgrade. AI accuracy бага
буурна, alert delivery нэгэн адил.

**Opt 2:** Dynamic FPS governor-д "idle hours" config (e.g., night 22-06
= 1 fps, day = 5 fps).

**Opt 3:** 4G fallback router ($80-120 extra) санал болгох, ашиглахад
customer-д монолог.

### 5.2 Харилцагч WireGuard-ыг корпорат firewall-д зөвшөөрөхгүй

**Solution:** TCP-over-HTTPS tunnel (e.g. Cloak, TLS-over-WireGuard).
Engineer effort 1-2 цаг. Paid option.

### 5.3 Камер ONVIF-гүй (хуучин моделль)

**Solution:** Manual RTSP URL input. Vendor-specific config template-
уудыг [`runbooks/camera-configs/`](./runbooks/camera-configs/)-с ашиглах.

### 5.4 Multi-dэлгүүр tenant

**Solution:** Нэг org-д олон store, store бүрд өөр VPN peer. Dashboard-д
store selector. Cross-store aggregate reporting (org tier-д).

### 5.5 Харилцагч on-prem шаардаж байна

**Solution:** On-prem SKU redirect. See
[`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`](./decisions/2026-04-21-drop-edge-box-hybrid-architecture.md).
Playbook: [`runbooks/onprem-install.md`](./runbooks/onprem-install.md) (future).

---

## 6. Scripts / tooling summary

| Script | Purpose |
|---|---|
| `scripts/provision-tenant.sh` | Tenant slot + VPN peer үүсгэх |
| `scripts/provision-vpn-peer.sh` | Stand-alone VPN peer regen |
| `scripts/revoke-vpn-peer.sh` | Peer revoke |
| `scripts/verify-vpn-peer.sh` | Handshake + bandwidth test |
| `scripts/onvif-config.py` | Камерын sub-stream auto-config |
| `scripts/camera-discover.py` | LAN scan (ONVIF WS-Discovery) |
| `scripts/offboard-tenant.sh` | Data export + purge |

Бүгд Chipmo ops toolkit-д (`tools/ops-cli`) packaged ирнэ.

---

## 7. SLA summary (customer-facing)

| Metric | Target | Measurement |
|---|---|---|
| Onboarding completion | ≤ 2 цаг on-site эсвэл ≤ 1 хоног remote | Tenant creation → first confirmed alert |
| Uptime (monthly) | 99.0% Starter, 99.5% Business, 99.9% Enterprise | Alert dispatch successful / total events |
| Alert latency (confirmed event → Telegram) | P95 ≤ 5 сек | End-to-end trace |
| False positive rate (post-30-day calibration) | ≤ 10% of total alerts | Feedback label ratio |
| Internet outage tolerance | 24 hour local buffer (VPN appliance) | Backfill window |

---

## 8. Related documents

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) — System architecture
- [02-ROADMAP.md](./02-ROADMAP.md) — Development roadmap
- [04-INFRASTRUCTURE-STRATEGY.md](./04-INFRASTRUCTURE-STRATEGY.md) — Infra phase
- [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md) — DPIA / consent
- [10-PRICING-BUSINESS.md](./10-PRICING-BUSINESS.md) — Pricing tier
- `runbooks/camera-configs/` — Per-vendor manual config

### Superseded

- `05-MIGRATION-PLAN.md` — архивласан prior art (hybrid → central)

---

Updated: 2026-04-21
