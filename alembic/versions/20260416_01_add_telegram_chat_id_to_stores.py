"""add telegram_chat_id to stores

Revision ID: 20260416_01
Revises: 20260414_01
Create Date: 2026-04-16 15:00:00
"""

from alembic import op

revision = "20260416_01"
down_revision = "20260414_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE stores
            ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(100);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE stores
            DROP COLUMN IF EXISTS telegram_chat_id;
    """)
