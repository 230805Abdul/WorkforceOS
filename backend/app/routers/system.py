from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_auth
from app.config import ENABLE_DEMO_RESET
from app.db import get_db
from app.errors import ApiError
from app.models import utcnow
from app.schemas import VALID_TRANSITIONS, ApplicationStatus, CandidateSource, EmploymentStatus, EmploymentType, JobStatus

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """200 only if the API AND the database are reachable."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise ApiError(503, "The database is unavailable. Check that PostgreSQL is running and DATABASE_URL is correct.")
    return {"status": "ok", "database": "ok", "service": "workforceos-api", "time": utcnow().isoformat()}


@router.get("/meta", dependencies=[Depends(get_auth)])
def meta():
    """Fixed option lists the UI needs for dropdowns (any signed-in user). Departments are real data: GET /api/departments."""
    return {
        "job_statuses": [s.value for s in JobStatus],
        "employment_types": [s.value for s in EmploymentType],
        "application_statuses": [s.value for s in ApplicationStatus],
        "candidate_sources": [s.value for s in CandidateSource],
        "employment_statuses": [s.value for s in EmploymentStatus],
        "transitions": VALID_TRANSITIONS,
        "demo_reset_enabled": ENABLE_DEMO_RESET,
    }
