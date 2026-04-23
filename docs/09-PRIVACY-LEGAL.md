# 09 — Privacy & Legal Compliance

> **Note (2026-04-21):** Centralized SaaS architecture-д шинэчлэгдсэн.
> Харилцагчийн raw video нь одоо Chipmo-ийн VPN tunnel-ээр
> Chipmo серверлүү дамжина. Энэ нь хуулийн хувьд хуучин edge-based
> архитектурт байхгүй байсан нэмэлт commitments үүсгэнэ:
> (1) "no recording" default, (2) ≤10сек alert clip retention, (3) per-tenant
> isolation баталгаа, (4) tenant opt-in для shared behavior taxonomy.
> See [`decisions/2026-04-21-centralized-saas-no-customer-hardware.md`](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md).

Монголын хувийн мэдээллийн хамгаалалтын хууль, GDPR-тэй нийцсэн байдал,
харилцагчтай байгуулах гэрээний шаардлагууд.

---

## ⚠️ Disclaimer

Энэ документ нь ерөнхий хандлага юм. Бодит хэрэгжүүлэлт хийхээс өмнө
Монгол Улсад зарлигдсан хуульч эрх бүхий этгээдийн зөвлөгөөг авах ёстой.

---

## 1. Монгол улсын хууль эрх зүйн орчин

### 1.1 Хувийн мэдээллийн хамгаалалтын тухай хууль (2021)

**Гол заалтууд:**

1. **Хувийн мэдээлэл** гэж хүний хувийн амьдрал, эрх зүйн байдал,
   эд хөрөнгө, нийгэм-хувийн орчинг тодорхойлох мэдээлэл.
   - Биометрийн мэдээлэл (нүүр, аавгийн өгөгдөл, хурууны хээ) нь **онцгой
     ангилалд** ордог.

2. **Биометрийн мэдээлэл цуглуулах, ашиглах**:
   - Зөвшөөрөл тодорхой, баримтжсан байх
   - Цуглуулах зорилго тодорхой (хулгай урьдчилан сэргийлэх)
   - Анхны зорилгоос өөр зорилгоор ашиглахыг хориглоно

3. **Харуулах тэмдэглэл (notice):**
   - Камер байгаа гэдгийг **харагдах газарт** мэдэгдэх
   - Өгөгдөл хэн цуглуулж, хэн боловсруулж, хэдий хугацаа хадгалахыг
     олон нийтэд ил болгох

4. **Мэдээлэл хадгалах хугацаа:**
   - Зорилгод шаардлагатай хугацаанаас урт биш
   - Харилцагчийн дотоод бодлоготой уялдсан байх

5. **Мэдээлэл хилийн гадна гаргах:**
   - Хилээр гадагшлуулах бол тусгай зөвшөөрөл
   - Centralized SaaS архитектурт raw video харилцагчаас Chipmo-ийн
     сервер рүү дамждаг. Phase A (Railway) болон Phase B (cloud GPU)
     зарим тохиолдолд гадаад юрисдикц (US/EU) байж болно → MSA-д
     **explicit cross-border transfer consent clause** заавал байна.
   - Phase C (owned GPU) Монголын datacenter-д байрлуулснаар хилийн
     гадна дамжуулалтыг устгана — energy reg compliance-ийн хамгийн
     цэвэр хувилбар.

### 1.2 Зөрчлийн хариуцлага

- Захиргааны шийтгэл: 500,000₮ - 10,000,000₮
- Хууль зүйн байгууллагын шалгалт
- Харилцагчтай эрх зүйн маргаан хохирол

---

## 2. GDPR alignment (future international expansion-д)

Харилцагч бүртгэлд ЕХ-ны дэлгүүр нэмэхэд GDPR хэрэгжинэ. Систем GDPR-тэй
нийцтэй байх зарчмуудыг баримтална:

### 2.1 Data subject rights

| GDPR Right | Implementation |
|---|---|
| Right to access | Harilцагч API-ээр өөрийн store-тай холбоотой бүх өгөгдөл татна |
| Right to erasure | `DELETE /api/v1/users/{id}` каскад хийнэ |
| Right to rectification | `PATCH` endpoint бүгд |
| Right to data portability | JSON/CSV экспорт |
| Right to object | Face blur opt-out config |
| Right to restrict processing | `is_active` flag |

### 2.2 Privacy by design

- Face blur default on
- Clip retention short default (48h)
- Encryption at rest
- Access log (audit_log table)
- Minimized data collection (pose keypoints-ыг encrypt хадгална)

### 2.3 Data Processing Agreement (DPA)

Харилцагчтай байгуулна. Template: `legal/dpa_template_v1.docx`.

---

## 3. System-level privacy measures

### 3.1 Face blur

**Default:** ON for all new stores.

**Харилцагч opt-out хийх боломжтой:**
- Хуулийн зөвшөөрлөөрөө l
- Бодит хулгайч танихад нүүр зайлшгүй гэсэн нөхцөлд

**Implementation:**
- YOLO pose keypoint ашиглан face bbox detect
- CV2 GaussianBlur (51x51 kernel)
- Хадгалах clip-д blur хийнэ, inference frame-д blur хийхгүй
  (accuracy-д нөлөөлөхгүй)

**Config:** `store_settings.face_blur_enabled`

### 3.2 Clip encryption at rest

- AES-256-GCM
- Key per store
- Key storage: HashiCorp Vault эсвэл AWS KMS
- Decrypt only on demand (audit log хийнэ)

**Implementation details:**
- FastAPI middleware decrypt-д хариуцна
- Symmetric key rotation 90 хоногт 1 удаа
- Old key-ийг 180 хоног хадгална (backwards compat)

### 3.3 Audit log

Бүх өгөгдөл хандалтыг тэмдэглэнэ:

```sql
-- audit_log table (see 06-DATABASE-SCHEMA.md)
-- action values:
--   view_clip, download_clip, share_clip
--   label_clip, delete_clip
--   view_alert, export_alerts
--   config_change, user_created, user_deleted
```

Retention: 1 жил.

### 3.4 Network isolation

- **Харилцагч LAN:** Камерууд тусдаа VLAN, internet access NO
  (customer-ийн router-т тохируулна).
- **VPN appliance:** Chipmo-ийн WireGuard peer (GL.iNet router эсвэл Pi)
  зөвхөн outbound UDP 51820 ашиглана. Customer LAN-ийн бусад device
  рүү routing байхгүй.
- **WireGuard tunnel:** ChaCha20-Poly1305 encrypted. Peer pubkey
  rotation 180 хоногт.
- **Chipmo hub:** Inter-peer traffic дефолт DROP (iptables policy),
  зөвхөн peer ↔ hub зөвшөөрөгдсөн. Өөр tenant-ын peer рүү traffic
  боломжгүй.
- **TLS 1.3** бүх HTTPS endpoint.
- **Per-tenant network namespace** (Phase B+): ingest worker-ууд
  нэг-нэгэнд шаардлагагүй байдлаар isolated.

### 3.5 Data minimization & no-recording default

**Core commitment to customer:** Chipmo **бичлэг хийдэггүй**. Video
stream нь RAM-д decoded, inference-д ашиглагдаж, дараа нь буцааж шалгах
боломжгүй ба буцааж гаргагдах боломжгүй.

**Exception — confirmed alert clip only:**
- Layer 3 VLM verify-р пасс хийсэн event-д л ≤10 сек video clip
  persist хийнэ.
- Clip нь per-tenant encryption key-ээр AES-256-GCM encrypt.
- Clip retention (см §3.6) — default 30 хоног, tenant policy-оор
  богиносгож болно.

**Биометрийн мэдээллийг хадгалахыг хязгаарлана:**
- Face embedding **НЕ** хадгална (Re-ID-д нүүрээс биш биеэс embedding).
- OSNet нь биеийн appearance (хувцас, физик хэмжээ) дээр сурсан.
- Pose keypoint нь нүүрний 5 цэгийг (нүд, хамар, чих) ашигладаг хэдий ч
  эдгээрийг нэрлэлттэй холбогдсон хэлбэрээр хадгалахгүй.

### 3.6 Retention policy (centralized SaaS)

| Data | Retention | Justification |
|---|---|---|
| Live RTSP stream | **0** (in-memory only) | Chipmo "no recording" commitment |
| VPN appliance local ring buffer | 24h max | Internet outage backfill only; customer-side |
| Alert clip (unlabeled) | 30 хоног | Investigation window |
| Alert clip (labeled theft) | 2 жил | Эрх зүйн маргаан, training |
| Alert clip (labeled FP) | 6 сар | Hard-negative training |
| Feedback labels | Unlimited | Model improvement |
| Re-ID embedding (per-tenant) | 30 хоног default, tenant-configurable | GDPR-aligned, opt-in extension |
| Shared behavior taxonomy | Unlimited (anonymized, no PII) | Product moat, audit-safe |
| Audit log | 1 жил | Compliance |
| Metrics | 30 хоног | Ops |

### 3.7 DPIA (Data Protection Impact Assessment)

Centralized SaaS архитектурт раw video customer premises-ээс гардаг
тул DPIA бичиж, харилцагчтай хамт батлуулна:

- **Шаардлагатай үе:** Первый paid customer-ын өмнө.
- **Template:** `legal/dpia_template_v1.docx` (Монгол + Англи).
- **Тууз хэсгүүд:**
  1. Processing descriptn (юу хийнэ, юуны төлөө)
  2. Necessity + proportionality assessment
  3. Risk (хэн нөлөөлнө: харилцагч ажилтан, үйлчлүүлэгч, 3rd party)
  4. Mitigation measures (анонимчлал, retention, access control)
  5. Cross-border transfer (Phase A/B — зарим хугацаанд)
  6. Monitoring + review plan

- **Update cycle:** Жил бүр эсвэл архитектур томоохон өөрчлөлтөнд.
- **Public-facing summary:** Simplified version on chipmo.mn/privacy.

### 3.8 Shared behavior taxonomy — opt-in consent

Tenant-ын confirmed alert-оос anonymized pose pattern-ийг
`behavior_taxonomy_v1` Qdrant collection-д бичих нь **opt-in** (MSA-д
tick-box, default ON байх боловч customer мэдээлэлтэй).

**Anonymization guarantees:**
- NO tenant_id
- NO store_id / camera_id
- NO person_reid_id
- NO image / clip reference
- NO timestamps (just temporal_window_sec)

See [`03-TECH-SPECS.md`](./03-TECH-SPECS.md) §14 for technical
enforcement. Test harness `tests/test_taxonomy_anonymization.py`
должен pass before any release touching taxonomy write path.

---

## 4. Харилцагчтай байгуулах гэрээ (Customer agreement)

### 4.1 Үндсэн гэрээ (Master Service Agreement)

**Гол заалтууд:**

1. Үйлчилгээний тодорхойлолт
2. Хугацаа (анх 12 сар, autorenewal)
3. Үнэ тариф (setup + monthly)
4. SLA (uptime, support хариу)
5. Төлбөрийн нөхцөл
6. Гэрээ цуцлах шалтгаан
7. Нууцлалын заалт
8. Хариуцлагын хязгаарлалт
9. Маргаан шийдвэрлэх

### 4.2 Data Processing Agreement (хувийн мэдээллийн тусгайбуув агшин)

**Харилцагч = Data Controller**
**Chipmo = Data Processor**

**Гол үүрэг:**

| Үүрэг | Харилцагч | Chipmo |
|---|---|---|
| Зорилго тодорхойлох | ✓ | |
| Зөвшөөрөл цуглуулах | ✓ (Байшин дахь мэдэгдлээр) | |
| Мэдээлэл боловсруулах | | ✓ |
| Аюулгүй байдал хангах | | ✓ |
| Зөрчил мэдэгдэх | | ✓ (24 цагт) |
| Retention эвдэрсэн эрх шийдвэрлэх | ✓ | ✓ (technical support) |

**Харилцагчийн уялдсан үүрэг:**
- Камерын дэргэд "CCTV AI ашигласан, өгөгдөл X хугацаанд хадгалагдана"
  гэсэн мэдэгдэл тавих
- Ажилтнууддаа мэдэгдэх
- Зөвхөн хууль хамгаалалтын байгууллагад хүсэлтээр өгөгдөл өгөх

### 4.3 Sample clause (template-аас)

```
ХЭСЭГ 5. ХУВИЙН МЭДЭЭЛЛИЙН ХАМГААЛАЛТ

5.1. Chipmo-оос харилцагчийн төлөөлөлд мэдээллийг Монгол Улсын "Хувийн
мэдээллийн хамгаалалтын тухай" хуульд заасан зарчмыг баримталж
боловсруулна.

5.2. Харилцагч нь дэлгүүр дэх камерын зохистой мэдэгдэлийг тавих үүргийг
хүлээнэ. Chipmo мэдэгдлийн загварыг үнэ төлбөргүй өгнө.

5.3. Харилцагчийн дэлгүүрийн видео мэдээлэл зөвхөн харилцагчийн өмч
бөгөөд Chipmo нь техникийн боловсруулалт, хадгалах зорилгоор
хандана.

5.4. Chipmo нь видео мэдээллийг:
    а) Нэг харилцагчийн өгөгдлийг өөр харилцагчид ил болгохгүй
    б) Гуравдагч этгээдэд худалдахгүй
    в) Reklaам, профайлинг зорилгоор ашиглахгүй

5.5. Харилцагч гэрээ цуцалбал:
    а) 30 хоногт бүх clip устгагдана
    б) Feedback label-ууд анонимчилж, identifier-гүй болгосны
       дараа хадгалагдаж болно (model improvement)
```

---

## 5. Employee monitoring асуудлууд

### 5.1 Ажилтнууд дээр монитор хийх ethics

Систем нь ажилтнуудыг шууд шинжлээгүй ч, ажилтан "сэжигтэй зан" гаргавал
alert trigger болох боломжтой.

**Зөвлөмж harilцагчид:**

1. Ажилтнуудад урьдчилан мэдэгдэх
   ("Энэ дэлгүүрт AI-тэй камерын систем ажилладаг")
2. Tax/payroll цаг бүртгэлд ашиглахгүй
3. Ажилтны "ажлын бүтээмж"-ийг хэмжихэд ашиглахгүй
4. Зөвхөн хулгайлалтын сэжиг илэрсэн үед л ажилтнуудын данстэй
   харьцуулах (human-in-the-loop)

### 5.2 Suggested store notice (Монгол)

```
ЭНЭ ДЭЛГҮҮРТ CCTV AI СИСТЕМ ТАВИГДСАН

Энэ дэлгүүрт хулгайлахаас урьдчилан сэргийлэх зорилгоор
хиймэл оюун ухаантай камерын систем ажиллаж байна.

• Бичлэг хадгалах хугацаа: 30 хоног
• Мэдээллийг хариуцагч: [ХАРИЛЦАГЧИЙН БАЙГУУЛЛАГА]
• Техник operator: Chipmo LLC

Асуулт, гомдол байвал:
[Харилцагчийн имэйл] / [Утас]
```

---

## 6. Алертын clip хуваалцалт

### 6.1 Зорилгогүй хуваалцахыг хориглоно

Dashboard-д clip download хийхэд:
- Default: **зөвхөн view** (browser-д stream)
- Download хийх бол "Зорилго" гэсэн талбар бичиж бичих

Audit log-д бичигдэнэ.

### 6.2 Хуулийн байгууллагад өгөх

Цагдаа, шүүхээс албан хүсэлт ирвэл:
1. Хууль ёсны эсэхийг харилцагч + Chipmo хоёр баталгаажуулна
2. Chipmo нь харилцагчийн зөвшөөрөлгүйгээр клип өгөхгүй
3. Өгсөн тохиолдолд audit log-д бичнэ

---

## 7. Breach response plan

### 7.1 Зөрчлийн төрөл

| Төрөл | Жишээ | Ноцтой байдал |
|---|---|---|
| Unauthorized access | DB-д хэн нэгэн логин хийсэн | Critical |
| Data leak | Clip гуравдагч этгээдэд очсон | Critical |
| Misconfiguration | Public bucket-д clip upload | High |
| System intrusion | RCE, exploit | Critical |
| Employee negligence | Клипийг Facebook-д post хийсэн | Med |
| Harilцагч misuse | Ажилтнуудыг мониторинг хийсэн | Med |

### 7.2 Response timeline

**0-2 цаг:** Detection, containment
- Эцэг IP block
- Affected token revoke
- DB access log audit

**2-12 цаг:** Investigation
- Scope тодорхойлох (affected stores, users)
- Forensic analysis
- Root cause identify

**12-24 цаг:** Notification
- Хуулиар шаардагдсан бол MOJ-д мэдэгдэх
- Харилцагчид имэйл (affected-д шууд, бусдад ерөнхий update)

**24-72 цаг:** Remediation
- Fix deploy
- Password reset (affected users)
- Enhanced monitoring

**1 долоо хоног:** Postmortem
- Blameless postmortem
- Process improvement
- Public disclosure (if applicable)

---

## 8. Legal review checklist (quarterly)

- [ ] Хувийн мэдээллийн хууль шинэчлэлт шалгах
- [ ] GDPR нийцэл audit (expand рүү орж байгаа бол)
- [ ] Харилцагчтай гэрээний template шинэчлэл
- [ ] Privacy notice (web + in-store) шинэчлэл
- [ ] Retention policy эвдрэх эсэх
- [ ] Sub-processor list шинэчлэл
- [ ] Encryption key rotation
- [ ] Audit log review

---

## 9. Vendor / Sub-processor list

Chipmo дээр ажиллахад ашигладаг гуравдагч этгээдийг харилцагчид ил
болгоно.

| Vendor | Purpose | Data accessed | Location |
|---|---|---|---|
| AWS / Хост provider | Infra hosting | Encrypted metadata | Optional MN hosting |
| Sentry | Error tracking | Metadata (no PII) | EU |
| Telegram | Notifications | Alert metadata | Global |
| OpenAI (if any) | ❌ NONE | — | — |
| Anthropic (if any) | ❌ NONE | — | — |

*Санамж:* Self-hosted зарчмын дагуу external AI API (OpenAI, Anthropic,
etc.) хэрэглэхгүй.

---

## 10. Internal training

Бүх Chipmo staff жилд 1 удаа (эцэст нь enroll):

- Privacy fundamentals (1 цаг)
- Монгол хуулийн overview (1 цаг)
- Incident response drill (30 мин)
- Secure coding (30 мин)

Tracker: `hr/compliance_training_tracker.xlsx`.

---

## 11. Harilцagчийн зөвшөөрлийн форм (consent)

Шинэ харилцагчийн onboarding-д signin хийнэ:

```
ЗӨВШӨӨРЛИЙН ФОРМ

Би ________________________________ (албан тушаалтан)
________________________________ (харилцагч байгууллага)-ийн
төлөөлөгчөөр дараах зүйлд зөвшөөрч байна:

☐ Дэлгүүрийн CCTV камераас видеог хиймэл оюун ухааны
   боловсруулалтанд ашиглах

☐ Дэлгүүрт харагдах газарт "AI CCTV идэвхтэй" мэдэгдэл тавих

☐ Ажилтнуудад энэ системийн тухай мэдэгдэх

☐ Зөрчил илэрвэл 24 цагт дотор Chipmo-д мэдэгдэх

☐ Chipmo-тэй хуваалцсан өгөгдлийг нэмэх гуравдагч этгээдэд
   өгөхгүй (зөвхөн Chipmo-тэй processing хийгдэнэ)

Гарын үсэг: _____________________
Огноо: _____________________
```

---

## 12. Checklist: Шинэ feature launch-д

Privacy-г барьцаалж шинэ feature launch-дах гэвэл:

- [ ] Privacy Impact Assessment (PIA) form filled
- [ ] Data flow diagram updated
- [ ] Retention policy defined
- [ ] Encryption / access control verified
- [ ] Audit log events added
- [ ] Legal review (if processing new data type)
- [ ] Customer notification (if material change)
- [ ] DPA annex update (if needed)

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md) (privacy-by-design section)
- [06-DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md) (audit_log, encryption)
- [07-API-SPEC.md](./07-API-SPEC.md) (auth, access control)
- [decisions/2026-04-21-centralized-saas-no-customer-hardware.md](./decisions/2026-04-21-centralized-saas-no-customer-hardware.md)

---

Updated: 2026-04-21
