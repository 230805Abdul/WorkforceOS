import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Append-only trail of who did what. Never updated, never deleted by app code."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. "application.status_changed"
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
