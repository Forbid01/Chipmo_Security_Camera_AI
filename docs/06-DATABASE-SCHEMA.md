# 06 — Database Schema

Одоогийн DB schema-д нэмэх шинэ хүснэгтүүд, хувьсалын migration план,
TimescaleDB integration.

---

## 1. Одоогийн schema (assumed)

Repo-д одоо байгаа гол хүснэгтүүд (multi-tenant structure):

```
organizations (id, name, plan, created_at)
  └─ users (id, org_id, email, password_hash, role)
  └─ stores (id, org_id, name, address, settings)
      └─ cameras (id, store_id, name, rtsp_url, status)
          └─ alert_events (id, camera_id, timestamp, score, clip_path, label)

feedback (id, alert_event_id, label, user_id, created_at)
auto_learning_state (store_id, weights, last_trained_at)
```

---

## 2. Шинэ хүснэгтүүд

### 2.1 `edge_boxes`

Edge box бүрийг тусад нь бүртгэнэ.

```sql
CREATE TABLE edge_boxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
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
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    person_track_id INT NOT NULL,
    state VARCHAR(16) NOT NULL,
    -- idle, active, cooldown, resolved

    started_at TIMESTAMPTZ NOT NULL,
    last_trigger_at TIMESTAMPTZ NOT NULL,
    cooldown_expires_at TIMESTAMPTZ,
    alert_event_id BIGINT REFERENCES alert_events(id),

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
    alert_event_id BIGINT REFERENCES alert_events(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,

    timestamp TIMESTAMPTZ NOT NULL,

    -- Behavior signals (6 features)
    behavior_scores JSONB NOT NULL,
    -- {"looking_around": 0.3, "item_pickup": 0.8, ...}

    -- Pose sequence reference (S3/local path to serialized keypoints)
    pose_sequence_path VARCHAR(500),

    -- Clip
    clip_path VARCHAR(500),
    keyframe_paths TEXT[],  -- 3-5 keyframe-ийн S3/local path

    -- Label
    label VARCHAR(32),  -- theft, false_positive, not_sure, unlabeled
    label_confidence FLOAT,
    labeled_by UUID REFERENCES users(id),
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
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
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
    store_id UUID NOT NULL REFERENCES stores(id),
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
    user_id UUID REFERENCES users(id),
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
    camera_id UUID PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    last_seen_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL DEFAULT 'unknown',
    -- online, offline, degraded, unknown
    last_disconnect_at TIMESTAMPTZ,
    disconnect_count_24h INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.9 `store_settings` (enhanced)

Одоогийн `stores.settings` JSONB-д дараах нэмнэ:

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

## 3. `alert_events` шинэчлэл

Одоогийн table-д шинэ багана нэмнэ:

```sql
ALTER TABLE alert_events ADD COLUMN edge_box_id UUID REFERENCES edge_boxes(id);
ALTER TABLE alert_events ADD COLUMN suppressed BOOLEAN DEFAULT FALSE;
ALTER TABLE alert_events ADD COLUMN suppressed_reason TEXT;
ALTER TABLE alert_events ADD COLUMN rag_decision VARCHAR(32);
-- rag_decision: passed, suppressed_by_rag, not_run
ALTER TABLE alert_events ADD COLUMN vlm_decision VARCHAR(32);
-- vlm_decision: passed, suppressed_by_vlm, not_run
ALTER TABLE alert_events ADD COLUMN person_track_id INT;

CREATE INDEX idx_alert_events_suppressed ON alert_events(store_id, timestamp DESC)
    WHERE suppressed = FALSE;
CREATE INDEX idx_alert_events_edge ON alert_events(edge_box_id, timestamp DESC);
```

Мөн TimescaleDB hypertable болгоно:

```sql
SELECT create_hypertable('alert_events', 'timestamp', if_not_exists => TRUE);
SELECT add_retention_policy('alert_events', INTERVAL '2 years');
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
    time_bucket('1 day', timestamp) AS day,
    COUNT(*) FILTER (WHERE label = 'false_positive') AS false_positives,
    COUNT(*) FILTER (WHERE label = 'theft') AS true_positives,
    COUNT(*) AS total_alerts
FROM alert_events
JOIN feedback ON feedback.alert_event_id = alert_events.id
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
    "alert_event_id": BigInt,
    "camera_id": UUID,
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

Хийх migration-уудын дараалал:

```
alembic/versions/
  ├─ 20260420_001_add_edge_boxes.py
  ├─ 20260420_002_add_alert_state.py
  ├─ 20260420_003_add_cases.py
  ├─ 20260420_004_timescaledb_setup.py
  ├─ 20260420_005_hypertable_alert_events.py
  ├─ 20260420_006_add_audit_log.py
  ├─ 20260420_007_add_camera_health.py
  ├─ 20260420_008_add_sync_packs.py
  ├─ 20260420_009_add_inference_metrics.py
  └─ 20260420_010_enhance_store_settings.py
```

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
        sa.Column("store_id", sa.UUID, sa.ForeignKey("stores.id"), nullable=False),
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
| alert_events (unlabeled) | TimescaleDB | 2 years |
| alert_events (labeled) | TimescaleDB | Unlimited |
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

**Ruult:** Бүх query-д `store_id` эсвэл `org_id` filter заавал orson байх.

**Implementation:**
- Row-level security (RLS) PostgreSQL
- ORM middleware-д automatic filter
- Query audit: Prometheus log all `SELECT` without `store_id` filter

```sql
-- Example RLS policy
ALTER TABLE alert_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY alert_events_isolation ON alert_events
    FOR ALL
    USING (store_id IN (
        SELECT id FROM stores WHERE org_id = current_setting('app.current_org_id')::uuid
    ));
```

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [03-TECH-SPECS.md](./03-TECH-SPECS.md)
- [05-MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md)

---

Updated: 2026-04-17
