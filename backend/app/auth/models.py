"""Tables for accounts and access control. (Business tables live in app/models.py.)

    users >──< roles >──< permissions        (user_roles, role_permissions: many-to-many)
    users 0..1 ── 0..1 employees             (users.employee_id: an account MAY be linked to one employee record)
    users 1 ──< sessions                     (one row per signed-in browser)
    users 1 ──< password_reset_tokens        (single-use, time-limited links)
    auth_attempts                            (login/registration/reset attempts, for rate limiting)

Secrets are never stored as-is: passwords are Argon2id hashes, session and reset tokens are stored as SHA-256 hashes,
so a copy of the database cannot be used to sign in.
"""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models import utcnow


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # e.g. "employees:update"
    group: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(200))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True, index=True)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("name = lower(name)", name="name_lowercase"),)  # full format checked by the API

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)  # machine name, e.g. "hr_admin"
    label: Mapped[str] = mapped_column(String(60))               # shown in the UI, e.g. "HR Administrator"
    description: Mapped[str | None] = mapped_column(String(300))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # built-in: can't be renamed/deleted
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    permissions: Mapped[list[Permission]] = relationship(secondary="role_permissions", order_by=Permission.code)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # RESTRICT: a role that is still assigned to someone can't be deleted by accident.
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True, index=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    # NULL = no password yet (invited, hasn't set one). Such accounts can't sign in until they use their link.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # Optional link to the employee record this person IS. Unique: one account per employee and vice versa.
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), unique=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", order_by=Role.name)


Index("uq_users_email_lower", func.lower(User.email), unique=True)


class Session(Base):
    """One signed-in browser. The cookie holds a random token; only its SHA-256 hash is stored here."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))  # must be echoed in the X-CSRF-Token header on changes
    remember: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)  # absolute limit
    # Last time the password was typed in this session (sign-in or "confirm your password"). High-impact admin
    # actions require this to be recent (REAUTH_MINUTES): a stolen or unattended session alone isn't enough.
    reauthenticated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))


class PasswordResetToken(Base):
    """A single-use, time-limited link that lets someone set a new password (reset or invitation)."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('reset', 'invite')", name="purpose_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(10), default="reset")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuthAttempt(Base):
    """Every sign-in / registration / reset attempt, so the rate limiter works across restarts and processes."""

    __tablename__ = "auth_attempts"
    __table_args__ = (CheckConstraint("kind IN ('login', 'register', 'reset')", name="kind_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(254))
    ip: Mapped[str | None] = mapped_column(String(45))
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


Index("ix_auth_attempts_kind_email_created", AuthAttempt.kind, func.lower(AuthAttempt.email), AuthAttempt.created_at)
Index("ix_auth_attempts_kind_ip_created", AuthAttempt.kind, AuthAttempt.ip, AuthAttempt.created_at)
