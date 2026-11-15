from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.audit import actor_from, field_changes, record_event
from app.auth.dependencies import require
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import parse_id, parse_id_loose, public_id
from app.models import Department, Job, utcnow
from app.schemas import JobIn, JobOut, JobStatus
from app.services import (get_job_or_404, hired_count, job_dict, job_out, jobs_with_counts, like, log_activity,
                          order_by, resolve_department)

router = APIRouter(prefix="/jobs", tags=["jobs"])

SortKey = Literal["title", "department", "status", "openings", "applications_count", "created_at"]


def _values(db: Session, payload: JobIn) -> dict:
    """Request body -> column values (the public department id becomes the real foreign key)."""
    values = payload.model_dump(mode="json")
    values["department_id"] = resolve_department(db, payload.department_id).id
    return values


@router.get("", response_model=list[JobOut], dependencies=[Depends(require("jobs:read"))])
def list_jobs(
    search: SearchQuery = None,
    status: JobStatus | None = None,
    department_id: str | None = None,
    sort: SortKey = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
):
    stmt, applications_count = jobs_with_counts()
    if search and search.strip():
        q = search.strip()
        conditions = [like(Job.title, q), like(Department.name, q), like(Job.location, q)]
        if (pk := parse_id_loose("job", q)) is not None:
            conditions.append(Job.id == pk)
        stmt = stmt.where(or_(*conditions))
    if status:
        stmt = stmt.where(Job.status == status.value)
    if department_id:
        if (pk := parse_id("department", department_id)) is None:
            return []
        stmt = stmt.where(Job.department_id == pk)

    sort_columns = {
        "title": [func.lower(Job.title)], "department": [func.lower(Department.name)], "status": [Job.status],
        "openings": [Job.openings], "applications_count": [applications_count], "created_at": [Job.created_at],
    }
    stmt = stmt.order_by(*order_by(sort_columns[sort], order, Job.id))
    return [job_dict(*row) for row in db.execute(stmt).all()]


@router.get("/{job_id}", response_model=JobOut, dependencies=[Depends(require("jobs:read"))])
def get_job(job_id: str, db: Session = Depends(get_db)):
    return job_out(db, get_job_or_404(db, job_id))


@router.post("", response_model=JobOut, status_code=201, dependencies=[Depends(require("jobs:manage"))])
def create_job(payload: JobIn, request: Request, db: Session = Depends(get_db)):
    job = Job(**_values(db, payload))
    db.add(job)
    db.flush()
    log_activity(db, "job", f"Job '{job.title}' was created")
    db.commit()
    record_event("job.created", category="job", actor=actor_from(request), target=("job", public_id("job", job.id)),
                 metadata={"title": job.title, "status": job.status})
    return job_out(db, job)


@router.put("/{job_id}", response_model=JobOut, dependencies=[Depends(require("jobs:manage"))])
def update_job(job_id: str, payload: JobIn, request: Request, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id, lock=True)  # row lock: nobody can hire into this job while we edit it
    hired = hired_count(db, job.id)
    if payload.openings < hired:
        raise ApiError(422, "Please fix the highlighted fields.",
                       {"openings": f"Cannot be lower than the {hired} candidate(s) already hired"})
    values = _values(db, payload)
    before = {field: getattr(job, field) for field in values}
    for field, value in values.items():
        setattr(job, field, value)
    job.updated_at = utcnow()
    log_activity(db, "job", f"Job '{job.title}' was updated")
    db.commit()
    changes = field_changes(before, values)
    if changes["fields"]:
        record_event("job.updated", category="job", actor=actor_from(request), target=("job", public_id("job", job.id)),
                     metadata=changes)
    return job_out(db, job)


@router.delete("/{job_id}", status_code=204, dependencies=[Depends(require("jobs:manage"))])
def delete_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    """Deleting a job also removes its applications: the database cascades it (ON DELETE CASCADE)."""
    job = get_job_or_404(db, job_id)
    log_activity(db, "job", f"Job '{job.title}' was deleted")
    target, title = ("job", public_id("job", job.id)), job.title
    db.delete(job)
    db.commit()
    record_event("job.deleted", category="job", actor=actor_from(request), target=target, metadata={"title": title})
    return Response(status_code=204)
