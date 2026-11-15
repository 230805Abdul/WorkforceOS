from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import actor_from, record_event
from app.auth.dependencies import require
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import parse_id, parse_id_loose, public_id
from app.models import Application, Candidate, Job, utcnow
from app.schemas import (VALID_TRANSITIONS, ApplicationIn, ApplicationOut, ApplicationStatus, ApplicationStatusUpdate)
from app.services import (application_dict, application_out, applications_query, get_application_or_404,
                          get_candidate_or_404, get_job_or_404, hired_count, like, log_activity)

router = APIRouter(prefix="/applications", tags=["applications"])

ALREADY_APPLIED = ApiError(409, "Please fix the highlighted fields.", {"job_id": "This candidate has already applied for this job"})


@router.get("", response_model=list[ApplicationOut], dependencies=[Depends(require("applications:read"))])
def list_applications(
    job_id: str | None = None,
    candidate_id: str | None = None,
    status: ApplicationStatus | None = None,
    search: SearchQuery = None,
    db: Session = Depends(get_db),
):
    stmt = applications_query()
    if job_id:
        if (pk := parse_id("job", job_id)) is None:
            return []
        stmt = stmt.where(Application.job_id == pk)
    if candidate_id:
        if (pk := parse_id("candidate", candidate_id)) is None:
            return []
        stmt = stmt.where(Application.candidate_id == pk)
    if status:
        stmt = stmt.where(Application.status == status.value)
    if search and search.strip():
        q = search.strip()
        conditions = [like(Candidate.full_name, q), like(Job.title, q)]
        if (pk := parse_id_loose("application", q)) is not None:
            conditions.append(Application.id == pk)
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(Application.updated_at.desc(), Application.id.desc())
    return [application_dict(a) for a in db.execute(stmt).scalars().all()]


@router.post("", response_model=ApplicationOut, status_code=201, dependencies=[Depends(require("applications:manage"))])
def create_application(payload: ApplicationIn, request: Request, db: Session = Depends(get_db)):
    candidate = get_candidate_or_404(db, payload.candidate_id)
    job = get_job_or_404(db, payload.job_id)
    if job.status != "open":
        raise ApiError(409, "Please fix the highlighted fields.", {"job_id": "This job is not open for applications"})
    if db.scalar(select(Application.id).where(Application.candidate_id == candidate.id, Application.job_id == job.id)):
        raise ALREADY_APPLIED

    now = utcnow()
    app = Application(candidate_id=candidate.id, job_id=job.id, status="applied", created_at=now, updated_at=now)
    db.add(app)
    log_activity(db, "application", f"{candidate.full_name} applied for '{job.title}'")
    try:
        db.commit()  # the unique constraint (candidate, job) is the final guard against double submits
    except IntegrityError:
        db.rollback()
        raise ALREADY_APPLIED
    record_event("application.created", category="application", actor=actor_from(request),
                 target=("application", public_id("application", app.id)),
                 metadata={"candidate": public_id("candidate", candidate.id), "job": public_id("job", job.id)})
    return application_out(db, app)


@router.patch("/{application_id}/status", response_model=ApplicationOut, dependencies=[Depends(require("applications:manage"))])
def update_status(application_id: str, payload: ApplicationStatusUpdate, request: Request, db: Session = Depends(get_db)):
    # Lock order is always application -> job, so two requests can never deadlock each other.
    app = get_application_or_404(db, application_id, lock=True)
    current, target = app.status, payload.status.value
    if target not in VALID_TRANSITIONS[current]:
        raise ApiError(400, f"Cannot move an application from '{current}' to '{target}'")

    job = db.execute(select(Job).where(Job.id == app.job_id).with_for_update()).scalar_one()
    if target == "hired" and hired_count(db, job.id) >= job.openings:
        # Because the job row is locked, two simultaneous "hire" clicks cannot both take the last opening.
        raise ApiError(409, f"All {job.openings} opening(s) for '{job.title}' are already filled")

    app.status = target
    app.updated_at = utcnow()
    candidate = db.get(Candidate, app.candidate_id)
    log_activity(db, "application", f"{candidate.full_name} moved to {target} for '{job.title}'")
    db.commit()
    record_event("application.status_changed", category="application", actor=actor_from(request),
                 target=("application", public_id("application", app.id)), metadata={"from": current, "to": target})
    return application_out(db, app)


@router.delete("/{application_id}", status_code=204, dependencies=[Depends(require("applications:manage"))])
def delete_application(application_id: str, request: Request, db: Session = Depends(get_db)):
    app = get_application_or_404(db, application_id)
    row = application_dict(db.execute(applications_query().where(Application.id == app.id)).scalar_one())
    log_activity(db, "application", f"{row['candidate_name']}'s application for '{row['job_title']}' was removed")
    target = ("application", public_id("application", app.id))
    db.delete(app)
    db.commit()
    record_event("application.deleted", category="application", actor=actor_from(request), target=target)
    return Response(status_code=204)
