import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str
    department: str
    location: str
    status: JobStatus = JobStatus.DRAFT


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    department: str | None = None
    location: str | None = None
    status: JobStatus | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    department: str
    location: str
    status: JobStatus
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
