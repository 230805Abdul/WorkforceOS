"""/api/roles and /api/permissions: inspect and edit roles (Super Administrators by default)."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession, selectinload

from app.audit import record_event
from app.auth.dependencies import Auth, require_any, require_recent
from app.auth.models import Permission, Role, UserRole
from app.auth.permissions import LOCKED_ROLES
from app.auth.schemas import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.db import get_db
from app.errors import ApiError
from app.ids import parse_id, public_id
from app.services import log_activity

router = APIRouter(tags=["roles"])
can_view = require_any("users:read", "roles:assign", "roles:manage")


def _role_dict(db: DbSession, role: Role) -> dict:
    users = db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id))
    return {"id": public_id("role", role.id), "name": role.name, "label": role.label, "description": role.description,
            "is_system": role.is_system, "locked": role.name in LOCKED_ROLES,
            "permissions": [p.code for p in role.permissions], "users_count": users}


def _get_role(db: DbSession, role_id: str) -> Role:
    pk = parse_id("role", role_id)
    role = db.scalar(select(Role).options(selectinload(Role.permissions)).where(Role.id == pk)) if pk else None
    if role is None:
        raise ApiError(404, "Role not found")
    return role


def _permissions(db: DbSession, auth: Auth, codes: list[str]) -> list[Permission]:
    found = db.scalars(select(Permission).where(Permission.code.in_(set(codes)))).all()
    if len(found) != len(set(codes)):
        raise ApiError(422, "Please fix the highlighted fields.", {"permissions": "Unknown permission"})
    if not {p.code for p in found} <= auth.permissions:
        raise ApiError(403, "You can't grant permissions you don't have yourself.", code="privilege_escalation")
    return list(found)


@router.get("/permissions", response_model=list[PermissionOut], dependencies=[Depends(can_view)])
def list_permissions(db: DbSession = Depends(get_db)):
    return db.scalars(select(Permission).order_by(Permission.group, Permission.code)).all()


@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(can_view)])
def list_roles(db: DbSession = Depends(get_db)):
    roles = db.scalars(select(Role).options(selectinload(Role.permissions)).order_by(Role.is_system.desc(), Role.id)).all()
    return [_role_dict(db, r) for r in roles]


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(payload: RoleCreate, auth: Auth = Depends(require_recent("roles:manage")), db: DbSession = Depends(get_db)):
    if db.scalar(select(Role.id).where(Role.name == payload.name)) is not None:
        raise ApiError(409, "Please fix the highlighted fields.", {"name": "A role with this name already exists"})
    role = Role(name=payload.name, label=payload.label, description=payload.description, is_system=False,
                permissions=_permissions(db, auth, payload.permissions))
    db.add(role)
    log_activity(db, "role", f"{auth.user.full_name} created the role '{role.label}'")
    db.commit()
    record_event("role.created", category="role", actor=auth.user, target=("role", public_id("role", role.id)),
                 metadata={"name": role.name, "permissions": sorted(p.code for p in role.permissions)})
    return _role_dict(db, role)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: str, payload: RoleUpdate, auth: Auth = Depends(require_recent("roles:manage")), db: DbSession = Depends(get_db)):
    role = _get_role(db, role_id)
    new_codes = sorted(set(payload.permissions))
    if role.name in LOCKED_ROLES and new_codes != sorted(p.code for p in role.permissions):
        raise ApiError(409, f"The permissions of '{role.label}' can't be changed (it must always be able to administer the system).",
                       code="locked_role")
    before = {p.code for p in role.permissions}
    role.label, role.description = payload.label, payload.description
    if role.name not in LOCKED_ROLES:
        role.permissions = _permissions(db, auth, new_codes)
    log_activity(db, "role", f"{auth.user.full_name} updated the role '{role.label}'")
    db.commit()
    after = {p.code for p in role.permissions}
    record_event("role.updated", category="role", actor=auth.user, target=("role", public_id("role", role.id)),
                 metadata={"name": role.name, "permissions_added": sorted(after - before), "permissions_removed": sorted(before - after)})
    return _role_dict(db, role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(role_id: str, auth: Auth = Depends(require_recent("roles:manage")), db: DbSession = Depends(get_db)):
    role = _get_role(db, role_id)
    if role.is_system:
        raise ApiError(409, "Built-in roles can't be deleted.", code="system_role")
    users = db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id))
    if users:
        raise ApiError(409, f"'{role.label}' is still assigned to {users} user(s). Remove it from them first.", code="role_in_use")
    log_activity(db, "role", f"{auth.user.full_name} deleted the role '{role.label}'")
    target = ("role", public_id("role", role.id))
    db.delete(role)
    db.commit()
    record_event("role.deleted", category="role", actor=auth.user, target=target, metadata={"name": role.name})
    return Response(status_code=204)
