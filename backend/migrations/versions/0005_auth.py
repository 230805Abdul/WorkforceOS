"""auth: users, roles, permissions, sessions, password-reset links, auth attempts + the built-in roles

DATA MIGRATION as well: inserts the permission catalog and the five built-in roles with their permissions.
This is a FROZEN COPY of app/auth/permissions.py as it was when this migration was written (migrations must never
import app code). Changing a role later = a new migration (or an administrator using the Roles page).

No user accounts are created here: the first Super Administrator is created with `python -m app.create_admin`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 13:58:30.520040
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("dashboard:view", "Dashboard", "See the dashboard (sections follow the other read permissions)"),
    ("employees:read", "Employees", "View all employee records"),
    ("employees:create", "Employees", "Add employees, including from hired candidates"),
    ("employees:update", "Employees", "Edit employee records"),
    ("employees:delete", "Employees", "Permanently delete employee records"),
    ("departments:read", "Departments", "View departments"),
    ("departments:manage", "Departments", "Create, edit and delete departments"),
    ("jobs:read", "Recruiting", "View jobs"),
    ("jobs:manage", "Recruiting", "Create, edit and delete jobs"),
    ("candidates:read", "Recruiting", "View candidates"),
    ("candidates:manage", "Recruiting", "Create, edit and delete candidates"),
    ("applications:read", "Recruiting", "View applications and the pipeline"),
    ("applications:manage", "Recruiting", "Add applications and move them through the pipeline"),
    ("users:read", "Administration", "View user accounts"),
    ("users:manage", "Administration", "Invite users, edit/disable accounts, create password-reset links, end sessions"),
    ("roles:assign", "Administration", "Change which roles a user has"),
    ("roles:manage", "Administration", "Create, edit and delete roles and their permissions"),
    ("system:demo_reset", "Administration", "Reset all business data to the sample data (development only)"),
    ("profile:own", "Self-service", "View and edit your own profile and linked employee record"),
]
_RECRUITING = ["jobs:read", "jobs:manage", "candidates:read", "candidates:manage", "applications:read", "applications:manage"]
ROLES = [
    ("super_admin", "Super Administrator", "Full access, including user, role and system administration.",
     [code for code, _, _ in PERMISSIONS]),
    ("hr_admin", "HR Administrator", "Runs HR: employees, departments and recruiting. No security administration.",
     ["dashboard:view", "employees:read", "employees:create", "employees:update", "departments:read", "departments:manage",
      "profile:own", *_RECRUITING]),
    ("hr_manager", "HR Manager", "Reviews workforce and recruiting data and moves candidates through the pipeline.",
     ["dashboard:view", "employees:read", "departments:read", "jobs:read", "candidates:read", "applications:read",
      "applications:manage", "profile:own"]),
    ("recruiter", "Recruiter", "Manages jobs, candidates and the hiring pipeline. No access to employee records.",
     ["dashboard:view", "departments:read", "profile:own", *_RECRUITING]),
    ("employee", "Employee", "Self-service only: own profile and own employee record.", ["profile:own"]),
]


def _insert_catalog() -> None:
    bind = op.get_bind()
    permissions = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
                           sa.column("group", sa.String), sa.column("description", sa.String))
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("label", sa.String),
                     sa.column("description", sa.String), sa.column("is_system", sa.Boolean),
                     sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime))
    links = sa.table("role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer))
    now = datetime.now(timezone.utc)
    op.bulk_insert(permissions, [{"code": c, "group": g, "description": d} for c, g, d in PERMISSIONS])
    op.bulk_insert(roles, [{"name": n, "label": label, "description": d, "is_system": True, "created_at": now, "updated_at": now}
                           for n, label, d, _ in ROLES])
    perm_ids = dict(bind.execute(sa.select(permissions.c.code, permissions.c.id)).all())
    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    op.bulk_insert(links, [{"role_id": role_ids[name], "permission_id": perm_ids[code]}
                           for name, _, _, codes in ROLES for code in codes])


def upgrade() -> None:
    op.create_table('auth_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('succeeded', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('login', 'register', 'reset')", name=op.f('ck_auth_attempts_kind_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_attempts'))
    )
    op.create_index(op.f('ix_auth_attempts_created_at'), 'auth_attempts', ['created_at'], unique=False)
    op.create_index('ix_auth_attempts_kind_email_created', 'auth_attempts', ['kind', sa.text('lower(email)'), 'created_at'], unique=False)
    op.create_index('ix_auth_attempts_kind_ip_created', 'auth_attempts', ['kind', 'ip', 'created_at'], unique=False)
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('group', sa.String(length=40), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_permissions')),
    sa.UniqueConstraint('code', name=op.f('uq_permissions_code'))
    )
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('is_system', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('name = lower(name)', name=op.f('ck_roles_name_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('name', name=op.f('uq_roles_name'))
    )
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], name=op.f('fk_role_permissions_permission_id_permissions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_role_permissions_role_id_roles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_role_permissions'))
    )
    op.create_index(op.f('ix_role_permissions_permission_id'), 'role_permissions', ['permission_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('is_sample', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f('ck_users_status_valid')),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_users_employee_id_employees'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('employee_id', name=op.f('uq_users_employee_id'))
    )
    op.create_index(op.f('ix_users_status'), 'users', ['status'], unique=False)
    op.create_index('uq_users_email_lower', 'users', [sa.text('lower(email)')], unique=True)
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=10), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("purpose IN ('reset', 'invite')", name=op.f('ck_password_reset_tokens_purpose_valid')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_created_by_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_password_reset_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_password_reset_tokens_token_hash'))
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('remember', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('user_roles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_user_roles_role_id_roles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_roles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'role_id', name=op.f('pk_user_roles'))
    )
    op.create_index(op.f('ix_user_roles_role_id'), 'user_roles', ['role_id'], unique=False)

    _insert_catalog()

def downgrade() -> None:
    op.drop_index(op.f('ix_user_roles_role_id'), table_name='user_roles')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_index(op.f('ix_users_status'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_role_permissions_permission_id'), table_name='role_permissions')
    op.drop_table('role_permissions')
    op.drop_table('roles')
    op.drop_table('permissions')
    op.drop_index('ix_auth_attempts_kind_ip_created', table_name='auth_attempts')
    op.drop_index('ix_auth_attempts_kind_email_created', table_name='auth_attempts')
    op.drop_index(op.f('ix_auth_attempts_created_at'), table_name='auth_attempts')
    op.drop_table('auth_attempts')
