"""Add substream_url to cameras table.

Secondary (lower-resolution) RTSP URL per camera. When set, the AI
inference loop reads frames from this stream instead of the primary
stream — keeping the primary stream pristine for display while the AI
processes a cheaper low-res feed.

Revision ID: 20260428_01
Revises: 20260427_03
"""

from alembic import op

revision = "20260428_01"
down_revision = "20260427_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cameras
            ADD COLUMN IF NOT EXISTS substream_url TEXT;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cameras DROP COLUMN IF EXISTS substream_url;")
