# Chipmo Security Camera AI — Хөгжүүлэлтийн бичиг баримт

Энэ фолдер нь **Chipmo Security Camera AI** системийн хөгжүүлэлтийн
техникийн бичиг баримтуудыг агуулна. Одоогийн систем (FastAPI + YOLO11-pose +
rule-based behavior detection)-ийг дараагийн түвшинд (Hybrid edge + RAG + VLM +
auto-learning) хөгжүүлэх төлөвлөгөөг агуулсан.

## Бичиг баримтын жагсаалт

| № | Файл | Агуулга |
|---|---|---|
| 00 | [AS-IS-INVENTORY.md](./00-AS-IS-INVENTORY.md) | Одоогийн repo-ийн endpoint, table, service, env, deploy inventory |
| 01 | [ARCHITECTURE.md](./01-ARCHITECTURE.md) | Одоогийн болон эцсийн архитектурын харьцуулалт |
| 02 | [ROADMAP.md](./02-ROADMAP.md) | 4 үе шаттай хөгжүүлэлтийн roadmap |
| 03 | [TECH-SPECS.md](./03-TECH-SPECS.md) | Шинэ feature бүрийн техникийн нарийвчилсан тодорхойлолт |
| 04 | [EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md) | Edge box архитектур, hardware BOM, суулгалт |
| 05 | [MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md) | Centralized → Hybrid edge-д шилжих алхам-алхмын план |
| 06 | [DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md) | DB schema-ийн өөрчлөлт, шинэ хүснэгтүүд |
| 07 | [SCHEMA-MIGRATION-LOCK.md](./07-SCHEMA-MIGRATION-LOCK.md) | Current integer schema → future schema backward-compatible lock |

## Уншлагын дараалал

**Шинэ гишүүн код хийж эхэлж байгаа бол:**
1. `00-AS-IS-INVENTORY.md` — одоогийн бодит repo state
2. `01-ARCHITECTURE.md` — системийн ерөнхий бүтэц
3. `02-ROADMAP.md` — яг одоо юу хийж байгаа
4. `03-TECH-SPECS.md` — өөрийн хариуцсан хэсэгтэй холбоотой section

**DevOps / Infrastructure engineer:**
1. `04-EDGE-DEPLOYMENT.md`
2. `05-MIGRATION-PLAN.md`
3. `06-DATABASE-SCHEMA.md`

**Product/Business:**
1. `01-ARCHITECTURE.md` (comparison table хэсэг)
2. `02-ROADMAP.md`

## Бизнесийн үндсэн зорилт

1. **Self-hosted** — Гадаад API-д төлөхгүй, бүх component локал ажиллана
2. **Self-improving** — Харилцагч нэмэгдэх тусам систем ухаалаг болно
3. **Cost-effective scale** — Нэг GPU-д олон камер (batched inference)
4. **Privacy-first** — Монголын хувийн нууцын хууль дагуу

## Технологийн stack (target)

**Backend:** FastAPI (async), PostgreSQL + TimescaleDB, Redis Streams
**AI/ML:** YOLO11-pose, ByteTrack, OSNet (Re-ID), Qwen2.5-VL (Ollama)
**Vector DB:** Qdrant (self-hosted)
**Edge:** Jetson Orin / RTX 5060 mini PC
**Central GPU:** RTX 5090 (15-25 харилцагчид)
**Frontend:** React 19 + Vite + TailwindCSS v4
**Observability:** Prometheus + Grafana + Loki
**Orchestration:** Docker Compose (edge), Docker Swarm / K3s (central)

## Баримт бичгийн статус

Бүх бичиг баримт 2026-04-17-д бичигдсэн. Архитектур эсвэл технологи
өөрчлөгдөх бүрт холбогдох документыг шинэчлэх шаардлагатай.

Шинэчлэлт хийсэн тохиолдолд:
- Commit message-д `docs:` prefix хэрэглэнэ
- Өөрчлөгдсөн document-ын доод хэсэгт `Updated: YYYY-MM-DD` тэмдэглэ
