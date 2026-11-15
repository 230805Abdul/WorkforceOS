from typing import Literal

from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.audit import actor_from, field_changes, record_event
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import parse_id_loose, public_id
from app.models import Application, Candidate
from app.schemas import CandidateDetail, CandidateIn, CandidateOut, CandidateSource
from app.services import (applications_query, application_dict, candidate_dict, candidate_out,
                          candidates_with_counts, get_candidate_or_404, like, log_activity)

router = APIRouter(prefix="/candidates", tags=["candidates"])

SortKey = Literal["full_name", "email", "source", "applications_count", "created_at"]
EMAIL_TAKEN = ApiError(409, "Please fix the highlighted fields.", {"email": "A candidate with this email already exists"})


def _ensure_unique_email(db: Session, email: str, ignore_pk: int | None = None) -> None:
    stmt = select(Candidate.id).where(func.lower(Candidate.email) == email.lower())
    if ignore_pk is not None:
        stmt = stmt.where(Candidate.id != ignore_pk)
    if db.scalar(stmt) is not None:
        raise EMAIL_TAKEN


def _commit(db: Session) -> None:
    """The unique index is the real guard; this catches two people submitting the same email at once."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EMAIL_TAKEN


@router.get("", response_model=list[CandidateOut], dependencies=[Depends(require("candidates:read"))])
def list_candidates(
    search: SearchQuery = None,
    source: CandidateSource | None = None,
    sort: SortKey = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
):
    stmt, applications_count = candidates_with_counts()
    if search and search.strip():
        q = search.strip()
        conditions = [like(Candidate.full_name, q), like(Candidate.email, q)]
        if (pk := parse_id_loose("candidate", q)) is not None:
            conditions.append(Candidate.id == pk)
        stmt = stmt.where(or_(*conditions))
    if source:
        stmt = stmt.where(Candidate.source == source.value)

    sort_columns = {
        "full_name": func.lower(Candidate.full_name), "email": func.lower(Candidate.email), "source": Candidate.source,
        "applications_count": applications_count, "created_at": Candidate.created_at,
    }
    column = sort_columns[sort]
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), Candidate.id.desc() if order == "desc" else Candidate.id.asc())
    return [candidate_dict(*row) for row in db.execute(stmt).all()]


@router.get("/{candidate_id}", response_model=CandidateDetail, dependencies=[Depends(require("candidates:read"))])
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    c = get_candidate_or_404(db, candidate_id)
    apps = db.execute(applications_query().where(Application.candidate_id == c.id)
                      .order_by(Application.created_at.desc(), Application.id.desc())).scalars().all()
    return {**candidate_out(db, c), "applications": [application_dict(a) for a in apps]}


@router.post("", response_model=CandidateOut, status_code=201, dependencies=[Depends(require("candidates:manage"))])
def create_candidate(payload: CandidateIn, request: Request, db: Session = Depends(get_db)):
    _ensure_unique_email(db, payload.email)
    c = Candidate(**payload.model_dump(mode="json"))
    db.add(c)
    db.flush()
    log_activity(db, "candidate", f"{c.full_name} was added as a candidate")
    _commit(db)
    record_event("candidate.created", category="candidate", actor=actor_from(request),
                 target=("candidate", public_id("candidate", c.id)), metadata={"source": c.source})
    return candidate_dict(c, 0)


@router.put("/{candidate_id}", response_model=CandidateOut, dependencies=[Depends(require("candidates:manage"))])
def update_candidate(candidate_id: str, payload: CandidateIn, request: Request, db: Session = Depends(get_db)):
    c = get_candidate_or_404(db, candidate_id)
    _ensure_unique_email(db, payload.email, ignore_pk=c.id)
    before = {field: getattr(c, field) for field in payload.model_dump(mode="json")}
    for field, value in payload.model_dump(mode="json").items():
        setattr(c, field, value)
    log_activity(db, "candidate", f"{c.full_name}'s profile was updated")
    _commit(db)
    changes = field_changes(before, payload.model_dump(mode="json"))
    if changes["fields"]:
        record_event("candidate.updated", category="candidate", actor=actor_from(request),
                     target=("candidate", public_id("candidate", c.id)), metadata=changes)
    return candidate_out(db, c)


@router.delete("/{candidate_id}", status_code=204, dependencies=[Depends(require("candidates:manage"))])
def delete_candidate(candidate_id: str, request: Request, db: Session = Depends(get_db)):
    """Deleting a candidate also removes their applications (ON DELETE CASCADE)."""
    c = get_candidate_or_404(db, candidate_id)
    log_activity(db, "candidate", f"{c.full_name} was deleted")
    target = ("candidate", public_id("candidate", c.id))
    db.delete(c)
    db.commit()
    record_event("candidate.deleted", category="candidate", actor=actor_from(request), target=target)
    return Response(status_code=204)
