"""Test setup.

The schema is built by the REAL Alembic migrations (not create_all), so every run also proves the migrations work.
Each test starts with fresh business sample data, one account per built-in role (see USERS) and the built-in roles
reset to their default permissions.

By default tests use a throw-away SQLite file, so `pytest` works with nothing installed.
To run the SAME tests against PostgreSQL (recommended; some tests only run there):

    TEST_DATABASE_URL=postgresql+psycopg://workforceos:YOUR_PASSWORD@localhost:5432/workforceos_test pytest

The database must be a *test* database: its name has to contain "test", so a typo can never wipe your real data.
"""
import os
import tempfile
from pathlib import Path

# Must happen BEFORE any `app` import: app.config reads the environment once, at import time.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["ENABLE_DEMO_RESET"] = "true"
os.environ["APP_ENV"] = "development"
os.environ["PASSWORD_HASH_PROFILE"] = "fast"  # cheap Argon2 so the suite runs in seconds (refused in production)
os.environ["REGISTRATION_ENABLED"] = "true"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # the suite makes thousands of requests a minute; tests/test_security.py
                                            # builds apps WITH limits to test them
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.auth.models import AuthAttempt, PasswordResetToken, Permission, Role, Session, User  # noqa: E402
from app.auth.passwords import hash_password  # noqa: E402
from app.auth.permissions import BUILTIN_ROLES  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Employee  # noqa: E402
from app.seed import reset_tables, seed  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]

# A complete, valid production configuration (nothing connects at import time, so the hosts needn't exist).
PRODUCTION_ENV = {
    "APP_ENV": "production",
    "DATABASE_URL": "postgresql+psycopg://workforceos_app:app-secret@db.internal:5432/workforceos",
    "MIGRATION_DATABASE_URL": "postgresql+psycopg://workforceos:owner-secret@db.internal:5432/workforceos",
    "FRONTEND_ORIGINS": "https://workforceos.example.com",
    "PUBLIC_APP_URL": "https://workforceos.example.com",
    "AUDIT_HMAC_KEY": "0123456789abcdef0123456789abcdef0123456789abcdef",
    "PASSWORD_HASH_PROFILE": "standard",
}
PASSWORD = "Test-Password-For-All-Roles-9"
USERS = {  # role -> (email, full name, linked employee code)
    "super_admin": ("root@test.example.com", "Root Admin", None),
    "hr_admin": ("hradmin@test.example.com", "Hilda Admin", "E-0010"),
    "hr_manager": ("hrmanager@test.example.com", "Hugo Manager", "E-0009"),
    "recruiter": ("recruiter@test.example.com", "Remy Recruiter", None),
    "employee": ("employee@test.example.com", "Aisha Rahman", "E-0003"),
}

if engine.dialect.name != "sqlite" and "test" not in (engine.url.database or ""):
    pytest.exit(f"Refusing to run tests against '{engine.url.database}': the database name must contain 'test'.", returncode=2)


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


_MIGRATED = False


def ensure_migrated() -> None:
    """Bring the test database to the newest migration once per test run (a no-op when already there), so a test
    database left behind by an older version of the project is upgraded exactly like a real one would be."""
    global _MIGRATED
    if not _MIGRATED:
        command.upgrade(alembic_config(), "head")
        _MIGRATED = True


_HASH = None


def reset_accounts(db) -> None:
    """Delete every account/session/attempt, restore built-in roles, then create one account per role."""
    global _HASH
    _HASH = _HASH or hash_password(PASSWORD)  # hashed once per test run
    for model in (Session, PasswordResetToken, AuthAttempt, User):
        db.execute(delete(model))
    db.execute(delete(Role).where(Role.is_system.is_(False)))
    perms = {p.code: p for p in db.scalars(select(Permission)).all()}
    roles = {r.name: r for r in db.scalars(select(Role)).all()}
    for builtin in BUILTIN_ROLES:
        roles[builtin.name].permissions = [perms[c] for c in sorted(builtin.permissions)]
    for role, (email, name, code) in USERS.items():
        employee_id = db.scalar(select(Employee.id).where(Employee.employee_code == code)) if code else None
        db.add(User(full_name=name, email=email, password_hash=_HASH, status="active", roles=[roles[role]], employee_id=employee_id))
    db.commit()


@pytest.fixture(autouse=True)
def fresh_data():
    ensure_migrated()
    with SessionLocal() as db:
        reset_tables(db)
        seed(db)
        reset_accounts(db)


def sign_in(email: str, password: str = PASSWORD, *, remember: bool = False, target=None, headers=None) -> TestClient:
    c = TestClient(target or app, raise_server_exceptions=False, headers=headers)
    r = c.post("/api/auth/login", json={"email": email, "password": password, "remember": remember})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]  # what the frontend does with the token from /auth/login or /auth/me
    return c


@pytest.fixture
def as_role():
    """as_role("hr_admin") -> a TestClient signed in as that role's test user."""
    return lambda role: sign_in(USERS[role][0])


@pytest.fixture
def client():
    """Signed in as Super Administrator, so the business-logic tests can focus on business logic."""
    return sign_in(USERS["super_admin"][0])


@pytest.fixture
def anon():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
