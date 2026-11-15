"""Request/response shapes for accounts. Every INPUT model forbids unknown fields (extra="forbid"): a request that
tries to sneak in {"roles": [...]} or {"status": "active"} is rejected with 422 instead of silently ignored or applied.
That is the mass-assignment protection. Responses never include password hashes or token hashes.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints

from app.validation import SecretText, text

Name = text(2, 120)
Secret = SecretText  # never stripped: spaces are allowed; NUL refused


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- public ----------
class RegisterIn(Strict):
    full_name: Name
    email: EmailStr
    password: Secret
    password_confirm: Secret


class LoginIn(Strict):
    email: EmailStr
    password: Secret
    remember: bool = False


class ResetPasswordIn(Strict):
    token: Annotated[str, StringConstraints(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")]
    new_password: Secret
    new_password_confirm: Secret


# ---------- signed in: own account ----------
class ProfileUpdate(Strict):
    full_name: Name  # the ONLY thing you can change about your own account here (no e-mail, roles or status)


class ReauthIn(Strict):
    password: Secret


class SignInOut(BaseModel):
    at: datetime
    outcome: Literal["success", "failure", "denied"]
    ip: str | None
    user_agent: str | None
    new_device: bool
    reason: str | None


class ChangePasswordIn(Strict):
    current_password: Secret
    new_password: Secret
    new_password_confirm: Secret


class OwnEmployeeUpdate(Strict):
    phone: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9+()\-\s]{7,20}$")] | None = None


# ---------- administration ----------
class RoleRef(BaseModel):
    id: str
    name: str
    label: str


class EmployeeRef(BaseModel):
    id: str
    employee_code: str
    full_name: str
    department: str


class UserOut(BaseModel):
    id: str
    full_name: str
    email: str
    status: Literal["active", "disabled"]
    roles: list[RoleRef]
    employee: EmployeeRef | None
    has_password: bool
    is_sample: bool
    last_login_at: datetime | None
    created_at: datetime


class UserDetail(UserOut):
    active_sessions: int


class MeOut(UserOut):
    permissions: list[str]
    csrf_token: str


class UserInvite(Strict):
    full_name: Name
    email: EmailStr
    role_ids: list[str] = Field(default_factory=list, max_length=20)  # empty -> the default "Employee" role
    employee_id: str | None = None


class UserUpdate(Strict):
    full_name: Name
    employee_id: str | None = None  # link/unlink the employee record this account belongs to


class UserStatusUpdate(Strict):
    status: Literal["active", "disabled"]


class UserRolesUpdate(Strict):
    role_ids: list[str] = Field(min_length=1, max_length=20)


class LinkOut(BaseModel):
    url: str
    expires_at: datetime


class InviteOut(BaseModel):
    user: UserOut
    invite: LinkOut


class PermissionOut(BaseModel):
    code: str
    group: str
    description: str


class RoleOut(BaseModel):
    id: str
    name: str
    label: str
    description: str | None
    is_system: bool
    locked: bool  # permissions can't be edited (super_admin)
    permissions: list[str]
    users_count: int


RoleName = Annotated[str, BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v),
                     StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,39}$")]
Label = text(2, 60)
Description = text(0, 300)


class RoleCreate(Strict):
    name: RoleName
    label: Label
    description: Description | None = None
    permissions: list[str] = Field(default_factory=list, max_length=100)


class RoleUpdate(Strict):
    label: Label
    description: Description | None = None
    permissions: list[str] = Field(default_factory=list, max_length=100)
