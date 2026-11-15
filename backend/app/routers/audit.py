"""/api/audit: read-only access to the audit log for holders of `audit:read` (Super Administrators by default).
There are deliberately no endpoints that change or delete audit records."""
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.audit import CATEGORIES, AuditEvent, verify_chain
from app.auth.dependencies import require
from app.config import AUDIT_KEY_IS_DEVELOPMENT_DEFAULT
from app.db import get_db
from app.models import utcnow
from app.services import like
from app.validation import SearchQuery

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require("audit:read"))])


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    category: str
    action: str
    outcome: str
    actor_user_id: int | None
    actor_email: str | None
    target_type: str | None
    target_id: str | None
    ip: str | None
    user_agent: str | None
    request_id: str | None
    details: dict


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    next_before_id: int | None  # pass as before_id to get the next (older) page


@router.get("/events", response_model=AuditPage)
def list_events(
    category: Literal[CATEGORIES] | None = None,  # type: ignore[valid-type]
    outcome: Literal["success", "failure", "denied"] | None = None,
    action: Annotated[str | None, Query(max_length=60, pattern=r"^[a-z_.]+$")] = None,
    target_type: Annotated[str | None, Query(max_length=30, pattern=r"^[a-z_]+$")] = None,
    target_id: Annotated[str | None, Query(max_length=40, pattern=r"^[A-Za-z0-9-]+$")] = None,
    search: SearchQuery = None,
    since: datetime | None = None,
    until: datetime | None = None,
    before_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db: DbSession = Depends(get_db),
):
    stmt = select(AuditEvent)
    if category:
        stmt = stmt.where(AuditEvent.category == category)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
    if target_id:
        stmt = stmt.where(AuditEvent.target_id == target_id)
    if since:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.occurred_at <= until)
    if search and search.strip():
        q = search.strip()
        stmt = stmt.where(or_(like(AuditEvent.action, q), like(AuditEvent.actor_email, q), like(AuditEvent.target_id, q),
                              like(AuditEvent.ip, q), like(AuditEvent.request_id, q),
                              like(AuditEvent.details["email"].as_string(), q)))  # e-mail typed in a failed sign-in
    if before_id:
        stmt = stmt.where(AuditEvent.id < before_id)
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1)).all()
    items = rows[:limit]
    return {"items": items, "next_before_id": items[-1].id if len(rows) > limit else None}


@router.get("/summary")
def security_summary(db: DbSession = Depends(get_db)):
    """Security events of the last 24 hours, for the overview at the top of the Audit log page."""
    since = utcnow() - timedelta(hours=24)

    def count(*conditions):
        return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.occurred_at >= since, *conditions))

    email = AuditEvent.details["email"].as_string().label("email")  # one labelled expression, reused by GROUP BY
    failures = func.count().label("failures")
    top_failed = db.execute(
        select(email, failures)
        .where(AuditEvent.occurred_at >= since, AuditEvent.action == "auth.login", AuditEvent.outcome == "failure")
        .group_by(email).order_by(failures.desc(), email).limit(5)
    ).all()
    return {
        "window_hours": 24,
        "failed_sign_ins": count(AuditEvent.action == "auth.login", AuditEvent.outcome == "failure"),
        "successful_sign_ins": count(AuditEvent.action == "auth.login", AuditEvent.outcome == "success"),
        "access_denied": count(AuditEvent.action == "security.access_denied"),
        "rate_limited": count(AuditEvent.action.in_(["security.rate_limited", "security.too_many_attempts"])),
        "new_device_sign_ins": count(AuditEvent.action == "security.new_device_sign_in"),
        "cross_site_refused": count(AuditEvent.action == "security.cross_site_refused"),
        "most_failed_emails": [{"email": email, "failures": n} for email, n in top_failed if email],
    }


@router.get("/verify")
def verify(db: DbSession = Depends(get_db)):
    """Recompute the whole hash chain. Detects records that were altered, inserted or removed in the middle."""
    return {**verify_chain(db), "development_key": AUDIT_KEY_IS_DEVELOPMENT_DEFAULT}
