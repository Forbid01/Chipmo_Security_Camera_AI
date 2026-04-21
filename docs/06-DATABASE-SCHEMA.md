# 06 — Database Schema

Одоогийн DB schema-д нэмэх шинэ хүснэгтүүд, хувьсалын migration план,
TimescaleDB integration.

---

## 1. Одоогийн schema (repo-verified)

Repo-д одоо байгаа гол хүснэгтүүд (`shoplift_detector/app/db/models/*`):

```
organizations (id, name, created_at, updated_at)
  └─ users (id, organization_id, username, email, hashed_password, role, is_active)
  └─ stores (id, organization_id, name, address, alert_threshold, alert_cooldown, telegram_chat_id)
      └─ cameras (id, store_id, organization_id, name, url, camera_type, is_active, is_ai_enabled)
          └─ alerts (id, person_id, organization_id, store_id, camera_id, event_time,
                     image_path, video_path, description, confidence_score,
                     reviewed, feedback_status)

alert_feedback (id, alert_id, store_id, feedback_type, reviewer_id, notes,
                score_at_alert, behaviors_detected, created_at)
model_versions (id, store_id, version, model_type, learned_threshold,
                learned_score_weights, total_feedback_used, is_active, trained_at)
```

**Нэршлийн дүрэм:** Одоогийн production table нь `alerts`. Зарим target
architecture хэсгүүд өмнө нь `alert_events` гэж нэрлэсэн байсан. Энэ document-д
current-compatible migration-ууд `alerts` дээр ажиллана. Хэрэв ирээдүйд
`alert_events` нэр рүү rename хийх бол тусдаа breaking migration + API compatibility
plan шаардлагатай.

**ID type:** Current repo `organizations`, `users`, `stores`, `cameras`, `alerts`
зэрэг core table-ууд дээр integer primary key ашиглаж байна. Тиймээс ойрын
migration-ууд core table рүү foreign key хийхдээ `INTEGER/BIGINT` ашиглана.
Шинэ standalone table-ийн own `id` нь UUID байж болно.

---

## 2. Шинэ хүснэгтүүд

### 2.1 `edge_boxes`

Edge box бүрийг тусад нь бүртгэнэ.

```sql
CREATE TABLE edge_boxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    serial_number VARCHAR(64) UNIQUE,
    hostname VARCHAR(128),
    token_hash VARCHAR(255) NOT NULL,  -- bcrypt(edge_token)
    wireguard_public_key VARCHAR(255),
    wireguard_ip INET,

    hardware JSONB,  -- {"cpu": "...", "gpu": "RTX 5060", "ram_gb": 32}
    os_version VARCHAR(64),
    chipmo_version VARCHAR(32),

    status VARCHAR(16) NOT NULL DEFAULT 'provisioning',
    -- provisioning, active, degraded, offline, retired

    last_heartbeat_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_edge_boxes_store ON edge_boxes(store_id);
CREATE INDEX idx_edge_boxes_status ON edge_boxes(status) WHERE status != 'retired';
CREATE INDEX idx_edge_boxes_heartbeat ON edge_boxes(last_heartbeat_at DESC);
```

### 2.2 `edge_box_metrics`

TimescaleDB hypertable — edge box-ийн health data.

```sql
CREATE TABLE edge_box_metrics (
    edge_box_id UUID NOT NULL REFERENCES edge_boxes(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    cpu_percent FLOAT,
    ram_used_mb INT,
    disk_used_percent FLOAT,
    gpu_utilization_percent FLOAT,
    gpu_memory_used_mb INT,
    gpu_temp_celsius FLOAT,
    wireguard_connected BOOLEAN,

    PRIMARY KEY (edge_box_id, timestamp)
);

-- TimescaleDB hypertable
SELECT create_hypertable('edge_box_metrics', 'timestamp');

-- Retention: 30 days
SELECT add_retention_policy('edge_box_metrics', INTERVAL '30 days');

-- Compression after 7 days
ALTER TABLE edge_box_metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'edge_box_id'
);
SELECT add_compression_policy('edge_box_metrics', INTERVAL '7 days');
```

### 2.3 `alert_state`

Alert state machine (dedup-д).

```sql
CREATE TABLE alert_state (
    id BIGSERIAL PRIMARY KEY,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    person_track_id INT NOT NULL,
    state VARCHAR(16) NOT NULL,
    -- idle, active, cooldown, resolved

    started_at TIMESTAMPTZ NOT NULL,
    last_trigger_at TIMESTAMPTZ NOT NULL,
    cooldown_expires_at TIMESTAMPTZ,
    alert_id BIGINT REFERENCES alerts(id),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (camera_id, person_track_id, started_at)
);

CREATE INDEX idx_alert_state_camera_active ON alert_state(camera_id, state)
    WHERE state IN ('active', 'cooldown');
CREATE INDEX idx_alert_state_cooldown ON alert_state(cooldown_expires_at)
    WHERE state = 'cooldown';
```

### 2.4 `cases` (RAG case memory reference)

Qdrant-д хадгалсан case-уудын metadata PostgreSQL-д (joinable).

```sql
CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id BIGINT REFERENCES alerts(id) ON DELETE CASCADE,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,

    timestamp TIMESTAMPTZ NOT NULL,

    -- Behavior signals (6 features)
    behavior_scores JSONB NOT NULL,
    -- {"looking_around": 0.3, "item_pickup": 0.8, ...}

    -- Pose sequence reference (S3/local path to serialized keypoints)
    pose_sequence_path VARCHAR(500),

    -- Clip
    clip_path VARCHAR(500),
    keyframe_paths JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 3-5 keyframe path

    -- Label
    label VARCHAR(32),  -- theft, false_positive, not_sure, unlabeled
    label_confidence FLOAT,
    labeled_by INTEGER REFERENCES users(id),
    labeled_at TIMESTAMPTZ,

    -- VLM verdict (if run)
    vlm_is_suspicious BOOLEAN,
    vlm_confidence FLOAT,
    vlm_reason TEXT,
    vlm_run_at TIMESTAMPTZ,

    -- Qdrant reference
    qdrant_point_id UUID UNIQUE,  -- matches Qdrant collection point

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cases_store_time ON cases(store_id, timestamp DESC);
CREATE INDEX idx_cases_label ON cases(store_id, label) WHERE label IS NOT NULL;
CREATE INDEX idx_cases_unlabeled ON cases(store_id, timestamp DESC)
    WHERE label IS NULL OR label = 'unlabeled';
```

### 2.5 `inference_metrics`

Per-camera inference performance (TimescaleDB).

```sql
CREATE TABLE inference_metrics (
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    edge_box_id UUID REFERENCES edge_boxes(id),
    timestamp TIMESTAMPTZ NOT NULL,

    fps FLOAT,
    yolo_latency_ms FLOAT,
    reid_latency_ms FLOAT,
    rag_latency_ms FLOAT,
    vlm_latency_ms FLOAT,
    end_to_end_latency_ms FLOAT,

    PRIMARY KEY (camera_id, timestamp)
);

SELECT create_hypertable('inference_metrics', 'timestamp');
SELECT add_retention_policy('inference_metrics', INTERVAL '30 days');
```

### 2.6 `sync_packs`

Edge-рүү явсан sync pack-уудын тэмдэглэл.

```sql
CREATE TABLE sync_packs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id INTEGER NOT NULL REFERENCES stores(id),
    edge_box_id UUID REFERENCES edge_boxes(id),

    version VARCHAR(32) NOT NULL,  -- semver

    -- Pack contents summary
    weights_hash VARCHAR(64),
    qdrant_snapshot_id VARCHAR(128),
    case_count INT,  -- RAG-д included case тоо

    s3_path VARCHAR(500),
    signature VARCHAR(255),

    status VARCHAR(32) DEFAULT 'pending',
    -- pending, downloaded, applied, failed, rolled_back

    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    applied_by_edge_box_id UUID REFERENCES edge_boxes(id)
);

CREATE INDEX idx_sync_packs_store ON sync_packs(store_id, created_at DESC);
CREATE INDEX idx_sync_packs_edge ON sync_packs(edge_box_id, status);
```

### 2.7 `audit_log`

Compliance-ын audit log.

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(64) NOT NULL,
    -- view_clip, download_clip, label_clip, delete_clip, config_change, ...
    resource_type VARCHAR(32),
    resource_id UUID,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('audit_log', 'timestamp');
SELECT add_retention_policy('audit_log', INTERVAL '1 year');
```

### 2.8 `camera_health`

Camera connectivity monitoring.

```sql
CREATE TABLE camera_health (
    camera_id INTEGER PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    last_seen_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL DEFAULT 'unknown',
    -- online, offline, degraded, unknown
    last_disconnect_at TIMESTAMPTZ,
    disconnect_count_24h INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.9 `store_settings` / `stores.settings` (enhanced)

Одоогийн `stores` table-д `settings` JSONB байхгүй; `alert_threshold`,
`alert_cooldown`, `telegram_chat_id` гэсэн explicit columns байна. Enhanced
settings хийхдээ нэгийг сонгоно:

1. `stores.settings JSONB` column нэмэх
2. эсвэл тусдаа `store_settings` table үүсгэх

Тохиргооны target shape:

```json
{
  "face_blur_enabled": true,
  "clip_retention_normal_h": 48,
  "clip_retention_alert_d": 30,
  "night_mode_enabled": true,
  "night_luminance_threshold": 60,
  "dynamic_fps_enabled": true,
  "fps_idle": 3,
  "fps_active": 15,
  "fps_suspicious": 30,
  "vlm_verification_enabled": true,
  "vlm_confidence_threshold": 0.5,
  "rag_check_enabled": true,
  "rag_fp_threshold": 0.8,
  "alert_cooldown_seconds": 60,
  "timezone": "Asia/Ulaanbaatar",
  "notification_channels": {
    "telegram": {"chat_ids": ["..."]},
    "sms": {"numbers": ["..."]},
    "email": {"addresses": ["..."]}
  }
}
```

---

## 3. `alerts` шинэчлэл

Одоогийн `alerts` table-д шинэ багана нэмнэ:

```sql
ALTER TABLE alerts ADD COLUMN edge_box_id UUID REFERENCES edge_boxes(id);
ALTER TABLE alerts ADD COLUMN suppressed BOOLEAN DEFAULT FALSE;
ALTER TABLE alerts ADD COLUMN suppressed_reason TEXT;
ALTER TABLE alerts ADD COLUMN rag_decision VARCHAR(32);
-- rag_decision: passed, suppressed_by_rag, not_run
ALTER TABLE alerts ADD COLUMN vlm_decision VARCHAR(32);
-- vlm_decision: passed, suppressed_by_vlm, not_run
ALTER TABLE alerts ADD COLUMN person_track_id INT;

CREATE INDEX idx_alerts_suppressed ON alerts(store_id, event_time DESC)
    WHERE suppressed = FALSE;
CREATE INDEX idx_alerts_edge ON alerts(edge_box_id, event_time DESC);
```

Мөн TimescaleDB hypertable болгоно:

```sql
SELECT create_hypertable('alerts', 'event_time', if_not_exists => TRUE);
SELECT add_retention_policy('alerts', INTERVAL '2 years');
```

---

## 4. TimescaleDB setup

### Install

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### Continuous aggregates

Хурдан dashboard-ын чанарт:

```sql
-- False positive rate per store per day
CREATE MATERIALIZED VIEW store_fp_rate_daily
WITH (timescaledb.continuous) AS
SELECT
    store_id,
    time_bucket('1 day', event_time) AS day,
    COUNT(*) FILTER (WHERE feedback_status = 'false_positive') AS false_positives,
    COUNT(*) FILTER (WHERE feedback_status = 'true_positive') AS true_positives,
    COUNT(*) AS total_alerts
FROM alerts
GROUP BY store_id, day;

SELECT add_continuous_aggregate_policy('store_fp_rate_daily',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

---

## 5. Qdrant collections

PostgreSQL-ийн гадна Qdrant vector DB-д collection-ууд:

### `store_{store_id}_cases`

Store-specific case memory (RAG).

```python
VectorParams(
    size=768,  # pose(256) + clip(512), aligned
    distance=Distance.COSINE,
)

# Payload
{
    "case_id": UUID,
    "alert_id": BigInt,
    "camera_id": int,
    "timestamp": ISO8601,
    "label": str,
    "confidence": float,
    "behavior_scores": dict,
}
```

### `store_{store_id}_reid`

Re-ID working memory (2h TTL).

```python
VectorParams(
    size=512,  # OSNet embedding
    distance=Distance.COSINE,
)

# Payload
{
    "person_id": UUID,
    "camera_id": UUID,
    "timestamp": ISO8601,
    "track_id": int,
}
```

### `global_patterns` (federated)

Cross-store anonymized pattern knowledge.

```python
VectorParams(
    size=768,
    distance=Distance.COSINE,
)

# Payload (no PII)
{
    "pattern_id": UUID,
    "source_store_count": int,  # хэдэн дэлгүүрээс aggregate
    "pattern_type": str,  # "shoplifting_generic", "distraction_theft", etc.
    "confidence": float,
}
```

---

## 6. Alembic migrations дараалал

Migration lock: [07-SCHEMA-MIGRATION-LOCK.md](./07-SCHEMA-MIGRATION-LOCK.md).

Одоогийн Phase 1 migration-ууд болон дараагийн хийх migration-уудын locked
дараалал:

```
alembic/versions/
  ├─ 20260414_01_align_railway_schema.py
  ├─ 20260416_01_add_telegram_chat_id_to_stores.py
  ├─ 20260420_01_add_alert_state.py
  ├─ 20260420_02_add_camera_health.py
  ├─ 20260420_03_add_cases.py
  ├─ 20260420_04_add_edge_boxes.py
  ├─ 20260420_05_add_sync_packs.py
  ├─ 20260420_06_add_inference_metrics.py
  ├─ 20260420_07_add_audit_log.py
  ├─ 20260420_08_timescaledb_spike_or_setup.py
  └─ 20260420_09_enhance_store_settings.py
```

T02 phase-ийн дүрэм: core table-уудын integer PK-г өөрчлөхгүй; шинэ table-ууд
current core table рүү FK хийхдээ `INTEGER/BIGINT` хэрэглэнэ; `alerts` table-г
`alert_events` болгон rename хийхгүй.

Ерөнхий migration template:

```python
# alembic/versions/20260420_001_add_edge_boxes.py

"""add edge_boxes table

Revision ID: abc123
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "edge_boxes",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("serial_number", sa.String(64), unique=True),
        # ... (full schema above)
    )
    op.create_index("idx_edge_boxes_store", "edge_boxes", ["store_id"])

def downgrade():
    op.drop_table("edge_boxes")
```

---

## 7. Data retention policy

| Data type | Location | Retention |
|---|---|---|
| alerts (unlabeled) | TimescaleDB | 2 years |
| alerts (labeled) | TimescaleDB | Unlimited |
| edge_box_metrics | TimescaleDB | 30 days (compressed 7d+) |
| inference_metrics | TimescaleDB | 30 days |
| audit_log | TimescaleDB | 1 year |
| Normal clips | S3 / local disk | 48 hours |
| Alert clips | S3 / local disk | 30 days |
| Alert clips (labeled) | S3 / local disk | Unlimited |
| Qdrant case memory | Qdrant | Unlimited (pruned by score) |
| Qdrant Re-ID | Qdrant | 2 hours |

---

## 8. Backup strategy

### Central PostgreSQL
- Daily full dump → S3 / external storage
- WAL archival → continuous (point-in-time recovery)
- Retention: 30 days

### Central Qdrant
- Weekly snapshot → S3
- Retention: 4 weeks

### Edge box local data
- Critical config-г central-д sync хийсэн болохоор edge backup шаардлагагүй
- Local SQLite cache: хэрэгтэй бол restart-аар rebuild

---

## 9. Indexing стратеги

Queryуудыг profile хийн optimize хийх:

**Most common queries:**
1. "List alerts for store in time range" → `(store_id, timestamp DESC)` ✓
2. "Get unlabeled alerts to show in queue" → `(store_id, label IS NULL, timestamp DESC)` ✓
3. "Get active cooldown alerts" → `(state, cooldown_expires_at)` ✓
4. "Get edge health snapshot" → `(edge_box_id, timestamp DESC)` ✓

**Expensive queries avoid:**
- `LIKE '%...'` текст хайх — full-text index хэрэглэ
- Cross-hypertable JOIN without time bucket

---

## 10. Multi-tenant isolation

**Rule:** Бүх query-д `store_id` эсвэл `organization_id` filter заавал орсон байх.

**Implementation:**
- Row-level security (RLS) PostgreSQL
- ORM middleware-д automatic filter
- Query audit: Prometheus log all `SELECT` without `store_id` filter

```sql
-- Example RLS policy
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY alerts_isolation ON alerts
    FOR ALL
    USING (store_id IN (
        SELECT id FROM stores
        WHERE organization_id = current_setting('app.current_org_id')::integer
    ));
```

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [03-TECH-SPECS.md](./03-TECH-SPECS.md)
- [05-MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md)

---

Updated: 2026-04-20
