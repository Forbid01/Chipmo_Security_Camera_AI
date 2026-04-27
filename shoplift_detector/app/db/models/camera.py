from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .alert import Alert
    from .store import Store


class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    camera_type: Mapped[str] = mapped_column(String(20), nullable=False)  # rtsp, mjpeg, usb, axis
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Shelf ROI polygons (normalized 0..1 coords). Empty list = fall back to
    # COCO class detection. See alembic 20260423_01 for schema.
    shelf_zones: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    # Legacy support
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    store: Mapped["Store"] = relationship(back_populates="cameras")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="camera")

    def __repr__(self) -> str:
        return f"<Camera(id={self.id}, name='{self.name}', store_id={self.store_id})>"
