# 07 — Schema Migration Lock

Энэ document нь current production-compatible integer schema-аас future
hybrid edge/RAG/VLM schema руу шилжих **lock decision** юм. T02 phase-ийн DB
migration бүр энэ contract-г дагана.

Updated: 2026-04-20

---

## 1. Locked Decisions

| Decision | Lock |
|---|---|
| Core table primary keys | `organizations`, `users`, `stores`, `cameras`, `alerts` integer PK хэвээр |
| Alert table name | Current `alerts` table-г rename хийхгүй |
| Future `alert_events` нэр | Одоогоор хэрэглэхгүй; docs/API дээр `alerts` хэвээр |
| Migration style | Backward-compatible, additive, idempotent where practical |
| Deploy style | Expand → backfill → dual-read/write → contract |
| Destructive changes | T02 phase-д байхгүй |
| UUID usage | New standalone entities may use UUID own `id`, but FK to current core tables remains `INTEGER` |
| TimescaleDB | Optional/spike-gated; normal PostgreSQL migration first |
| Tenant isolation | Every new query/table must carry `store_id` or `organization_id` where applicable |

---

## 2. Current Schema Baseline

Source of truth:

- Models: `shoplift_detector/app/db/models/`
- Current migrations: `alembic/versions/`
- Inventory: `docs/00-AS-IS-INVENTORY.md`

Current core schema uses integer IDs:

| Table | PK | Notes |
|---|---|---|
| `organizations` | integer `id` | Tenant root |
| `users` | integer `id` | `organization_id` integer FK |
| `stores` | integer `id` | `organization_id` integer FK |
| `cameras` | integer `id` | `store_id`, `organization_id` integer FK |
| `alerts` | integer `id` | `store_id`, `camera_id`, `person_id` integer fields |
| `alert_feedback` | integer `id` | `alert_id` integer FK |
| `model_versions` | integer `id` | `store_id` integer FK |
| `alert_state` | integer `id` | Added in Phase 1; `(camera_id, person_track_id)` state |
| `camera_health` | integer `camera_id` PK/FK | Added in Phase 1; runtime camera heartbeat |

Current migration chain:

```text
20260414_01
  -> 20260416_01
  -> 20260420_01  (alert_state)
  -> 20260420_02  (camera_health)
```

---

## 3. Compatibility Rules

1. Do not rename `alerts`.
2. Do not change current integer PK types in place.
3. Do not rewrite existing API response IDs from integer to UUID.
4. Add nullable columns first; make them required only after app write path is live and backfilled.
5. Add indexes concurrently where production DB size requires it.
6. New tables that reference current core entities must use integer FK columns:
   - `store_id INTEGER REFERENCES stores(id)`
   - `camera_id INTEGER REFERENCES cameras(id)`
   - `alert_id INTEGER/BIGINT REFERENCES alerts(id)`
   - `user_id INTEGER REFERENCES users(id)`
7. New standalone tables may have UUID primary keys:
   - `edge_boxes.id UUID`
   - `cases.id UUID`
   - `sync_packs.id UUID`
8. If an external/edge UUID is needed for a current integer entity, add a sidecar column such as `external_id UUID UNIQUE`; do not replace `id`.
9. Every migration must have a rollback-safe downgrade for newly added objects. Data-preserving downgrades are preferred.
10. App code must tolerate missing new columns during rolling deploy when practical by using column discovery or nullable reads.

---

## 4. Target Tables And ID Plan

| Task | Table / change | Own ID | FK compatibility |
|---|---|---|---|
| T02-02 | `edge_boxes` | UUID | `store_id INTEGER` |
| T02-03 | `cases` | UUID | `alert_id INTEGER/BIGINT`, `store_id INTEGER`, `camera_id INTEGER`, `labeled_by INTEGER` |
| T02-04 | `sync_packs` | UUID | `store_id INTEGER`, `edge_box_id UUID` |
| T02-05 | `inference_metrics` | Composite | `camera_id INTEGER`, optional `edge_box_id UUID` |
| T02-06 | `audit_log` | BIGSERIAL | `user_id INTEGER`, resource IDs split by resource type |
| T02-07 | TimescaleDB setup | N/A | Optional extension, no app dependency until verified |
| T01-08/T02 later | store settings | Current `stores.id` | Add `stores.settings JSONB` or `store_settings.store_id INTEGER` |

Important correction for future specs:

- Qdrant payloads may use UUID for `case_id`, but `store_id` and `camera_id`
  in payload should mirror current integer IDs unless a later explicit
  external-ID mapping is introduced.
- `resource_id UUID` in target `audit_log` is too narrow for current integer
  resources. Use `resource_id_text TEXT` or `resource_int_id BIGINT` plus
  optional `resource_uuid UUID`.

---

## 5. Expand → Backfill → Dual-Read/Write → Contract

### Phase A — Expand

Add tables/nullable columns without changing existing code behavior.

Examples:

```sql
CREATE TABLE edge_boxes (...);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS edge_box_id UUID;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS person_track_id INTEGER;
```

Acceptance:

- Existing tests pass.
- Existing endpoints keep the same response shape.
- New tables can be empty.

### Phase B — Backfill

Populate new columns from existing data where possible.

Examples:

```sql
UPDATE alerts
SET person_track_id = person_id
WHERE person_track_id IS NULL;
```

Acceptance:

- Backfill is idempotent.
- Large updates are chunked if production row count is high.

### Phase C — Dual-Read/Write

App writes both old and new fields/tables while reads still prefer old schema
or support both.

Examples:

- Alert pipeline writes `alerts.camera_id` and `alerts.edge_box_id` when edge
  source exists.
- Label flow writes `alert_feedback` and later `cases.label`.

Acceptance:

- Old UI/API works.
- New tables receive data.
- Rollback app can ignore new data.

### Phase D — Contract

After one production release has validated dual-write, code may prefer new
tables for new features. Current integer IDs still remain public unless a
separate API version migration is approved.

---

## 6. Locked Migration Order

The next migrations should be created in this order. Existing Phase 1
migrations are already present and must stay before these.

```text
20260414_01_align_railway_schema.py
20260416_01_add_telegram_chat_id_to_stores.py
20260420_01_add_alert_state.py
20260420_02_add_camera_health.py

Next:
20260420_03_add_cases.py
20260420_04_add_edge_boxes.py
20260420_05_add_sync_packs.py
20260420_06_add_inference_metrics.py
20260420_07_add_audit_log.py
20260420_08_timescaledb_spike_or_setup.py
20260420_09_enhance_store_settings.py
```

TimescaleDB remains after normal table creation unless T02-07 confirms Railway
and local deployment support. If TimescaleDB is unavailable, metrics tables
must still work as normal PostgreSQL tables.

---

## 7. Table-Specific Locks

### `edge_boxes`

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `store_id INTEGER NOT NULL REFERENCES stores(id)`
- `status` constrained to provisioning/active/degraded/offline/retired
- No dependency on camera rows; one store may have multiple edge boxes.

### `cases`

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `alert_id INTEGER/BIGINT REFERENCES alerts(id)` nullable for cases created
  before alert promotion.
- `store_id INTEGER NOT NULL`, `camera_id INTEGER` nullable only if source is
  unknown.
- Label fields must not replace `alert_feedback` until dual-write is validated.

### `sync_packs`

- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `store_id INTEGER NOT NULL`
- `edge_box_id UUID NULL`
- `version`, `status`, `signature`, `s3_path` are additive and safe to deploy
  before sync APIs exist.

### `inference_metrics`

- Normal PostgreSQL table first.
- Suggested PK: `(camera_id, timestamp)` or synthetic `BIGSERIAL id` plus
  `(camera_id, timestamp)` index.
- Add Timescale hypertable only after T02-07.

### `audit_log`

- `id BIGSERIAL PRIMARY KEY`
- `user_id INTEGER REFERENCES users(id)`
- Avoid UUID-only `resource_id`; use polymorphic-safe resource reference:
  `resource_type VARCHAR(32)`, `resource_int_id BIGINT NULL`,
  `resource_uuid UUID NULL`, `resource_key TEXT NULL`.

### `alerts` additions

Allowed additive columns:

- `edge_box_id UUID NULL REFERENCES edge_boxes(id)`
- `suppressed BOOLEAN DEFAULT FALSE`
- `suppressed_reason TEXT`
- `rag_decision VARCHAR(32)`
- `vlm_decision VARCHAR(32)`
- `person_track_id INTEGER`

Do not drop or rename:

- `person_id`
- `image_path`
- `video_path`
- `feedback_status`
- `reviewed`

---

## 8. Verification Checklist For Each Schema Task

Every T02 schema task must include:

- Alembic migration under `alembic/versions/`
- SQLAlchemy model under `shoplift_detector/app/db/models/` where app code will use it
- Repository or service read/write path if the task acceptance requires behavior
- Focused tests for repository/model behavior
- `docs/06-DATABASE-SCHEMA.md` update if target schema changed
- `docs/TASKS.md` status update
- `python3.12 -m ruff check .`
- `python3.12 -m pytest -q`

Deployment note:

- Do not run `alembic upgrade head` against Railway until the code containing
  the migration files is deployed or the user explicitly approves that flow.
- GitHub push requires explicit user approval.

---

## 9. Open Decisions

These are not locked by T02-01 and need separate decisions/tasks:

| Decision | Owner task |
|---|---|
| TimescaleDB availability on Railway/local | T02-07 |
| `stores.settings JSONB` vs `store_settings` table | T01-08 / T02 follow-up |
| Whether public API ever exposes UUID IDs for core resources | Future API versioning task |
| Object storage lifecycle policy for S3/Cloudinary | Future storage retention task |
| RLS vs app-level tenant filter enforcement | T02-13 |
