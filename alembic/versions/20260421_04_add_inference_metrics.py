"""add inference_metrics table

Revision ID: 20260421_04
Revises: 20260421_03
Create Date: 2026-04-21 00:00:00

- Normal PostgreSQL table first; TimescaleDB hypertable is gated by
  the optional setup migration (20260421_06).
- Composite PK `(camera_id, timestamp)` so point-in-time rows are unique
  per camera without adding a synthetic id column.

Additive, rollback-safe, no core-table alterations.
"""

from alembic import op

revision = "20260421_04"
down_revision = "20260421_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS inference_metrics (
            camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            timestamp TIMESTAMPTZ NOT NULL,

            fps DOUBLE PRECISION,
            yolo_latency_ms DOUBLE PRECISION,
            reid_latency_ms DOUBLE PRECISION,
            rag_latency_ms DOUBLE PRECISION,
            vlm_latency_ms DOUBLE PRECISION,
            end_to_end_latency_ms DOUBLE PRECISION,

            PRIMARY KEY (camera_id, timestamp)
        );

        CREATE INDEX IF NOT EXISTS idx_inference_metrics_timestamp
            ON inference_metrics (timestamp DESC);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS inference_metrics;
    """)
