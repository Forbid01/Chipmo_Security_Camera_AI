# Chipmo Security Camera AI — Гадны өрсөлдөгчдийн судалгаа

**Огноо:** 2026-04-16
**Бэлтгэсэн:** Claude (Cowork)
**Төсөл:** [Chipmo_Security_Camera_AI](https://github.com/Forbid01/Chipmo_Security_Camera_AI)

---

## Агуулга

1. [Гол өрсөлдөгчид (Tier 1)](#1-гол-өрсөлдөгчид-tier-1)
2. [Бизнес процессийн харьцуулалт](#2-бизнес-процессийн-харьцуулалт)
3. [Технологийн харьцуулалт](#3-технологийн-харьцуулалт)
4. [Chipmo-ийн давуу тал (Differentiation)](#4-chipmo-ийн-давуу-тал-differentiation)
5. [Суралцах боломжууд (Key Learnings)](#5-суралцах-боломжууд-key-learnings)
6. [Зах зээлийн position](#6-зах-зээлийн-position)
7. [Дараагийн алхам](#7-дараагийн-алхам)
8. [Эх сурвалж](#эх-сурвалж)

---

## 1. Гол өрсөлдөгчид (Tier 1)

### 🇫🇷 Veesion (Франц) — Chipmo-той хамгийн ойр

- **Нийт санхүүжилт:** €38M Series B (2024)
- **Бизнес загвар:** SaaS, per-camera monthly fee (~$200-500/сар/дэлгүүр)
- **Технологи:** Gesture recognition (Deep Learning), existing CCTV-д холбогддог, 30 минутын суурилуулалт
- **Detection:** "Gesture-based AI" — бүтээгдэхүүнийг халаас, цүнх, хүрмэнд нуух үйлдлийг тусгайлан илрүүлдэг
- **Privacy:** Face recognition **ашигладаггүй** (EU GDPR-т тохируулсан)
- **Үр дүн:** Дэлгүүр бүрт сард 15+ хулгай илрүүлж, жилд ~$7K хэмнэлт
- **Сул тал:** Өдөрт 10+ alert, **90% false positive** (жижиг retailer-ууд гомдоллодог)

### 🇮🇪 Everseen (Ирланд) — Enterprise аварга

- **Нийт санхүүжилт:** $70M+ (2023)
- **Хэрэглэгч:** Walmart, Kroger, Meijer, Woolworths — 140,000+ checkout, 8,000+ дэлгүүр
- **Ялгаатай чухал:** **Checkout/POS-д гол төвлөрдөг** ("Missed Scan Detection") — Chipmo-гээс тэс өөр use case
- **Технологи:** Google Cloud + Vertex AI partnership (2025), ceiling-mounted камер + CV
- **2026 шинэчлэл:** Conversational AI layer нэмсэн (ажилчид LLM-тэй ярилцах боломж)
- **Сул тал:** Ажилчид "NeverSeen" хочтой — Wired сэтгүүлийн мөрдлөгөөгөөр илэрхий хулгайг алдаад, ердийн үйлдлийг flag хийдэг

### 🇺🇸 Scylla AI — Multi-threat platform

- **Use case:** Зөвхөн хулгай биш — **gun violence, perimeter intrusion, thermal screening** гэх мэт олон threat-ийг зэрэг хамардаг
- **Technical claim:** 99.95% false alarm filtering, <1 секундын хариу
- **Ялгаа:** Face recognition ашигладаг (repeat offender database), энэ нь Монголын хуулийн орчинд эмзэг сэдэв
- **Integration:** Бараг бүх VMS/камертай compatible

### 🇺🇸 Sensormatic (Johnson Controls) — Hardware + AI гибрид

- **Бизнес:** Том enterprise, RFID + EPC + computer vision гурвыг нийлүүлсэн
- **Partner:** Intel-тэй хамтарсан, proprietary chip-тэй
- **Шинэ feature:** "Shelf Sweep Detection" — тавиурыг нэг дор цэвэрлэх үйлдэл
- **Pricing:** Enterprise-only, custom quote (Chipmo-ийн SME/chain-тэй өрсөлдөхгүй сегмент)

### 🇺🇸 Dragonfruit AI / Lexius / 3DiVi / Anavid (Hikvision) — Mid-tier

- **Dragonfruit:** "AI agents" нэртэй, existing video-д нэмэлт layer
- **3DiVi:** Олон удаагийн тавиур зочлох, удаан зогсох, сэжигтэй хөдөлгөөнийг илрүүлдэг
- **Anavid (Hikvision):** Хятадын Hikvision camera-тай хамт, Азид түгээмэл — **Монголд танай шууд өрсөлдөгч байж болзошгүй**

---

## 2. Бизнес процессийн харьцуулалт

| Үе шат | Veesion | Everseen | Chipmo (та) |
|---|---|---|---|
| **Суурилуулалт** | 30 мин, plug-and-play server | Enterprise integration (долоо хоног) | Docker deploy — ойролцоо |
| **Detection focus** | Gesture (нуух үйлдэл) | POS/checkout алдаа | Pre-theft predictive + gesture |
| **Alert delivery** | Mobile app, богино видео | Store associate terminal | Telegram + push + dashboard ✅ |
| **Evidence storage** | Alert видеог хадгалдаг | Checkout snippet | **Auto-clip хадгалдаг** ✅ |
| **Pre-theft warning** | ❌ Байхгүй (event зөвхөн) | ❌ Байхгүй | ✅ **Таны гол давуу тал** |
| **Risk scoring** | Бинари alert | Transaction anomaly | ✅ Weighted score (item pickup 15, wrist-to-torso 5...) |
| **Feedback loop** | Manual review | Analyst team | ✅ Auto-learning |

---

## 3. Технологийн харьцуулалт

| Компонент | Гадны leader-ууд | Chipmo |
|---|---|---|
| **Detection model** | Custom Deep Learning (Veesion), 3D CNN (Anavid), proprietary (Everseen) | **YOLO11 pose** (Ultralytics) — open source, хурдан iterate |
| **Infrastructure** | On-prem server + cloud (Veesion), Google Cloud/Vertex AI (Everseen) | Docker Compose, FastAPI async, PostgreSQL |
| **Model training** | Millions of labeled retail clips | Auto-learning feedback loop |
| **Deployment** | Edge server in store | Cloud-heavy (магадгүй edge болгож болно) |
| **False positive rate** | Veesion: ~90% FP (reported) | Weighted scoring-тэй тул багасах боломжтой |
| **Privacy** | Veesion: no face recognition. Scylla: uses face recognition | Pose keypoints only — GDPR/Монгол хуульд найдвартай |

---

## 4. Chipmo-ийн давуу тал (Differentiation)

Судалгаанаас харахад таны системд **3 гол unique value** байна:

1. **Pre-theft predictive alert** — Veesion, Everseen аль аль нь зөвхөн "хулгай гарсан" alert-тай. Та "эрсдэл өсч байна" гэдэг **early warning layer** нэмсэн. Энэ нь сэтгэл зүйн deterrent болно — ажилчин ойртоод л хулгайчийг зогсооно.

2. **Weighted risk scoring (6 behavior, өөр өөр жин)** — ихэнх leader-ууд бинари alert явуулдаг. Таны scoring framework false positive-ийг багасгах найдвартай механизм.

3. **Auto-clip evidence management** — хэрэглэгч хэдэн цагийн бичлэг гуйлж суух шаардлагагүй, системд автоматаар кейс файл үүсгэнэ. Энэ нь Veesion-ий "short mobile video" дээр нэмэлт давуу тал.

---

## 5. Суралцах боломжууд (Key Learnings)

### 🎯 False positive асуудлыг hard-code бай

**Асуудал:** Veesion 90% FP-тэй, Everseen "NeverSeen" хоч авсан. Энэ салбарын #1 сөрөг зүйл.

**Санал:**

- **"Human-in-the-loop" verification tier** нэм — high-risk alert шууд явуулахгүй, 3-5 секундын делай дотор score 2 дахь нэвтрүүлэг хийдэг болго.
- **Per-store calibration** — нэг дэлгүүрийн threshold нөгөөд тохирохгүй (жимс, мах тавиурууд руу гар сунгах нь хулгай биш).
- **Shadow mode** — шинэ дэлгүүрт эхний 2 долоо хоног alert явуулахгүй зөвхөн metric цуглуул.

### 🎯 POS-level ялгарлыг бий болго (Everseen-аас суралц)

Everseen-ий гол value нь **checkout-д түлхүү** — scan алддаг юмуу, баркод солих зэрэгт чиглэдэг. Chipmo-д **POS fraud module** нэмбэл:

- Self-checkout-ийн "missed scan" илрүүлэлт
- Касс ажилчин найздаа дискаунт өгөх (sweethearting) илрүүлэлт
- Retail chain-д дахин нэг premium tier болж өгнө

### 🎯 Edge deployment болж өг (unit economics)

Veesion-ий суурилуулалт компакт server шаарддаг. Үүнд суралцаж:

- **NVIDIA Jetson Orin Nano** (~$500) дээр YOLO11-ийг quantize хийж ажиллуулбал cloud cost эрс буурна.
- Internet тасрахад локал ажиллах боломж — Монголын дэлгүүрүүдэд чухал.

### 🎯 Conversational layer нэм (Everseen 2026 хандлага)

Everseen-ий хамгийн шинэ шинэчлэл: **managers can ask the AI** ("өчигдөр хамгийн их сэжигтэй үйл хаана байсан?"). Chipmo-д LLM layer нэмбэл:

- "Энэ долоо хоногт 5-р тавиур руу хэдэн удаа сэжигтэй ойртсон бэ?"
- "Хамгийн их хулгай гардаг цаг, байршлыг тайлан болгож өг"
- Монгол хэлээр query хүлээн авах — **локал давуу тал**

### 🎯 Privacy-first messaging (Veesion-ээс суралц)

Veesion "no facial recognition" гэсэн messaging-ээр EU-д итгэлцэл байгуулсан. Та эдгээрийг sales deck-дээ highlight хий:

- "Зөвхөн skeletal pose keypoint"
- "Ямар нэг биометр өгөгдөл хадгалдаггүй"
- "Монголын Хувийн нууцын тухай хуульд 100% нийцтэй"

### 🎯 ROI калькулятор онлайн тавь (Veesion хийдэг)

Veesion сайт дээрээ "сард хэр хэмнэнэ" калькулятортой. Chipmo landing page-д **Монгол төгрөгөөр** ROI калькулятор нэмбэл conversion эрс сайжирна.

---

## 6. Зах зээлийн position

```
Enterprise (100+ store chain)     │  Everseen, Sensormatic
Mid-market (10-100 store)          │  Veesion, Scylla  ← ӨРСӨЛДӨГЧ
SME / Local retail (1-10 store)    │  ⭐ CHIPMO opportunity
                                     (Монгол, CIS, SEA markets)
```

**Strategic санал:** Veesion-ийг Монгол дахь локал alternative болж байршуул. Дараах боломжууд:

- Монгол хэлний dashboard
- Монгол банк/ERP-тэй integration (G-Mobile SMS, Unitel alerts, ...)
- Local support timezone
- Төгрөгөөр billing
- ~30-50% хямд price point (starter tier $50-80/сар/камер)

---

## 7. Дараагийн алхам

Дараах ажлуудын аль нь танд хамгийн ач холбогдолтой вэ:

1. **Detailed tech benchmark** — Veesion gesture model vs YOLO11 pose accuracy тест хийх plan
2. **Competitive battlecard** — sales team ашиглах нэг хуудсан pitch document
3. **Product roadmap v2** — дээрх learning-үүдийг Q2–Q4 2026 roadmap болгож буулгах
4. **Pricing strategy** — Veesion/Everseen-тэй харьцуулсан 3-tier pricing model
5. **Investor deck section** — "Competitive moat" slide бичих

---

## Эх сурвалж

- [Veesion AI — Gesture-based theft detection](https://veesion.io/en/)
- [White Star Capital — Why we invested in Veesion](https://whitestarcapital.medium.com/transforming-retail-security-with-gesture-based-ai-why-we-invested-in-veesion-f21a62c8fef3)
- [Everseen — Enterprise retail AI](https://everseen.com/)
- [TechCrunch — Everseen $70M raise](https://techcrunch.com/2023/05/11/everseen-raises-over-70m-for-ai-tech-to-spot-potential-retail-theft/)
- [SiliconANGLE — Everseen conversational AI 2026](https://siliconangle.com/2026/01/12/everseen-adds-conversational-intelligence-layer-ai-theft-prevention-system/)
- [Scylla AI — Retail security suite](https://www.scylla.ai/retail-security-suite/)
- [Sensormatic — AI shrink visibility](https://www.sensormatic.com/resources/pr/2021/sensormatic-iq-shrink-visibility)
- [Arcadian AI — Why AI theft solutions fail (2025)](https://www.arcadian.ai/blogs/blogs/shoplifting-detection-2025-why-ai-solutions-fail-and-how-retailers-must-think-differently)
- [AppIntent — 8 Best Computer Vision Theft Detection Platforms 2026](https://www.appintent.com/software/ai/computer-vision/theft-detection/)
- [SAI Group vs Everseen comparison 2026](https://news.saigroups.com/sai-group-vs-everseen/)
