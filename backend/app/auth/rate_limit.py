"""Rate limiting for the sensitive public endpoints, backed by the auth_attempts table.

Because attempts are stored in PostgreSQL, the limits survive restarts and apply across several server processes.

  login     5 failed attempts per e-mail per 15 minutes (counted since that account's last successful sign-in)
            30 failed attempts per IP address per 15 minutes
  register  10 attempts per IP address per hour
  reset     10 failed attempts per IP address per 15 minutes

Limitation (until Phase 5 adds a trusted reverse proxy): behind the Vite dev proxy every request seems to come from
127.0.0.1, so the per-IP limits act as one shared limit. The per-e-mail login limit is unaffected.
"""
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.models import AuthAttempt
from app.errors import ApiError
from app.models import utcnow

LIMITS = {  # kind: (window, max per e-mail, max per IP, count only failures?)
    "login": (timedelta(minutes=15), 5, 30, True),
    "register": (timedelta(hours=1), None, 10, False),
    "reset": (timedelta(minutes=15), None, 10, True),
}


def _too_many(window: timedelta) -> ApiError:
    minutes = int(window.total_seconds() // 60)
    return ApiError(429, f"Too many attempts. Please wait up to {minutes} minutes and try again.", code="rate_limited",
                    headers={"Retry-After": str(int(window.total_seconds()))})


def _blocked(kind: str, window: timedelta, by: str, who: str | None) -> ApiError:
    """Record the block (once per account/address per window, so a script can't flood the audit log), then refuse."""
    from app.audit import first_time_in, record_event

    if first_time_in(f"attempts:{kind}:{by}:{who}", window.total_seconds()):
        record_event("security.too_many_attempts", category="security", outcome="denied",
                     metadata={"kind": kind, "by": by, **({"email": who} if by == "email" else {})})
    return _too_many(window)


def check(db: DbSession, kind: str, *, email: str | None, ip: str | None) -> None:
    window, per_email, per_ip, failures_only = LIMITS[kind]
    since = utcnow() - window
    base = select(func.count()).select_from(AuthAttempt).where(AuthAttempt.kind == kind, AuthAttempt.created_at > since)
    if failures_only:
        base = base.where(AuthAttempt.succeeded.is_(False))
    if per_email and email:
        last_ok = db.scalar(select(func.max(AuthAttempt.created_at)).where(
            AuthAttempt.kind == kind, func.lower(AuthAttempt.email) == email.lower(), AuthAttempt.succeeded.is_(True)))
        stmt = base.where(func.lower(AuthAttempt.email) == email.lower())
        if last_ok is not None:
            stmt = stmt.where(AuthAttempt.created_at > last_ok)
        if db.scalar(stmt) >= per_email:
            raise _blocked(kind, window, "email", email.lower())
    if per_ip and ip and db.scalar(base.where(AuthAttempt.ip == ip)) >= per_ip:
        raise _blocked(kind, window, "ip", ip)


def record(db: DbSession, kind: str, *, email: str | None, ip: str | None, succeeded: bool) -> None:
    now = utcnow()
    db.add(AuthAttempt(kind=kind, email=(email or "")[:254].lower() or None, ip=ip, succeeded=succeeded, created_at=now))
    db.execute(delete(AuthAttempt).where(AuthAttempt.created_at < now - timedelta(days=1)))  # keep the table small
    db.commit()
