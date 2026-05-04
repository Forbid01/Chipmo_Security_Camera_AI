"""alerts.person_id: INTEGER → VARCHAR(32) for P-{store}-{date}-{seq} format.

Revision ID: 20260504_01
Revises: 20260428_02
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260504_01"
down_revision = "20260428_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cast existing integer values to string so no data is lost.
    # Existing rows get their YOLO track ID as the person_id string
    # (e.g. "42") which is valid until they are overwritten by the
    # new generator format.
    op.alter_column(
        "alerts",
        "person_id",
        type_=sa.String(32),
        existing_type=sa.Integer(),
        postgresql_using="person_id::varchar",
        nullable=False,
    )


def downgrade() -> None:
    # Only safe if no P-{store}-{date}-{seq} values exist.
    op.alter_column(
        "alerts",
        "person_id",
        type_=sa.Integer(),
        existing_type=sa.String(32),
        postgresql_using="person_id::integer",
        nullable=False,
    )
