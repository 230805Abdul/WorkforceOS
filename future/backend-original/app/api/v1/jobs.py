import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobOut, JobUpdate
from app.services.audit import record_audit_event
from app.services.cache import cache_get, cache_invalidate, cache_set

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[Job]:
    cache_key = "jobs:list:open"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached  # served from Redis — no DB hit on the hot path

    result = await db.execute(select(Job).order_by(Job.created_at.desc()))
    jobs = list(result.scalars().all())
    await cache_set(cache_key, [JobOut.model_validate(j).model_dump(mode="json") for j in jobs], ttl_seconds=30)
    return jobs


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    request: Request,
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER)),
) -> Job:
    job = Job(**payload.model_dump(), created_by_id=current_user.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await cache_invalidate("jobs:list:*")
    await record_audit_event(
        db, current_user.id, "job.created", "job", str(job.id), request.client.host if request.client else None
    )
    return job


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER)),
) -> Job:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    await db.commit()
    await db.refresh(job)

    await cache_invalidate("jobs:list:*")
    await record_audit_event(
        db, current_user.id, "job.updated", "job", str(job.id), request.client.host if request.client else None
    )
    return job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)) -> Job:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
