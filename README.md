# Chipmo Security Camera AI

**Cloud-hosted shoplift detection SaaS** for retail stores. Ships YOLO11-pose
behavior detection, RAG + VLM verification, and anonymized cross-customer
learning — all without requiring customers to buy or install new cameras
or servers.

> **Архитектур (2026-04-21):** Centralized SaaS default product.
> Харилцагчийн камерууд өөрчлөгдөхгүй; Chipmo-ийн WireGuard VPN
> appliance-аар RTSP sub-stream-ийг төв сервер рүү татаж inference хийнэ.
> No recording by default (≤10s confirmed alert clip only). 3-phase
> infrastructure: Railway → Cloud GPU → Owned GPU (1000+ cameras).
> On-prem SKU available as premium option for data-sovereignty customers.
> See [`docs/decisions/2026-04-21-centralized-saas-no-customer-hardware.md`](./docs/decisions/2026-04-21-centralized-saas-no-customer-hardware.md).

## Quick links

- **Full architecture:** [`docs/01-ARCHITECTURE.md`](./docs/01-ARCHITECTURE.md)
- **Roadmap:** [`docs/02-ROADMAP.md`](./docs/02-ROADMAP.md)
- **Tech specs:** [`docs/03-TECH-SPECS.md`](./docs/03-TECH-SPECS.md)
- **Infra strategy (3-phase):** [`docs/04-INFRASTRUCTURE-STRATEGY.md`](./docs/04-INFRASTRUCTURE-STRATEGY.md)
- **Customer onboarding:** [`docs/05-ONBOARDING-PLAYBOOK.md`](./docs/05-ONBOARDING-PLAYBOOK.md)
- **Privacy + legal:** [`docs/09-PRIVACY-LEGAL.md`](./docs/09-PRIVACY-LEGAL.md)
- **Pricing (internal):** [`docs/10-PRICING-BUSINESS.md`](./docs/10-PRICING-BUSINESS.md)
- **Task board:** [`docs/TASKS.md`](./docs/TASKS.md)
- **All docs index:** [`docs/README.md`](./docs/README.md)

## Technology stack

- **Backend:** FastAPI (async), PostgreSQL + TimescaleDB, Redis Streams
- **AI:** YOLO11-pose, ByteTrack, OSNet Re-ID, Qwen2.5-VL via vLLM
- **Vector DB:** Qdrant (per-tenant isolated + shared behavior taxonomy)
- **Ingress:** WireGuard VPN appliance (GL.iNet or Raspberry Pi)
- **Central GPU:** Phase A cloud serverless → Phase B rented RTX 4090 →
  Phase C owned RTX 5090 / L40S
- **Frontend:** React 19 + Vite + TailwindCSS v4
- **Observability:** Prometheus + Grafana + Loki
- **Orchestration:** Docker Compose → K3s (Phase C)

## Product principles

1. **Hardware-free onboarding** — no camera changes, no customer server.
2. **Self-improving via shared taxonomy** — cross-customer learning
   without exposing any tenant's PII.
3. **Privacy-first** — no recording by default, per-tenant isolation,
   DPIA compliance with Mongolian data protection law.
4. **Cost-effective at scale** — economies of shared GPU increase from
   Phase A to Phase C.

## Repo layout

```
.
├── shoplift_detector/         # Main FastAPI backend
│   └── app/
│       ├── api/               # REST endpoints
│       ├── ai/                # Detection pipeline
│       ├── db/                # SQLAlchemy models
│       └── services/          # Business logic
├── security-web/              # React dashboard
├── alembic/                   # DB migrations
├── observability/             # Prometheus + Grafana config
├── docs/                      # All development documentation
│   ├── decisions/             # ADRs
│   ├── audits/                # Audit reports
│   └── spikes/                # Technical spikes
└── tests/                     # Test suite
```

## Getting started

Development setup instructions: see [`CLAUDE.md`](./CLAUDE.md) and
[`docs/00-AS-IS-INVENTORY.md`](./docs/00-AS-IS-INVENTORY.md).

Production deployment (Phase A, Railway):

```bash
# Push to Railway project chipmo-prod
# Services: api, worker, web, postgres, redis, qdrant, wireguard
```

Onboarding a customer: see [`docs/05-ONBOARDING-PLAYBOOK.md`](./docs/05-ONBOARDING-PLAYBOOK.md).

## Current status

- **Engineering phase 0** (rule-based pilot): shipped
- **Engineering phase 1** (quick wins + VPN onboarding): in progress
- **Infra phase A** (Railway): active

See [`docs/TASKS.md`](./docs/TASKS.md) for detailed task tracking.

---

Updated: 2026-04-21
