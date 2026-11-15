import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import User, UserRole
from app.schemas.application import ApplicationCreate, ApplicationOut, ApplicationStatusUpdate
from app.services.audit import record_audit_event
from app.workers.tasks import send_application_status_email

router = APIRouter(prefix="/applications", tags=["applications"])
RECRUITING_ROLES = (UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER)

# Only these forward transitions are allowed — guards against e.g. HIRED -> APPLIED.
VALID_TRANSITIONS = {
    "applied": {"screening", "rejected"},
    "screening": {"interview", "rejected"},
    "interview": {"offer", "rejected"},
    "offer": {"hired", "rejected"},
    "hired": set(),
    "rejected": set(),
}


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> Application:
    if not await db.get(Candidate, payload.candidate_id):
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not await db.get(Job, payload.job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    application = Application(**payload.model_dump())
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


@router.patch("/{application_id}/status", response_model=ApplicationOut)
async def update_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> Application:
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    current = application.status.value
    target = payload.status.value
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition application from '{current}' to '{target}'",
        )

    application.status = payload.status
    await db.commit()
    await db.refresh(application)

    candidate = await db.get(Candidate, application.candidate_id)
    job = await db.get(Job, application.job_id)
    if candidate and job:
        send_application_status_email.delay(candidate.email, job.title, target)  # fire-and-forget

    await record_audit_event(
        db,
        current_user.id,
        "application.status_changed",
        "application",
        str(application.id),
        request.client.host if request.client else None,
        metadata={"from": current, "to": target},
    )
    return application


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> Application:
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("/job/{job_id}", response_model=list[ApplicationOut])
async def list_applications_for_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(*RECRUITING_ROLES)),
) -> list[Application]:
    result = await db.execute(select(Application).where(Application.job_id == job_id))
    return list(result.scalars().all())
