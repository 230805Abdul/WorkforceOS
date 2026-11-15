import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ApplicationStatus(str, enum.Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"


class Application(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.APPLIED,
        nullable=False,
        index=True,
    )
    ai_match_score: Mapped[float | None] = mapped_column(nullable=True, doc="0-100 score from the matching service")
