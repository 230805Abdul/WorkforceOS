import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatus


class ApplicationCreate(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    ai_match_score: float | None
    created_at: datetime
    updated_at: datetime
