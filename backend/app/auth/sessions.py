"""Server-side sessions in PostgreSQL + an HttpOnly cookie.

Lifecycle
  sign in   -> new random token; the browser gets it in the HttpOnly cookie, the database keeps only sha256(token)
  each call -> cookie -> hash -> sessions row; refused if past expires_at (absolute) or idle for too long
  sign out  -> row deleted, cookie removed
  password change / reset, account disabled -> rows deleted, so every other browser is signed out at once
"""
from datetime import datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.auth.models import Session, User
from app.auth.passwords import new_token, token_hash
from app.config import (COOKIE_SECURE, MAX_SESSIONS_PER_USER, REAUTH_MINUTES, REMEMBER_ME_DAYS, REMEMBER_ME_IDLE_DAYS,
                        SESSION_ABSOLUTE_HOURS, SESSION_IDLE_MINUTES)
from app.errors import SESSION_COOKIE, ApiError
from app.models import utcnow

TOUCH_EVERY = timedelta(seconds=60)  # don't write to the database on every single request


def client_ip(request: Request) -> str | None:
    # Behind the Vite dev proxy this is always 127.0.0.1. Trusting X-Forwarded-For safely needs a known reverse
    # proxy, which arrives with Docker/cloud (Phase 5/6); until then we deliberately don't read that header.
    return request.client.host if request.client else None


def idle_limit(session: Session) -> timedelta:
    return timedelta(days=REMEMBER_ME_IDLE_DAYS) if session.remember else timedelta(minutes=SESSION_IDLE_MINUTES)


def create_session(db: DbSession, user: User, *, remember: bool, request: Request) -> tuple[str, Session]:
    now = utcnow()
    token = new_token()
    session = Session(
        user_id=user.id, token_hash=token_hash(token), csrf_token=new_token(), remember=remember,
        created_at=now, last_seen_at=now, reauthenticated_at=now,
        expires_at=now + (timedelta(days=REMEMBER_ME_DAYS) if remember else timedelta(hours=SESSION_ABSOLUTE_HOURS)),
        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:200] or None,
    )
    db.add(session)
    db.flush()
    # Concurrent-session policy: at most MAX_SESSIONS_PER_USER; signing in on one more device ends the oldest.
    ids = db.scalars(select(Session.id).where(Session.user_id == user.id).order_by(Session.last_seen_at.desc(), Session.id.desc())).all()
    if len(ids) > MAX_SESSIONS_PER_USER:
        db.execute(delete(Session).where(Session.id.in_(ids[MAX_SESSIONS_PER_USER:])))
    db.execute(delete(Session).where(Session.user_id == user.id, Session.expires_at < now))  # tidy up
    return token, session


def end_presented_session(db: DbSession, request: Request) -> None:
    """Sign-in always starts a brand-new session with a new random token. If the browser still carried an older
    session cookie, that session is ended too, so no previously known/planted session ID survives a sign-in
    (session fixation) and one browser never holds two live sessions."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(Session).where(Session.token_hash == token_hash(token)))


def set_session_cookie(response: Response, token: str, session: Session) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True,             # JavaScript (and therefore an XSS attack) can't read it
        secure=COOKIE_SECURE,      # HTTPS only (forced in production)
        samesite="lax",            # not sent on cross-site POST/PUT/DELETE: first line of CSRF defence
        path="/",
        # "Remember me" -> a persistent cookie; otherwise a browser-session cookie that disappears on close.
        max_age=int((session.expires_at - utcnow()).total_seconds()) if session.remember else None,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")


SESSION_EXPIRED = "Your session has expired. Please sign in again."


def load_session(db: DbSession, token: str) -> Session:
    session = db.scalar(select(Session).where(Session.token_hash == token_hash(token)))
    if session is None:  # signed out, revoked (password change, disabled account, too many devices) or forged
        raise ApiError(401, SESSION_EXPIRED, code="session_expired", clear_session=True)
    now = utcnow()
    if session.expires_at <= now or session.last_seen_at + idle_limit(session) <= now:
        db.delete(session)
        db.commit()
        raise ApiError(401, SESSION_EXPIRED, code="session_expired", clear_session=True)
    if now - session.last_seen_at >= TOUCH_EVERY:
        session.last_seen_at = now
        db.commit()
    return session


def revoke_sessions(db: DbSession, user_id: int, *, keep: int | None = None) -> int:
    stmt = delete(Session).where(Session.user_id == user_id)
    if keep is not None:
        stmt = stmt.where(Session.id != keep)
    return db.execute(stmt).rowcount


def active_session_count(db: DbSession, user_id: int, now: datetime | None = None) -> int:
    now = now or utcnow()
    return len(db.scalars(select(Session.id).where(Session.user_id == user_id, Session.expires_at > now)).all())


def recently_authenticated(session: Session, now: datetime | None = None) -> bool:
    confirmed = session.reauthenticated_at or session.created_at
    return (now or utcnow()) - confirmed < timedelta(minutes=REAUTH_MINUTES)
