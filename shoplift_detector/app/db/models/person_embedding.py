from datetime import datetime

from sqlalchemy import BigInteger, Column, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

REID_EMBEDDING_DIM = 576  # MobileNetV3-Small global average pool output


def _make_vector_column():
    """Return a SQLAlchemy Column(Vector(576)) or a plain Text column as
    fallback when pgvector is not installed in the local dev environment.
    The migration DDL is authoritative; this mapping is only used when
    create_all() runs against a pgvector-enabled Postgres."""
    try:
        from pgvector.sqlalchemy import Vector
        return Column("embedding", Vector(REID_EMBEDDING_DIM), nullable=True)
    except ImportError:
        from sqlalchemy import Text
        return Column("embedding", Text, nullable=True)


class PersonEmbedding(Base):
    """Appearance embedding for a person detected at alert time.

    Used for cross-camera Re-ID: given an alert on camera A, find the
    same person on cameras B and C within the same store and time window.
    Embeddings are L2-normalised before storage so cosine similarity ==
    dot product, compatible with pgvector's `<=>` cosine operator.
    """

    __tablename__ = "person_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box in the full display frame (pixels). Stored so the UI
    # can highlight the matched person crop on the source alert image.
    bbox_x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x2: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y2: Mapped[float | None] = mapped_column(Float, nullable=True)

    captured_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    # pgvector column — DDL lives in migration 20260428_02.
    embedding = _make_vector_column()

    def __repr__(self) -> str:
        return (
            f"<PersonEmbedding(id={self.id}, camera_id={self.camera_id}, "
            f"track_id={self.track_id})>"
        )
