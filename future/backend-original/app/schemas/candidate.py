import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class CandidateCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    source: str | None = None


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    phone: str | None
    source: str | None
    created_at: datetime
