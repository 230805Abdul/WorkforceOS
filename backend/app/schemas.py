"""Pydantic models = request validation + response shapes. (Database tables live in models.py.)"""
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.validation import STRICT, text


class JobStatus(str, Enum):
    draft = "draft"
    open = "open"
    closed = "closed"
    archived = "archived"


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"


class ApplicationStatus(str, Enum):
    applied = "applied"
    screening = "screening"
    interview = "interview"
    offer = "offer"
    hired = "hired"
    rejected = "rejected"


class CandidateSource(str, Enum):
    careers_page = "careers_page"
    referral = "referral"
    linkedin = "linkedin"
    agency = "agency"
    other = "other"


class EmploymentStatus(str, Enum):
    active = "active"
    on_leave = "on_leave"
    terminated = "terminated"


# Same rules as the original project's state machine: only forward moves, or reject.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "applied": ["screening", "rejected"],
    "screening": ["interview", "rejected"],
    "interview": ["offer", "rejected"],
    "offer": ["hired", "rejected"],
    "hired": [],
    "rejected": [],
}

Str = text  # bounded, trimmed, no control characters (app/validation.py)
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9+()\-\s]{7,20}$")]


def _blank_to_none(v):
    return None if isinstance(v, str) and not v.strip() else v


# ---------- Departments ----------
class DepartmentIn(BaseModel):
    model_config = STRICT

    name: Str(2, 80)
    code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{2,10}$")]
    description: Str(1, 500, multiline=True) | None = None

    _blank = field_validator("description", mode="before")(_blank_to_none)


class DepartmentOut(DepartmentIn):
    model_config = ConfigDict(extra="ignore")  # responses: inherit the fields, not the strictness

    id: str
    is_sample: bool
    employees_count: int
    active_employees_count: int
    jobs_count: int
    created_at: datetime
    updated_at: datetime


# ---------- Jobs ----------
class JobIn(BaseModel):
    model_config = STRICT

    title: Str(3, 120)
    department_id: Str(1, 40)
    location: Str(1, 100)
    employment_type: EmploymentType = EmploymentType.full_time
    status: JobStatus = JobStatus.draft
    openings: int = Field(default=1, ge=1, le=50)
    description: Str(10, 4000, multiline=True)


class JobOut(JobIn):
    model_config = ConfigDict(extra="ignore")  # responses: inherit the fields, not the strictness

    id: str
    department: str  # the department's name, for display
    is_sample: bool
    created_at: datetime
    updated_at: datetime
    applications_count: int
    hired_count: int


# ---------- Candidates ----------
class CandidateIn(BaseModel):
    model_config = STRICT

    full_name: Str(2, 120)
    email: EmailStr
    phone: Phone | None = None
    source: CandidateSource = CandidateSource.other

    _blank = field_validator("phone", mode="before")(_blank_to_none)


class ApplicationOut(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str
    job_id: str
    job_title: str
    department_id: str
    department: str
    status: ApplicationStatus
    allowed_next: list[ApplicationStatus]
    employee_id: str | None  # set once the hired candidate has been turned into an employee
    created_at: datetime
    updated_at: datetime


class CandidateOut(CandidateIn):
    model_config = ConfigDict(extra="ignore")  # responses: inherit the fields, not the strictness

    id: str
    is_sample: bool
    created_at: datetime
    applications_count: int


class CandidateDetail(CandidateOut):
    applications: list[ApplicationOut]


# ---------- Applications ----------
class ApplicationIn(BaseModel):
    model_config = STRICT

    candidate_id: Str(1, 40)
    job_id: Str(1, 40)


class ApplicationStatusUpdate(BaseModel):
    model_config = STRICT

    status: ApplicationStatus


# ---------- Employees ----------
class EmployeeIn(BaseModel):
    model_config = STRICT

    employee_code: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{1,19}$")]
    first_name: Str(1, 60)
    last_name: Str(1, 60)
    email: EmailStr
    phone: Phone | None = None
    job_title: Str(2, 120)
    department_id: Str(1, 40)
    employment_status: EmploymentStatus = EmploymentStatus.active
    joining_date: date

    _blank = field_validator("phone", mode="before")(_blank_to_none)

    @field_validator("joining_date")
    @classmethod
    def sensible_date(cls, v: date) -> date:
        if v < date(1950, 1, 1) or v > date.today() + timedelta(days=366):
            raise ValueError("Enter a realistic joining date")
        return v


class EmployeeCreate(EmployeeIn):
    candidate_id: Str(1, 40) | None = None  # only when turning a hired candidate into an employee


class EmployeeOut(EmployeeIn):
    model_config = ConfigDict(extra="ignore")  # responses: inherit the fields, not the strictness

    id: str
    full_name: str
    department: str
    candidate_id: str | None
    is_sample: bool
    created_at: datetime
    updated_at: datetime
