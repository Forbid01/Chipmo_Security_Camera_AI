# 05 — Migration Plan: Centralized → Hybrid Edge

> ⚠️ **SUPERSEDED (2026-04-21):** Энэ документ нь hybrid edge-д шилжих
> migration-ыг агуулсан боловч тэр architecture нь
> [`decisions/2026-04-21-drop-edge-box-hybrid-architecture.md`](./decisions/2026-04-21-drop-edge-box-hybrid-architecture.md)-р
> татгалзагдсан. Одоогийн default архитектур нь centralized SaaS —
> customer onboarding-ийг
> [`05-ONBOARDING-PLAYBOOK.md`](./05-ONBOARDING-PLAYBOOK.md)-с харна уу.
> Документ prior art-ын хувьд үлдсэн.

Одоогийн централизованный архитектураас hybrid edge архитектурт
шилжих алхам-алхмын төлөвлөгөө.

---

## 1. Migration-ын философи

**Zero downtime. Dual-write validation. Gradual cutover.**

Одоо ажиллаж байгаа харилцагчид үйлчилгээ алдагдалгүйгээр шинэ архитектур
руу шилжнэ. Migration 3 үе шатаар явагдана:

1. **Dual-run** — Central + Edge зэрэг ажиллана, үр дүнг харьцуулна
2. **Edge-primary** — Edge тал primary, Central standby
3. **Central-retire** — Central зөвхөн management/sync функцтэй үлдэнэ

---

## 2. Pre-migration checklist

Шилжилт эхлэхийн өмнө дараах нь бэлэн байх ёстой:

- [ ] Target architecture-ын бүх компонент production-д deploy-дсэн
  - [ ] Edge box OS image баталгаажсан
  - [ ] Edge-Central sync protocol тест
  - [ ] Central API-д edge endpoint-ууд нэмэгдсэн
- [ ] Hardware bulk procurement (3-5 spare edge box)
- [ ] Monitoring: Grafana dashboard ready
- [ ] Харилцагч notification template (Mongol)
- [ ] Rollback plan (доор 4-р хэсэгт)
- [ ] Staff бэлтгэлтэй (install team тренинг дууссан)

---

## 3. Per-customer migration процесс

### Step 0: Pre-flight (1 өдөр)

**Харилцагчтай communication:**
- Email / phone: "Таны системийг Edge Box-д шилжүүлэх ажил хийгдэх тухай"
- Timeframe зөвшөөрөл авах (ерөнхийдөө ажлын цагаас гадна)
- Downtime target: 0 мин (гэхдээ unexpected issue-д буферлэж 30 мин)

**Дотоод бэлтгэл:**
- Edge box provision (store_id, token, WG config pre-configured)
- Харилцагчийн камер тооллого + RTSP URL санах
- Харилцагчийн дотоод сүлжээ схем (VLAN ID, DHCP range)

### Step 1: Edge deploy (60-90 мин)

```
┌────────────────────────────────────────┐
│ Хоёр ажилтан онсайт:                    │
│ - 1 Infra (hardware + сүлжээ)          │
│ - 1 AI engineer (validation)            │
└────────────────────────────────────────┘

1. Edge box физикийн суулгалт
2. Network wire (isolated VLAN → LAN1, WAN → LAN2)
3. Power on + autoboot
4. Provisioning wizard (store_id, token)
5. WireGuard tunnel верификация
6. Central API reachable check
7. Камер RTSP stream-ийг edge дээр validate
```

### Step 2: Dual-run (24-72 цаг)

Энэ үед **Central болон Edge хоёулаа** event-ийг process хийнэ.

**Central config:**
- RTSP stream as-is (харилцагчийн router-аас ingress continue)
- Inference continue, alert Telegram илгээнэ

**Edge config:**
- RTSP stream LAN-аас subscribe
- Inference run
- Alert-уудыг DB-д хадгал, **Telegram илгээхгүй** (shadow mode)

**Validation metric:**
- Event ID count: central vs edge
- Alert match rate: ≥ 95%
- Latency comparison

### Step 3: Cut-over (15 мин)

**Харилцагчтай товлосон цагтаа:**
1. Telegram notifications switch: central OFF, edge ON
2. Harilцагчийн CCTV camera stream → LAN mode only (central-ээс disconnect)
3. Central-ийн inference pipeline disable for this store
4. Edge primary status confirmed in dashboard

### Step 4: Monitoring (14 хоног)

- Daily check-in with customer (эхний 3 хоног хамт ажиллана)
- Edge metrics Grafana-д хянана
- Харилцагчийн feedback (alert quality) асууна
- Any issue → immediate response

### Step 5: Retire (migration complete)

- Central-ээс тухайн store-ийн inference config archive
- Billing switches to edge tier
- Harilцагчид completion email

---

## 4. Rollback plan

### Rollback trigger conditions:
- Edge alert latency > 10s (sustained)
- False positive rate > 50%
- Edge box repeated crashes (> 3/day)
- Харилцагч unhappy with accuracy

### Rollback steps:
1. Edge инференс disable
2. Central inference re-enable for store
3. RTSP stream central-д redirect
4. Telegram routing central-д буцаана
5. Incident postmortem хийнэ

**Rollback SLA: < 15 мин** (central config ready to accept, disabled only).

---

## 5. Data migration

### Events & alerts history

- Central PostgreSQL → бүх event history хадгалагдана
- Edge local SQLite → зөвхөн 7 хоногийн local cache
- Миграци хийх өгөгдөл **байхгүй** — schema-level дизайн нь history-г
  central-д хадгалдаг

### Per-store config (weights, thresholds)

```
Central DB                   Edge sync-pack
├─ store_weights table       ├─ weights.json
├─ detection_config          ├─ detection_config.yaml
└─ feedback labels           └─ qdrant_snapshot.bin
                                (labeled cases)
```

**Migration script:**

```python
# scripts/migrate_store_to_edge.py

def generate_edge_sync_pack(store_id: UUID) -> Path:
    weights = get_store_weights(store_id)
    config = get_detection_config(store_id)
    cases = get_labeled_cases(store_id)

    # Build Qdrant snapshot
    snapshot = qdrant_client.create_snapshot(
        collection_name=f"store_{store_id}_cases"
    )

    # Pack
    pack_dir = Path(f"/tmp/sync_pack_{store_id}")
    pack_dir.mkdir(parents=True)

    (pack_dir / "weights.json").write_text(json.dumps(weights))
    (pack_dir / "detection_config.yaml").write_text(yaml.dump(config))
    shutil.copy(snapshot.path, pack_dir / "qdrant_snapshot.bin")

    # Manifest + signature
    manifest = {
        "store_id": str(store_id),
        "version": "1.0.0",
        "created_at": datetime.utcnow().isoformat(),
        "files": list(pack_dir.iterdir()),
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest))

    # Sign
    signature = hmac_sign(manifest, SYNC_SECRET)
    (pack_dir / "signature.sig").write_text(signature)

    # Archive
    archive_path = Path(f"/var/lib/chipmo/sync_packs/{store_id}.tar.gz")
    shutil.make_archive(archive_path.with_suffix(""), "gztar", pack_dir)

    return archive_path
```

---

## 6. Schedule / wave plan

### Wave 1 — Pilot migration (1 долоо хоног)
- 1 харилцагч (хамгийн идэвхтэй, захирлаас дэмжлэгтэй)
- Dual-run 72 цаг
- Full postmortem, lessons learned documented

### Wave 2 — Early adopters (2 долоо хоног)
- 2-3 харилцагч
- Dual-run 48 цаг тус бүр
- Iterate on install process

### Wave 3 — Rolling migration (1-2 сар)
- Үлдэх харилцагчдыг 2/долоо хоногт шилжүүлнэ
- Install process refined, 60 мин даалагдана
- Dual-run 24 цаг стандарт

### Wave 4 — Central retirement (зорилго)
- Бүх харилцагч migrated
- Central pipeline inference container disable
- Central зөвхөн Qdrant central + management + sync хадгалана
- GPU-ийг RTX 5090 → sync compute + VLM-д зориулна

---

## 7. Хүний нөөцийн план

| Үүрэг | Хамрагдах долоо хоног | Ажил |
|---|---|---|
| Infra engineer | Бүх 4 wave | Edge провиcion, сүлжээ |
| AI engineer | Wave 1-3 | Validation, accuracy check |
| Full-stack | Бүх wave | Dashboard, customer UI |
| Support | Wave 3-4 | Customer onboarding |
| Product/Founder | Wave 1-2 | Decision making, customer rel |

---

## 8. Risk + Mitigation (migration-specific)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Edge box hardware DOA | Low | Medium | Spare box on-site (3+) |
| Harilцагчийн camera firmware change | Low | High | Pre-flight check, firmware freeze agreement |
| RTSP auth changed на клиента | Med | Medium | Auth config migration script |
| Clock skew between edge-central | Low | High | NTP enforced, monitoring |
| Edge GPU driver incompatibility | Low | High | Standardized OS image |
| Internet outage in харилцагч (ongoing) | Med | Med | Offline-first local mode |

---

## 9. Communication план

### Харилцагчийн имэйл (template)

```
Субъект: Chipmo Security AI — таны системийн upgrade

Сайн байна уу [Харилцагч],

Таны Chipmo Security AI системийг илүү найдвартай, хурдтай болгох
зорилгоор шинэ Edge Box архитектурт шилжүүлнэ.

Давуу талууд:
- Alert хариу өгөх хурд 3x сайжирна
- Интернет тасарсан ч система ажиллана
- Таны видео хувийн нууц байдлаар хамгаалагдана

Хугацаа: [огноо]
Downtime: 0-15 мин
Онсайт хугацаа: ~90 мин

Та 2 мянга₮/сарын гэрээнд өөрчлөлт орохгүй.

Асуулт байвал [support email / phone].

Хүндэтгэсэн,
Chipmo team
```

### Migration хийсний дараа (daily 3-day checkin)

```
"Өнөөдөр систем хэвийн уу? 🙂 Асуудал гарвал даруй мэдэгдээрэй."
```

---

## 10. Success criteria

Migration дуусгавартай гэж хэзээ гэвэл:

- [ ] Бүх харилцагч edge-д шилжсэн (> 95%)
- [ ] Migration-ын дараа false positive rate шилжилт-өмнөх рейт-ээс доогуур
- [ ] Харилцагчийн NPS migration-ын дараа > 40
- [ ] Central server GPU load шилжилт-өмнөх рейт-ийн 30%-аас доогуур
- [ ] Edge box uptime average > 99.5%
- [ ] Unplanned rollback < 5% of migrations

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [02-ROADMAP.md](./02-ROADMAP.md)
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md)

---

Updated: 2026-04-17
