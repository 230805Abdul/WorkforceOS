"""Reusable FastAPI dependencies: the ONLY place where "who is calling and what may they do" is decided.

    @router.get("/employees", dependencies=[Depends(require("employees:read"))])     # just check
    def update(..., auth: Auth = Depends(require("users:manage"))):                  # check AND use the caller

401 = not signed in (or session ended). 403 = signed in but not allowed (or missing CSRF token).
"""
import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.models import Permission, RolePermission, Session, User, UserRole
from app.auth.sessions import load_session, recently_authenticated, revoke_sessions
from app.db import get_db
from app.errors import SESSION_COOKIE, ApiError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class Auth:
    user: User
    session: Session
    permissions: frozenset[str]

    def can(self, permission: str) -> bool:
        return permission in self.permissions


def effective_permissions(db: DbSession, user_id: int) -> frozenset[str]:
    """Union of the permissions of all the user's roles."""
    rows = db.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    ).all()
    return frozenset(rows)


def get_auth(request: Request, db: DbSession = Depends(get_db)) -> Auth:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError(401, "Please sign in to continue.", code="not_authenticated")
    session = load_session(db, token)
    user = db.get(User, session.user_id)
    request.state.user_id, request.state.user_email = session.user_id, user.email if user else None  # for logs/audit
    if user is None or user.status != "active":
        revoke_sessions(db, session.user_id)
        db.commit()
        raise ApiError(401, "This account has been disabled.", code="account_disabled", clear_session=True)

    # CSRF: a page on another site can make the browser SEND our cookie, but it can't READ our responses, so it
    # can't know this per-session token. Every state-changing request must echo it back in a header.
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent.encode(), session.csrf_token.encode()):
            raise ApiError(403, "Security check failed. Refresh the page and try again.", code="csrf_failed")

    return Auth(user=user, session=session, permissions=effective_permissions(db, user.id))


def require(*permissions: str):
    """Dependency factory: the caller must have ALL of the given permissions."""

    def dependency(auth: Auth = Depends(get_auth)) -> Auth:
        if not all(auth.can(p) for p in permissions):
            raise ApiError(403, "You don't have permission to do this.", code="forbidden")
        return auth

    dependency.required_permissions = permissions  # lets tests list what each endpoint requires
    return dependency


def require_any(*permissions: str):
    """Dependency factory: the caller needs AT LEAST ONE of the given permissions."""

    def dependency(auth: Auth = Depends(get_auth)) -> Auth:
        if not any(auth.can(p) for p in permissions):
            raise ApiError(403, "You don't have permission to do this.", code="forbidden")
        return auth

    dependency.required_permissions = permissions
    return dependency


def require_recent(*permissions: str):
    """Like require(), for high-impact actions (roles, account status, reset links...): the password must ALSO have been
    entered in this session within REAUTH_MINUTES. Otherwise 403 "reauth_required" and the frontend asks for it
    (POST /api/auth/reauthenticate), then retries. A hijacked or unattended session alone can't change who has power."""
    check = require(*permissions)

    def dependency(auth: Auth = Depends(check)) -> Auth:
        if not recently_authenticated(auth.session):
            raise ApiError(403, "Please confirm your password to continue.", code="reauth_required")
        return auth

    dependency.required_permissions = permissions
    dependency.requires_recent_auth = True
    return dependency
