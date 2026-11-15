from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Candidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "candidates"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resume_object_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True, doc="S3/object storage key for the uploaded resume file"
    )
    source: Mapped[str | None] = mapped_column(String(100), nullable=True, doc="e.g. referral, linkedin, applied")
