"""The command-line tools: creating the first Super Administrator, and the development-only demo accounts."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from app.auth.models import User
from tests.conftest import USERS, sign_in

BACKEND = Path(__file__).resolve().parents[1]


def _run(args: list[str], stdin: str = "", **env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", *args], cwd=BACKEND, input=stdin, capture_output=True, text=True,
                          env={**os.environ, **env})


def test_create_admin_creates_a_super_administrator_who_can_sign_in(db):
    r = _run(["app.create_admin", "--email", "Owner@Company.example.com", "--name", "Olga Owner", "--password-stdin"],
             "quiet-river-granite-33\n")
    assert r.returncode == 0, r.stdout + r.stderr
    user = db.scalar(select(User).where(User.email == "owner@company.example.com"))
    assert [role.name for role in user.roles] == ["super_admin"] and user.password_hash.startswith("$argon2id$")
    c = sign_in("owner@company.example.com", "quiet-river-granite-33")
    assert c.get("/api/users").status_code == 200


def test_create_admin_refuses_weak_passwords_and_duplicates(db):
    weak = _run(["app.create_admin", "--email", "x@company.example.com", "--name", "X Y", "--password-stdin"], "short\n")
    assert weak.returncode != 0 and "at least 12" in weak.stderr
    dup = _run(["app.create_admin", "--email", USERS["hr_admin"][0], "--name", "Dup", "--password-stdin"], "quiet-river-granite-33\n")
    assert dup.returncode != 0 and "--promote" in dup.stderr
    assert db.scalar(select(User).where(User.email == "x@company.example.com")) is None


def test_create_admin_can_promote_an_existing_account():
    r = _run(["app.create_admin", "--email", USERS["employee"][0], "--promote"])
    assert r.returncode == 0, r.stderr
    assert sign_in(USERS["employee"][0]).get("/api/users").status_code == 200


def test_demo_accounts_are_refused_in_production():
    from tests.conftest import PRODUCTION_ENV

    r = _run(["app.seed", "--demo-users"], **PRODUCTION_ENV)
    assert r.returncode == 2 and "Refusing" in r.stdout


def test_demo_accounts_work_and_survive_a_demo_reset(client):
    r = _run(["app.seed", "--demo-users"])
    assert r.returncode == 0 and "admin@demo.example.com" in r.stdout
    demo = sign_in("employee@demo.example.com", "WorkforceOS-demo-2026")
    assert client.post("/api/demo/reset").status_code == 200
    assert demo.get("/api/me/employee").json()["employee_code"] == "E-0003"  # still signed in, link restored
