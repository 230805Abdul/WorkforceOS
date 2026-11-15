"""Database tables. If you change anything here, create a migration:  alembic revision --autogenerate -m "..."

Relationships at a glance (see docs/DATABASE.md for the diagram):

    departments 1 ──< jobs 1 ──< applications >── 1 candidates 1 ── 0..1 employees >── 1 departments

* Deleting a department that still has jobs or employees is RESTRICTED (the database refuses).
* Deleting a job or a candidate deletes their applications (CASCADE).
* Deleting a candidate who became an employee keeps the employee (the link is set to NULL).
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.schemas import ApplicationStatus, CandidateSource, EmploymentStatus, EmploymentType, JobStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _one_of(column: str, enum_cls) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum_cls)})"


def _sample_flag() -> Mapped[bool]:
    """True for records inserted by `python -m app.seed`, so they can always be told apart from real ones."""
    return mapped_column(Boolean, default=False, server_default=false())


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (CheckConstraint("code = upper(code)", name="code_uppercase"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(10), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    is_sample: Mapped[bool] = _sample_flag()
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    # No cascade: the foreign keys use ON DELETE RESTRICT, and passive_deletes="all" stops SQLAlchemy
    # from trying to "helpfully" blank out children's department_id before the delete.
    jobs: Mapped[list["Job"]] = relationship(back_populates="department", passive_deletes="all")
    employees: Mapped[list["Employee"]] = relationship(back_populates="department", passive_deletes="all")


# Names are unique ignoring upper/lower case.
Index("uq_departments_name_lower", func.lower(Department.name), unique=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("openings BETWEEN 1 AND 50", name="openings_range"),
        CheckConstraint(_one_of("status", JobStatus), name="status_valid"),
        CheckConstraint(_one_of("employment_type", EmploymentType), name="employment_type_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    location: Mapped[str] = mapped_column(String(100))
    employment_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    openings: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    is_sample: Mapped[bool] = _sample_flag()
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    department: Mapped[Department] = relationship(back_populates="jobs")
    # Deleting a job deletes its applications. The database does it (ON DELETE CASCADE);
    # passive_deletes tells SQLAlchemy not to load them first.
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan", passive_deletes=True)


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (CheckConstraint(_one_of("source", CandidateSource), name="source_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), index=True)
    is_sample: Mapped[bool] = _sample_flag()
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    applications: Mapped[list["Application"]] = relationship(back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True)
    employee: Mapped["Employee | None"] = relationship(back_populates="candidate", uselist=False, passive_deletes=True)


# Email must be unique ignoring upper/lower case: "A@x.com" and "a@x.com" are the same person.
Index("uq_candidates_email_lower", func.lower(Candidate.email), unique=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_applications_candidate_job"),  # one application per person per job
        CheckConstraint(_one_of("status", ApplicationStatus), name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship(back_populates="applications")


class Employee(Base):
    """A person who works here. Deliberately has NO login fields: in Phase 3 a separate `users` table will
    point at employees (users.employee_id, nullable), so not every employee needs an account."""

    __tablename__ = "employees"
    __table_args__ = (CheckConstraint(_one_of("employment_status", EmploymentStatus), name="employment_status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(20), unique=True)
    first_name: Mapped[str] = mapped_column(String(60))
    last_name: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(20))
    job_title: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    employment_status: Mapped[str] = mapped_column(String(20), index=True)
    joining_date: Mapped[date] = mapped_column(Date)
    # Set when the employee was created from a hired candidate. One candidate can become at most one employee.
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), unique=True)
    is_sample: Mapped[bool] = _sample_flag()
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    department: Mapped[Department] = relationship(back_populates="employees")
    candidate: Mapped[Candidate | None] = relationship(back_populates="employee")


Index("uq_employees_email_lower", func.lower(Employee.email), unique=True)


class ActivityLog(Base):
    """What the dashboard's 'Recent activity' feed shows."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
