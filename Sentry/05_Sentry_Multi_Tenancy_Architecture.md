# Sentry — Multi-Tenancy Architecture
## SaaS Tenant Isolation, Quotas, Billing Data Flow

**Баримтын дугаар:** DOC-05
**Хувилбар:** 1.0
**Огноо:** 2026-04-22
**Эзэмшигч:** Lil
**Холбоотой:** `01_Sentry_PRD_v1.1.md` (FR-11), `02_Sentry_Architecture_v3.0.html`

---

## 1. Tenancy Model — Shared Multi-Tenant

Sentry нь **multi-tenant shared infrastructure** загвар ашиглана:
- Бүх Standard/Pro plan tenant нь нэг GPU pool, DB, server-ийг хуваалцана
- Enterprise plan (Phase 3) нь dedicated GPU + isolated DB schema авна
- **Tenant isolation:** every query/operation нь `tenant_id` namespace-ээр шүүгдэнэ

```
┌──────────────────────────────────────────────────────┐
│              Sentry SaaS Server (Shared)             │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Tenant A │  │ Tenant B │  │ Tenant C │  ...      │
│  │ (Pro)    │  │ (Starter)│  │ (Pro)    │           │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        │             │             │                 │
│        └──────┬──────┴──────┬──────┘                 │
│               │             │                        │
│        ┌──────▼─────┐ ┌─────▼──────┐                │
│        │ GPU Pool   │ │ Shared DB  │                │
│        │ (8 tenants)│ │ (per-row   │                │
│        │            │ │  tenant_id)│                │
│        └────────────┘ └────────────┘                │
└──────────────────────────────────────────────────────┘
```

---

## 2. Tenant Identity Model

### 2.1 Tenant entity
```sql
CREATE TABLE tenants (
  tenant_id        UUID PRIMARY KEY,
  legal_name       TEXT NOT NULL,
  display_name     TEXT NOT NULL,
  email            TEXT UNIQUE NOT NULL,
  phone            TEXT,
  status           TEXT NOT NULL,  -- pending, active, suspended, churned
  plan             TEXT NOT NULL,  -- starter, pro, enterprise, trial
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  trial_ends_at    TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  payment_method_id TEXT,           -- Stripe / QPay token
  api_key_hash     TEXT NOT NULL,
  resource_quota   JSONB NOT NULL  -- {max_cameras, max_stores, max_gpu_seconds}
);
```

### 2.2 Per-tenant API key
- Format: `sk_live_<32-byte-base64>`
- One-way SHA-256 hashed in DB
- Embedded in Docker installer at download time
- Rotatable via customer portal
- All API requests must include `Authorization: Bearer sk_live_...`

### 2.3 Tenant scoping helper
Бүх FastAPI endpoint dependency:
```python
async def get_current_tenant(
    api_key: str = Depends(api_key_header)
) -> Tenant:
    tenant = await db.tenants.find_by_api_key_hash(hash(api_key))
    if not tenant or tenant.status != 'active':
        raise HTTPException(401)
    return tenant
```

---

## 3. Data Isolation Strategy

### 3.1 Row-level isolation (бүх table-д)

**ALL** table-д `tenant_id` column байх ёстой:

```sql
CREATE TABLE events (
  event_id    UUID PRIMARY KEY,
  tenant_id   UUID NOT NULL REFERENCES tenants(tenant_id),
  store_id    UUID NOT NULL,
  ...
);

CREATE INDEX idx_events_tenant ON events(tenant_id);

-- PostgreSQL Row Level Security
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON events
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

### 3.2 Application-level enforcement

```python
# Бүр query тенант-ээр шүүгдэнэ
async def get_events(tenant: Tenant, filters: dict):
    return await db.events.find(
        tenant_id=tenant.tenant_id,  # ENFORCED
        **filters
    )

# Bad pattern — НИКОГДА
# events = await db.events.find_all()  # ❌ leaks all tenants!
```

### 3.3 Redis namespace isolation

```python
# Person state keys
key = f"tenant:{tenant_id}:store:{store_id}:person:{person_id}"
# жишээ: tenant:abc-123:store:store-42:person:P-247

# Camera state
key = f"tenant:{tenant_id}:camera:{camera_id}:state"
```

### 3.4 Qdrant collection per tenant
```python
# Re-ID embedding collection
collection_name = f"reid_tenant_{tenant_id.replace('-', '_')}"
```
**Benefit:** Tenant delete = drop entire collection, full data wipe.

### 3.5 MinIO bucket isolation
```
sentry-clips/
├── tenant_abc123/
│   ├── store_42/
│   │   └── 2026-04-22/event_xyz.mp4
└── tenant_def456/
    └── store_99/
        └── 2026-04-22/event_pqr.mp4
```

Per-tenant IAM policy.

---

## 4. Resource Quotas (Per-Tenant)

### 4.1 Quota definition
```json
{
  "max_cameras": 12,
  "max_stores": 1,
  "max_gpu_seconds_per_day": 86400,  // 1 GPU full day
  "max_storage_gb": 50,
  "max_api_calls_per_minute": 60,
  "max_webhooks_per_hour": 1000
}
```

Plan-based defaults:

| Quota | Starter | Pro | Enterprise |
|---|---|---|---|
| max_cameras | 5 | 50 | unlimited |
| max_stores | 1 | 10 | unlimited |
| max_gpu_seconds_per_day | 21,600 (6h) | 86,400 (24h) | unlimited |
| max_storage_gb | 10 | 100 | 1,000+ |
| max_api_calls_per_minute | 30 | 60 | 600 |

### 4.2 Enforcement points

**Камер нэмэх үед:**
```python
async def add_camera(tenant: Tenant, camera_data: dict):
    current_count = await db.cameras.count(tenant_id=tenant.tenant_id)
    if current_count >= tenant.resource_quota['max_cameras']:
        raise HTTPException(403, "Camera limit reached. Upgrade plan.")
    return await db.cameras.create(...)
```

**GPU inference queue:**
- Token bucket per tenant
- Pro plan: 5 concurrent inference slots
- Starter: 2 concurrent slots
- Enterprise: unlimited (dedicated GPU)

**Storage cleanup:**
- Daily cron: tenant_storage > quota → delete oldest events first

### 4.3 Soft limits & overage

- Quota exceeded → email warning at 80%, 100%
- Hard block at 110% (с upgrade plan CTA)
- Overage billing: Pro plan нь auto-bill camera over limit ($)

---

## 5. Noisy Neighbor Protection

### 5.1 GPU queue priority
```python
# Priority queue for inference jobs
class InferenceJob:
    tenant_id: UUID
    plan_tier: str  # 'starter', 'pro', 'enterprise'
    priority: int   # 0=highest

    @property
    def priority(self):
        return {
            'enterprise': 0,
            'pro': 1,
            'starter': 2,
            'trial': 3
        }[self.plan_tier]
```

### 5.2 Per-tenant rate limiting

Token bucket (Redis-based):
```python
async def check_rate_limit(tenant_id, action='api_call'):
    key = f"ratelimit:{tenant_id}:{action}:{minute_bucket()}"
    count = await redis.incr(key)
    await redis.expire(key, 60)
    if count > tenant.quota['max_api_calls_per_minute']:
        raise HTTPException(429, "Rate limit exceeded")
```

### 5.3 Detection circuit breaker

- Tenant нь 5 минутын дотор 1000+ alert үүсгэвэл → throttle
- Possible bug detected → notify ops team + auto-pause tenant

---

## 6. Billing Data Flow

### 6.1 Event → Usage → Invoice

```
┌──────────┐    ┌────────────┐    ┌────────────┐    ┌──────────┐
│ Tenant   │───>│ Usage      │───>│ Aggregator │───>│ Stripe / │
│ activity │    │ events     │    │ (daily)    │    │ QPay     │
│ (cameras,│    │ (Postgres) │    │            │    │ invoice  │
│  GPU sec)│    └────────────┘    └────────────┘    └──────────┘
└──────────┘
```

### 6.2 Usage event types

```sql
CREATE TABLE usage_events (
  event_id     BIGSERIAL PRIMARY KEY,
  tenant_id    UUID NOT NULL,
  metric       TEXT NOT NULL,  -- camera_active, gpu_seconds, storage_gb, api_call
  value        NUMERIC NOT NULL,
  recorded_at  TIMESTAMPTZ NOT NULL,
  store_id     UUID
);
```

**Жишээ:**
```
{tenant: A, metric: camera_active, value: 12, time: 2026-04-22}
{tenant: A, metric: gpu_seconds, value: 3600, time: 2026-04-22T15:00}
{tenant: A, metric: storage_gb, value: 23.5, time: 2026-04-22}
```

### 6.3 Daily aggregation (cron)
```python
# Cron @ 02:00 daily
async def aggregate_daily_usage():
    for tenant in active_tenants:
        camera_count = max(daily_camera_active_count(tenant))
        gpu_seconds = sum(daily_gpu_usage(tenant))
        storage = current_storage(tenant)
        await db.daily_usage.insert(
            tenant_id=tenant.tenant_id,
            date=yesterday,
            cameras=camera_count,
            gpu_seconds=gpu_seconds,
            storage_gb=storage
        )
```

### 6.4 Monthly billing cycle

1. Day 1 of month: calculate previous month subscription
2. Base = platform_fee + (camera_count × per_camera_rate)
3. Overage check (если ardenuun камер count surpassed plan quota)
4. Generate invoice (PDF, Mongolian + English)
5. Charge payment method:
   - QPay: send invoice URL via SMS/email (manual confirm)
   - Stripe: auto-charge saved card
6. Failed → retry day 3, 7, 14 → suspend if all fail

### 6.5 Invoice template
```
─────────────────────────────────────────
ИНВОЙС / INVOICE                    #2026-04-001
─────────────────────────────────────────
Sentry Technologies LLC
ҮТД: 5012345678
─────────────────────────────────────────
Харилцагч: Номин Супермаркет (Сансар)
Хугацаа:   2026-04-01 ~ 2026-04-30

Платформын төлбөр:           ₮29,000
Камер (12 ширхэг × ₮17,000): ₮204,000
─────────────────────────────────────────
Дэд дүн:                     ₮233,000
НӨАТ (10%):                  ₮23,300
─────────────────────────────────────────
НИЙТ ТӨЛБӨР:                 ₮256,300
─────────────────────────────────────────
Төлбөр хийх: 2026-05-05 хүртэл
QPay: [QR code]
Гүйлгээ: Голомт Банк, 1000-1234-5678
```

---

## 7. Tenant Lifecycle

### 7.1 States
```
   [pending]──pay──>[active]──30d_unpaid──>[suspended]
                       │                        │
                       │                        ├──reactivate──>[active]
                       │                        │
                       └──cancel──>[grace]<─────┘
                                      │
                                90d_after
                                      ↓
                                [churned]
                                      │
                                      └──data_purge──>[deleted]
```

### 7.2 Suspension behavior
- API access blocked (401)
- Live monitoring blocked
- Data retained 30 days
- Email reminder series
- Reactivation = pay outstanding balance

### 7.3 Data deletion (90-day grace)
- Customer cancel → status = grace
- 90 days: dashboard read-only, can export data
- After 90 days:
  ```python
  await delete_qdrant_collection(f"reid_tenant_{tenant_id}")
  await delete_minio_prefix(f"tenant_{tenant_id}/")
  await db.execute("DELETE FROM events WHERE tenant_id = $1", tenant_id)
  await db.execute("DELETE FROM cameras WHERE tenant_id = $1", tenant_id)
  await db.execute("UPDATE tenants SET status='deleted', api_key_hash=NULL WHERE tenant_id = $1", tenant_id)
  ```

### 7.4 Right to be forgotten (GDPR-style)
- Customer request → email to privacy@sentry.mn
- 30-day SLA for full data wipe
- Confirmation email with audit log

---

## 8. Audit & Compliance

### 8.1 Tenant action audit log
```sql
CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  tenant_id   UUID NOT NULL,
  user_id     UUID,
  action      TEXT NOT NULL,  -- 'login', 'plan_change', 'data_export', ...
  resource    TEXT,
  metadata    JSONB,
  ip_address  INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Customer-д portal-аар харах эрх (`/settings/audit-log`).

### 8.2 Cross-tenant query forbidden
Engineering rule:
> ❌ ANY query that doesn't filter by `tenant_id` requires explicit security review.

Linter rule (custom Python script): grep all `db.execute` calls and check for `tenant_id` in WHERE clause.

### 8.3 Penetration test scenarios
- IDOR (Insecure Direct Object Reference): tenant A trying to access tenant B's events
- API key brute force
- SQL injection via tenant input fields
- Subdomain takeover (per-tenant subdomain like `acme.sentry.mn`)

---

## 9. Architecture diagram (textual)

```
┌─────────────────────────────────────────────────────────────┐
│                     Internet (TLS 1.3)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌─────────────────────────────────┐
        │   API Gateway (FastAPI)         │
        │   - JWT/API key auth            │
        │   - Tenant ID extraction        │
        │   - Rate limiting per tenant    │
        └─────────┬───────────────────────┘
                  │
       ┌──────────┼──────────┬──────────────┐
       ▼          ▼          ▼              ▼
   ┌────────┐ ┌────────┐ ┌────────┐    ┌──────────┐
   │ Stream │ │ Detect │ │ Re-ID  │    │ Billing  │
   │ Worker │ │ Worker │ │ Worker │    │ Service  │
   │ (per   │ │ (GPU   │ │ (GPU   │    │          │
   │  tenant│ │  pool) │ │  pool) │    └────┬─────┘
   │  conn) │ └───┬────┘ └───┬────┘         │
   └───┬────┘     │          │              │
       │          └────┬─────┘              │
       │               │                    │
       ▼               ▼                    ▼
   ┌────────────────────────────────────────────────┐
   │  Storage Layer (per-tenant isolation)          │
   │                                                │
   │  Redis (key: tenant:X:...)                     │
   │  PostgreSQL (RLS + tenant_id column)           │
   │  Qdrant (collection: reid_tenant_X)            │
   │  MinIO (bucket prefix: tenant_X/)              │
   └────────────────────────────────────────────────┘
```

---

## 10. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| **Tenant data leak via missing WHERE filter** | RLS enforcement, code review checklist, query linter |
| **Noisy tenant exhausting GPU** | Quota + priority queue + circuit breaker |
| **Accidental cross-tenant join** | Foreign keys scoped to tenant, no global FKs |
| **API key leak** | Hashed storage, rotation, IP allowlist (Enterprise) |
| **Subdomain takeover** | wildcard DNS validation, no orphan subdomains |
| **Billing overcharge bug** | Reconciliation cron, customer self-service refund request |

---

## 11. Implementation Checklist (Phase 1)

- [ ] Migrate all tables to include `tenant_id` column
- [ ] Enable PostgreSQL RLS on all tenant-scoped tables
- [ ] Create `get_current_tenant` FastAPI dependency
- [ ] Implement per-tenant API key generation + rotation
- [ ] Redis key namespacing (helper class)
- [ ] Qdrant per-tenant collection management
- [ ] MinIO bucket policy per tenant
- [ ] Quota enforcement at API + worker level
- [ ] Usage event tracking + daily aggregation cron
- [ ] Billing service (QPay + Stripe webhooks)
- [ ] Invoice generation (PDF, Mongolian template)
- [ ] Audit log table + customer portal viewer
- [ ] Tenant lifecycle automation (suspension, deletion)
- [ ] Linter rule: forbid `db.execute` without tenant_id filter
- [ ] Security review checklist for each PR

---

## 12. Холбогдох баримтууд

- `01_Sentry_PRD_v1.1.md` — FR-11, FR-13, FR-14
- `02_Sentry_Architecture_v3.0.html` — System diagram
- `03_Sentry_Pricing_Business_Model.md` — Plan tier definition
- `04_Sentry_Onboarding_Flow.md` — Tenant creation flow
