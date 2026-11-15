"""/api/users: account administration (Super Administrators by default).

Rules that prevent privilege escalation and lock-outs:
  * You can't change your OWN roles or status here (ask another administrator).
  * The last active Super Administrator can't be disabled or lose that role.
  * You can only grant roles whose permissions you hold yourself.
  * Accounts are never deleted through the API: disable them instead (keeps the history consistent).
"""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.audit import record_event
from app.auth.dependencies import Auth, require, require_recent
from app.auth.models import Role, User, UserRole
from app.auth.permissions import DEFAULT_ROLE, SUPER_ADMIN_ROLE
from app.auth.schemas import (InviteOut, LinkOut, UserDetail, UserInvite, UserOut, UserRolesUpdate, UserStatusUpdate,
                              UserUpdate)
from app.auth.service import (active_super_admins, create_link, find_user_by_email, get_user_or_404, normalize_email,
                              resolve_employee_link, resolve_roles, user_dict, user_query)
from app.auth.sessions import active_session_count, revoke_sessions
from app.config import INVITE_LINK_HOURS, RESET_LINK_MINUTES
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import public_id
from app.services import like, log_activity

router = APIRouter(prefix="/users", tags=["users"])


def _detail(db: DbSession, user: User) -> dict:
    return {**user_dict(db, user), "active_sessions": active_session_count(db, user.id)}


def _ensure_grantable(auth: Auth, roles: list[Role]) -> None:
    granted = {p.code for r in roles for p in r.permissions}
    if not granted <= auth.permissions:
        raise ApiError(403, "You can't grant permissions you don't have yourself.", code="privilege_escalation")


@router.get("", response_model=list[UserOut], dependencies=[Depends(require("users:read"))])
def list_users(search: SearchQuery = None, status: Literal["active", "disabled"] | None = None, role: str | None = None,
               db: DbSession = Depends(get_db)):
    stmt = user_query()
    if search and search.strip():
        stmt = stmt.where(or_(like(User.full_name, search.strip()), like(User.email, search.strip())))
    if status:
        stmt = stmt.where(User.status == status)
    if role:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == role)))
    return [user_dict(db, u) for u in db.scalars(stmt.order_by(func.lower(User.full_name), User.id)).all()]


@router.get("/{user_id}", response_model=UserDetail, dependencies=[Depends(require("users:read"))])
def get_user(user_id: str, db: DbSession = Depends(get_db)):
    return _detail(db, get_user_or_404(db, user_id))


@router.post("", response_model=InviteOut, status_code=201)
def invite_user(payload: UserInvite, auth: Auth = Depends(require_recent("users:manage")), db: DbSession = Depends(get_db)):
    """Create an account WITHOUT a password and return a one-time link for the person to choose their own."""
    email = normalize_email(payload.email)
    if find_user_by_email(db, email) is not None:
        raise ApiError(409, "Please fix the highlighted fields.", {"email": "An account with this email already exists"})
    roles = resolve_roles(db, payload.role_ids) if payload.role_ids else [db.scalar(select(Role).where(Role.name == DEFAULT_ROLE))]
    if any(r.name != DEFAULT_ROLE for r in roles) and not auth.can("roles:assign"):
        raise ApiError(403, "You don't have permission to assign roles.", code="forbidden")
    _ensure_grantable(auth, roles)
    user = User(full_name=payload.full_name, email=email, password_hash=None, status="active", roles=roles,
                employee_id=resolve_employee_link(db, payload.employee_id))
    db.add(user)
    db.flush()
    invite = create_link(db, user, purpose="invite", lifetime=timedelta(hours=INVITE_LINK_HOURS), created_by=auth.user.id)
    log_activity(db, "user", f"{auth.user.full_name} invited {user.full_name}")
    db.commit()
    record_event("user.invited", category="user", actor=auth.user, target=("user", public_id("user", user.id)),
                 metadata={"roles": [r.name for r in roles], "employee_linked": user.employee_id is not None})
    return {"user": user_dict(db, user), "invite": invite}


@router.patch("/{user_id}", response_model=UserDetail)
def update_user(user_id: str, payload: UserUpdate, auth: Auth = Depends(require_recent("users:manage")), db: DbSession = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    before = {"full_name": user.full_name, "employee_id": user.employee_id}
    user.full_name = payload.full_name
    user.employee_id = resolve_employee_link(db, payload.employee_id, for_user_pk=user.id)
    changed = [f for f in before if before[f] != getattr(user, f)]
    log_activity(db, "user", f"{auth.user.full_name} updated {user.full_name}'s account")
    db.commit()
    if changed:
        record_event("user.updated", category="user", actor=auth.user, target=("user", public_id("user", user.id)),
                     metadata={"fields": changed, **({"employee": public_id("employee", user.employee_id) if user.employee_id else None}
                                                      if "employee_id" in changed else {})})
    return _detail(db, user)


@router.patch("/{user_id}/status", response_model=UserDetail)
def set_user_status(user_id: str, payload: UserStatusUpdate, auth: Auth = Depends(require_recent("users:manage")),
                    db: DbSession = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if user.id == auth.user.id:
        raise ApiError(403, "You can't change the status of your own account.", code="self_change")
    if payload.status == "disabled" and user.status == "active" and active_super_admins(db) == [user.id]:
        raise ApiError(409, "This is the last active Super Administrator. Make someone else Super Administrator first.",
                       code="last_super_admin")
    old_status = user.status
    user.status = payload.status
    if payload.status == "disabled":
        revoke_sessions(db, user.id)  # takes effect immediately, not at the next sign-in
    log_activity(db, "user", f"{auth.user.full_name} {'disabled' if payload.status == 'disabled' else 're-enabled'} {user.full_name}")
    db.commit()
    if old_status != payload.status:
        record_event("user.deactivated" if payload.status == "disabled" else "user.reactivated", category="user",
                     actor=auth.user, target=("user", public_id("user", user.id)), metadata={"from": old_status, "to": payload.status})
    return _detail(db, user)


@router.put("/{user_id}/roles", response_model=UserDetail)
def set_user_roles(user_id: str, payload: UserRolesUpdate, auth: Auth = Depends(require_recent("roles:assign")),
                   db: DbSession = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if user.id == auth.user.id:
        raise ApiError(403, "You can't change your own roles. Ask another administrator.", code="self_change")
    roles = resolve_roles(db, payload.role_ids)
    _ensure_grantable(auth, roles)
    loses_super_admin = any(r.name == SUPER_ADMIN_ROLE for r in user.roles) and not any(r.name == SUPER_ADMIN_ROLE for r in roles)
    if loses_super_admin and user.status == "active" and active_super_admins(db) == [user.id]:
        raise ApiError(409, "This is the last active Super Administrator. Make someone else Super Administrator first.",
                       code="last_super_admin")
    old_roles = sorted(r.name for r in user.roles)
    user.roles = roles
    log_activity(db, "user", f"{auth.user.full_name} set {user.full_name}'s roles to {', '.join(r.label for r in roles)}")
    db.commit()
    record_event("user.roles_changed", category="user", actor=auth.user, target=("user", public_id("user", user.id)),
                 metadata={"from": old_roles, "to": sorted(r.name for r in roles)})
    return _detail(db, user)


@router.post("/{user_id}/reset-link", response_model=LinkOut)
def create_reset_link(user_id: str, auth: Auth = Depends(require_recent("users:manage")), db: DbSession = Depends(get_db)):
    """A single-use, time-limited link that lets the user choose a new password. Hand it over privately."""
    user = get_user_or_404(db, user_id)
    link = create_link(db, user, purpose="reset", lifetime=timedelta(minutes=RESET_LINK_MINUTES), created_by=auth.user.id)
    log_activity(db, "user", f"{auth.user.full_name} created a password-reset link for {user.full_name}")
    db.commit()
    record_event("user.reset_link_created", category="user", actor=auth.user, target=("user", public_id("user", user.id)),
                 metadata={"expires_at": link["expires_at"].isoformat()})
    return link


@router.post("/{user_id}/revoke-sessions")
def end_user_sessions(user_id: str, auth: Auth = Depends(require_recent("users:manage")), db: DbSession = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    ended = revoke_sessions(db, user.id, keep=auth.session.id if user.id == auth.user.id else None)
    log_activity(db, "user", f"{auth.user.full_name} signed {user.full_name} out of {ended} session(s)")
    db.commit()
    record_event("auth.sessions_ended", category="auth", actor=auth.user, target=("user", public_id("user", user.id)),
                 metadata={"ended": ended, "scope": "by administrator"})
    return {"ended": ended}
