"""Account helpers shared by the auth, users and roles routers."""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.auth.models import PasswordResetToken, Role, User, UserRole
from app.auth.passwords import new_token, policy_problem, token_hash
from app.auth.permissions import SUPER_ADMIN_ROLE
from app.config import PUBLIC_APP_URL
from app.errors import ApiError
from app.ids import parse_id, public_id
from app.models import Employee, utcnow


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user_by_email(db: DbSession, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))


def check_new_password(password: str, confirm: str, *, email: str, full_name: str,
                       field: str = "password", confirm_field: str = "password_confirm") -> None:
    errors = {}
    if (problem := policy_problem(password, email=email, full_name=full_name)) is not None:
        errors[field] = problem
    if password != confirm:
        errors[confirm_field] = "Passwords do not match"
    if errors:
        raise ApiError(422, "Please fix the highlighted fields.", errors)


def user_query():
    return select(User).options(selectinload(User.roles))


def get_user_or_404(db: DbSession, user_id: str) -> User:
    pk = parse_id("user", user_id)
    user = db.scalar(user_query().where(User.id == pk)) if pk else None
    if user is None:
        raise ApiError(404, "User not found")
    return user


def user_dict(db: DbSession, user: User) -> dict:
    employee = db.get(Employee, user.employee_id) if user.employee_id else None
    return {
        "id": public_id("user", user.id), "full_name": user.full_name, "email": user.email, "status": user.status,
        "roles": [{"id": public_id("role", r.id), "name": r.name, "label": r.label} for r in user.roles],
        "employee": None if employee is None else {
            "id": public_id("employee", employee.id), "employee_code": employee.employee_code,
            "full_name": f"{employee.first_name} {employee.last_name}", "department": employee.department.name},
        "has_password": user.password_hash is not None, "is_sample": user.is_sample,
        "last_login_at": user.last_login_at, "created_at": user.created_at,
    }


def resolve_roles(db: DbSession, role_ids: list[str], field: str = "role_ids") -> list[Role]:
    pks = {parse_id("role", r) for r in role_ids}
    roles = db.scalars(select(Role).where(Role.id.in_({p for p in pks if p}))).all() if pks else []
    if None in pks or len(roles) != len(pks):
        raise ApiError(422, "Please fix the highlighted fields.", {field: "Select valid roles"})
    return list(roles)


def resolve_employee_link(db: DbSession, employee_id: str | None, *, for_user_pk: int | None = None) -> int | None:
    """Employee to link to an account; each employee can belong to at most one account."""
    if not employee_id:
        return None
    pk = parse_id("employee", employee_id)
    if pk is None or db.get(Employee, pk) is None:
        raise ApiError(422, "Please fix the highlighted fields.", {"employee_id": "Select a valid employee"})
    owner = db.scalar(select(User.id).where(User.employee_id == pk))
    if owner is not None and owner != for_user_pk:
        raise ApiError(409, "Please fix the highlighted fields.", {"employee_id": "This employee is already linked to another account"})
    return pk


def active_super_admins(db: DbSession) -> list[int]:
    return list(db.scalars(
        select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(Role.name == SUPER_ADMIN_ROLE, User.status == "active")
    ).all())


def create_link(db: DbSession, user: User, *, purpose: str, lifetime: timedelta, created_by: int | None) -> dict:
    """Make a single-use link. Any older unused link for the same user stops working."""
    now = utcnow()
    for old in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                          PasswordResetToken.used_at.is_(None))).all():
        old.used_at = now  # superseded
    token = new_token()
    row = PasswordResetToken(user_id=user.id, token_hash=token_hash(token), purpose=purpose,
                             created_by_user_id=created_by, created_at=now, expires_at=now + lifetime)
    db.add(row)
    return {"url": f"{PUBLIC_APP_URL}/reset-password?token={token}", "expires_at": row.expires_at}
