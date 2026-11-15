"""/api/auth: sign-up, sign-in, sign-out, "who am I", own profile, password change and reset-by-link, re-authentication.

There is no /auth/refresh: WorkforceOS uses server-side sessions (see docs/AUTH.md), not JWTs, so there is no
access token to refresh. Session lifetime is handled on the server.
Every security-relevant step writes an audit record (app/audit.py); passwords and tokens are never recorded.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from app.audit import AuditEvent, record_event
from app.auth import rate_limit
from app.auth.dependencies import Auth, effective_permissions, get_auth, require
from app.auth.models import PasswordResetToken, Role, User
from app.auth.passwords import MAX_LENGTH, MIN_LENGTH, POLICY_TEXT, hash_password, needs_rehash, token_hash, verify_password
from app.auth.permissions import DEFAULT_ROLE
from app.auth.schemas import (ChangePasswordIn, LoginIn, MeOut, ProfileUpdate, ReauthIn, RegisterIn, ResetPasswordIn,
                              SignInOut)
from app.auth.service import check_new_password, find_user_by_email, normalize_email, user_dict
from app.auth.sessions import (clear_session_cookie, client_ip, create_session, end_presented_session, revoke_sessions,
                               set_session_cookie)
from app.config import REAUTH_MINUTES, REGISTRATION_ENABLED
from app.db import get_db
from app.errors import SESSION_COOKIE, ApiError
from app.ids import public_id
from app.models import utcnow
from app.services import log_activity

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_LOGIN = "Incorrect email or password."  # same message whether the e-mail exists or not (no enumeration)


def _target(user: User) -> tuple[str, str]:
    return ("user", public_id("user", user.id))


def me_dict(db: DbSession, auth_user: User, csrf_token: str) -> dict:
    return {**user_dict(db, auth_user), "permissions": sorted(effective_permissions(db, auth_user.id)), "csrf_token": csrf_token}


def _is_new_device(db: DbSession, user: User, request: Request) -> bool:
    """Suspicious-sign-in signal: this address + browser hasn't been seen in the user's last 20 successful sign-ins.
    (The very first sign-in isn't flagged.) Shown under My profile -> Recent sign-ins, and recorded as a security event."""
    seen = db.execute(select(AuditEvent.ip, AuditEvent.user_agent).where(
        AuditEvent.action == "auth.login", AuditEvent.outcome == "success", AuditEvent.actor_user_id == user.id,
    ).order_by(AuditEvent.id.desc()).limit(20)).all()
    here = (client_ip(request), (request.headers.get("user-agent") or "")[:200] or None)
    return bool(seen) and here not in {tuple(row) for row in seen}


def _start_session(db: DbSession, user: User, *, remember: bool, request: Request, response: Response) -> dict:
    end_presented_session(db, request)  # session fixation: whatever session this browser had before is ended
    token, session = create_session(db, user, remember=remember, request=request)
    user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(response, token, session)
    return me_dict(db, user, session.csrf_token)


@router.get("/config")
def auth_config():
    """Public: what the sign-in/sign-up pages need to know."""
    return {"registration_enabled": REGISTRATION_ENABLED, "reauth_minutes": REAUTH_MINUTES,
            "password_policy": {"min_length": MIN_LENGTH, "max_length": MAX_LENGTH, "text": POLICY_TEXT}}


@router.post("/register", response_model=MeOut, status_code=201)
def register(payload: RegisterIn, request: Request, response: Response, db: DbSession = Depends(get_db)):
    if not REGISTRATION_ENABLED:
        raise ApiError(403, "Self-registration is turned off. Ask an administrator for an invitation.", code="registration_disabled")
    email, ip = normalize_email(payload.email), client_ip(request)
    rate_limit.check(db, "register", email=email, ip=ip)
    rate_limit.record(db, "register", email=email, ip=ip, succeeded=False)
    check_new_password(payload.password, payload.password_confirm, email=email, full_name=payload.full_name)
    if find_user_by_email(db, email) is not None:
        # Note: this does reveal that the e-mail has an account. Unavoidable without e-mail verification;
        # mitigated by the registration rate limit (see docs/AUTH.md, "Known limitations").
        raise ApiError(409, "Please fix the highlighted fields.", {"email": "An account with this email already exists"})

    default_role = db.scalar(select(Role).where(Role.name == DEFAULT_ROLE))
    # The role is decided HERE, never by the request: RegisterIn has no role field and forbids extra fields.
    user = User(full_name=payload.full_name, email=email, password_hash=hash_password(payload.password), status="active",
                password_changed_at=utcnow(), roles=[default_role] if default_role else [])
    db.add(user)
    db.flush()
    log_activity(db, "user", f"{user.full_name} created an account")
    result = _start_session(db, user, remember=False, request=request, response=response)
    record_event("auth.register", category="auth", actor=user, target=_target(user), metadata={"role": DEFAULT_ROLE})
    return result


@router.post("/login", response_model=MeOut)
def login(payload: LoginIn, request: Request, response: Response, db: DbSession = Depends(get_db)):
    email, ip = normalize_email(payload.email), client_ip(request)
    rate_limit.check(db, "login", email=email, ip=ip)
    user = find_user_by_email(db, email)
    ok = verify_password(user.password_hash if user else None, payload.password)  # same effort when user is unknown
    rate_limit.record(db, "login", email=email, ip=ip, succeeded=ok)
    if not ok:
        record_event("auth.login", category="auth", outcome="failure", target=_target(user) if user else None,
                     metadata={"reason": "invalid_credentials", "email": email, "account_exists": user is not None})
        raise ApiError(401, INVALID_LOGIN, code="invalid_credentials")
    if user.status != "active":
        # Only revealed AFTER the correct password, so it can't be used to discover accounts.
        record_event("auth.login", category="auth", outcome="denied", target=_target(user), metadata={"reason": "account_disabled"})
        raise ApiError(403, "This account has been disabled. Contact your administrator.", code="account_disabled")
    if needs_rehash(user.password_hash):  # transparently upgrade old hash parameters
        user.password_hash = hash_password(payload.password)
    new_device = _is_new_device(db, user, request)
    result = _start_session(db, user, remember=payload.remember, request=request, response=response)
    record_event("auth.login", category="auth", actor=user, target=_target(user),
                 metadata={"remember": payload.remember, "new_device": new_device})
    if new_device:
        record_event("security.new_device_sign_in", category="security", actor=user, target=_target(user))
    return result


@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, db: DbSession = Depends(get_db)):
    """Ends THIS browser's session. Works even if the session already expired (then it just clears the cookie)."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            auth = get_auth(request, db)  # also enforces the CSRF header for a live session
        except ApiError as exc:
            if exc.code == "csrf_failed":
                raise
        else:
            db.delete(auth.session)
            db.commit()
            record_event("auth.logout", category="auth", actor=auth.user, target=_target(auth.user))
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(auth: Auth = Depends(get_auth), db: DbSession = Depends(get_db)):
    """Who am I, what may I do, and the CSRF token for this session. Called on every page load."""
    return me_dict(db, auth.user, auth.session.csrf_token)


@router.patch("/me", response_model=MeOut)
def update_profile(payload: ProfileUpdate, auth: Auth = Depends(require("profile:own")), db: DbSession = Depends(get_db)):
    changed = auth.user.full_name != payload.full_name
    auth.user.full_name = payload.full_name
    db.commit()
    if changed:
        record_event("user.profile_updated", category="user", actor=auth.user, target=_target(auth.user),
                     metadata={"fields": ["full_name"]})
    return me_dict(db, auth.user, auth.session.csrf_token)


@router.get("/me/sign-ins", response_model=list[SignInOut])
def my_sign_ins(auth: Auth = Depends(require("profile:own")), db: DbSession = Depends(get_db)):
    """Your recent sign-in attempts (successful and failed), so you can spot ones that weren't you."""
    target_id = public_id("user", auth.user.id)
    rows = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "auth.login", AuditEvent.target_type == "user", AuditEvent.target_id == target_id,
    ).order_by(AuditEvent.id.desc()).limit(15)).all()
    return [{"at": e.occurred_at, "outcome": e.outcome, "ip": e.ip, "user_agent": e.user_agent,
             "new_device": bool((e.details or {}).get("new_device")), "reason": (e.details or {}).get("reason")} for e in rows]


@router.post("/reauthenticate")
def reauthenticate(payload: ReauthIn, request: Request, auth: Auth = Depends(get_auth), db: DbSession = Depends(get_db)):
    """Confirm your password to unlock high-impact actions for REAUTH_MINUTES ("sudo mode")."""
    user, ip = auth.user, client_ip(request)
    rate_limit.check(db, "login", email=user.email, ip=ip)  # counts towards the same budget as sign-in attempts
    ok = verify_password(user.password_hash, payload.password)
    rate_limit.record(db, "login", email=user.email, ip=ip, succeeded=ok)
    if not ok:
        record_event("auth.reauthenticate", category="auth", outcome="failure", actor=user, target=_target(user))
        raise ApiError(422, "Please fix the highlighted fields.", {"password": "Incorrect password"})  # nosec B105 # error message, not a password
    now = utcnow()
    auth.session.reauthenticated_at = now
    db.commit()
    record_event("auth.reauthenticate", category="auth", actor=user, target=_target(user))
    return {"confirmed_until": now + timedelta(minutes=REAUTH_MINUTES)}


@router.post("/change-password", status_code=204)
def change_password(payload: ChangePasswordIn, request: Request, auth: Auth = Depends(get_auth), db: DbSession = Depends(get_db)):
    user, ip = auth.user, client_ip(request)
    rate_limit.check(db, "login", email=user.email, ip=ip)  # stops guessing the current password from a stolen session
    if not verify_password(user.password_hash, payload.current_password):
        rate_limit.record(db, "login", email=user.email, ip=ip, succeeded=False)
        record_event("auth.password_changed", category="auth", outcome="failure", actor=user, target=_target(user),
                     metadata={"reason": "wrong_current_password"})
        raise ApiError(422, "Please fix the highlighted fields.", {"current_password": "Current password is incorrect"})  # nosec B105 # error message, not a password
    check_new_password(payload.new_password, payload.new_password_confirm, email=user.email, full_name=user.full_name,
                       field="new_password", confirm_field="new_password_confirm")
    if verify_password(user.password_hash, payload.new_password):
        raise ApiError(422, "Please fix the highlighted fields.", {"new_password": "Choose a password you haven't used here"})  # nosec B105 # error message, not a password
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utcnow()
    ended = revoke_sessions(db, user.id, keep=auth.session.id)  # sign out every OTHER browser
    auth.session.reauthenticated_at = utcnow()
    db.commit()
    record_event("auth.password_changed", category="auth", actor=user, target=_target(user), metadata={"other_sessions_ended": ended})
    return Response(status_code=204)


@router.post("/logout-others")
def logout_other_sessions(auth: Auth = Depends(require("profile:own")), db: DbSession = Depends(get_db)):
    ended = revoke_sessions(db, auth.user.id, keep=auth.session.id)
    db.commit()
    record_event("auth.sessions_ended", category="auth", actor=auth.user, target=_target(auth.user),
                 metadata={"ended": ended, "scope": "own other sessions"})
    return {"ended": ended}


@router.post("/reset-password", status_code=204)
def reset_password(payload: ResetPasswordIn, request: Request, db: DbSession = Depends(get_db)):
    """Public: set a new password with a single-use link an administrator created (reset or invitation)."""
    ip = client_ip(request)
    rate_limit.check(db, "reset", email=None, ip=ip)
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(payload.token)))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        rate_limit.record(db, "reset", email=None, ip=ip, succeeded=False)
        record_event("auth.password_reset", category="auth", outcome="failure",
                     metadata={"reason": "unknown_token" if row is None else "used" if row.used_at else "expired"})
        raise ApiError(400, "This link is invalid or has expired. Ask your administrator for a new one.", code="invalid_reset_token")
    user = db.get(User, row.user_id)
    check_new_password(payload.new_password, payload.new_password_confirm, email=user.email, full_name=user.full_name,
                       field="new_password", confirm_field="new_password_confirm")
    first_password = user.password_hash is None
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = now
    row.used_at = now  # single use
    ended = revoke_sessions(db, user.id)  # whoever had the old password is signed out everywhere
    db.commit()
    rate_limit.record(db, "reset", email=user.email, ip=ip, succeeded=True)
    record_event("auth.account_activated" if first_password else "auth.password_reset", category="auth", target=_target(user),
                 metadata={"via": row.purpose, "sessions_ended": ended})
    return Response(status_code=204)
