"""THE single place where permissions and the built-in roles are defined.

* The API checks permissions, never role names:   Depends(require("employees:update"))
* Roles are just named bundles of permissions, stored in the database (roles, role_permissions), so an administrator
  can adjust them or create new roles without code changes.
* A user's effective permissions are the union of the permissions of all their roles.

If you add a permission here, add a migration that inserts it and grants it to the roles that need it
(at least super_admin). tests/test_authorization.py fails if the database and this file disagree.
"""
from dataclasses import dataclass

# code -> (group shown in the admin UI, description)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "dashboard:view": ("Dashboard", "See the dashboard (sections follow the other read permissions)"),
    "employees:read": ("Employees", "View all employee records"),
    "employees:create": ("Employees", "Add employees, including from hired candidates"),
    "employees:update": ("Employees", "Edit employee records"),
    "employees:delete": ("Employees", "Permanently delete employee records"),
    "departments:read": ("Departments", "View departments"),
    "departments:manage": ("Departments", "Create, edit and delete departments"),
    "jobs:read": ("Recruiting", "View jobs"),
    "jobs:manage": ("Recruiting", "Create, edit and delete jobs"),
    "candidates:read": ("Recruiting", "View candidates"),
    "candidates:manage": ("Recruiting", "Create, edit and delete candidates"),
    "applications:read": ("Recruiting", "View applications and the pipeline"),
    "applications:manage": ("Recruiting", "Add applications and move them through the pipeline"),
    "users:read": ("Administration", "View user accounts"),
    "users:manage": ("Administration", "Invite users, edit/disable accounts, create password-reset links, end sessions"),
    "roles:assign": ("Administration", "Change which roles a user has"),
    "roles:manage": ("Administration", "Create, edit and delete roles and their permissions"),
    "system:demo_reset": ("Administration", "Reset all business data to the sample data (development only)"),
    "audit:read": ("Administration", "View the audit log and security events, and verify its integrity"),
    "profile:own": ("Self-service", "View and edit your own profile and linked employee record"),
}


@dataclass(frozen=True)
class BuiltinRole:
    name: str
    label: str
    description: str
    permissions: frozenset[str]


_RECRUITING = {"jobs:read", "jobs:manage", "candidates:read", "candidates:manage", "applications:read", "applications:manage"}

BUILTIN_ROLES: list[BuiltinRole] = [
    BuiltinRole("super_admin", "Super Administrator", "Full access, including user, role and system administration.",
                frozenset(PERMISSIONS)),
    BuiltinRole("hr_admin", "HR Administrator", "Runs HR: employees, departments and recruiting. No security administration.",
                frozenset({"dashboard:view", "employees:read", "employees:create", "employees:update",
                           "departments:read", "departments:manage", "profile:own"} | _RECRUITING)),
    BuiltinRole("hr_manager", "HR Manager", "Reviews workforce and recruiting data and moves candidates through the pipeline.",
                frozenset({"dashboard:view", "employees:read", "departments:read", "jobs:read", "candidates:read",
                           "applications:read", "applications:manage", "profile:own"})),
    BuiltinRole("recruiter", "Recruiter", "Manages jobs, candidates and the hiring pipeline. No access to employee records.",
                frozenset({"dashboard:view", "departments:read", "profile:own"} | _RECRUITING)),
    BuiltinRole("employee", "Employee", "Self-service only: own profile and own employee record.",
                frozenset({"profile:own"})),
]

DEFAULT_ROLE = "employee"          # what public registration and invitations without roles get
SUPER_ADMIN_ROLE = "super_admin"   # the system must always keep at least one active user with this role
LOCKED_ROLES = {SUPER_ADMIN_ROLE}  # roles whose permissions can't be edited (prevents locking everyone out)

# An explicit check, not `assert`: assertions vanish when Python runs with -O.
_unknown = {p for r in BUILTIN_ROLES for p in r.permissions} - set(PERMISSIONS)
if _unknown:
    raise RuntimeError(f"unknown permission(s) in BUILTIN_ROLES: {sorted(_unknown)}")
