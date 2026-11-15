"""Persistence across a REAL server restart, transaction atomicity, configuration and seed safety."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import ActivityLog, Candidate, Department, Employee, Job
from app.seed import remove_sample, seed

BACKEND = Path(__file__).resolve().parents[1]
EMP = {"employee_code": "E-0500", "first_name": "Persist", "last_name": "Ence", "email": "persist@example.org",
       "job_title": "Archivist", "department_id": "DEP-4006", "employment_status": "active", "joining_date": "2026-03-01"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=0.5).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("server did not start")


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    proc.wait(timeout=10)


def test_records_and_sessions_survive_a_real_backend_restart():
    """Start the real server process, sign in, create records, STOP it, start a NEW process: the records are still
    there, and so is the sign-in (sessions live in PostgreSQL, not in the server's memory)."""
    from tests.conftest import PASSWORD, USERS

    port = _free_port()
    base = f"http://127.0.0.1:{port}/api"
    browser = httpx.Client(base_url=base)  # keeps cookies like a browser
    server = _start_server(port)
    try:
        login = browser.post("/auth/login", json={"email": USERS["super_admin"][0], "password": PASSWORD})
        assert login.status_code == 200
        browser.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        dept = browser.post("/departments", json={"name": "Archives", "code": "ARC"}).json()
        emp = browser.post("/employees", json={**EMP, "department_id": dept["id"]}).json()
        job = browser.post("/jobs", json={"title": "Records Clerk", "department_id": dept["id"], "location": "Remote",
                                          "status": "open", "openings": 1, "description": "Keeps the archive tidy."}).json()
    finally:
        _stop(server)
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{base}/health", timeout=0.5)  # really down

    server = _start_server(port)
    try:
        assert browser.get("/auth/me").json()["email"] == USERS["super_admin"][0]  # still signed in
        assert browser.get(f"/employees/{emp['id']}").json()["full_name"] == "Persist Ence"
        assert browser.get(f"/jobs/{job['id']}").json()["department"] == "Archives"
        d = browser.get(f"/departments/{dept['id']}").json()
        assert d["employees_count"] == 1 and d["jobs_count"] == 1
    finally:
        _stop(server)


def test_a_failed_change_is_rolled_back_completely(client, monkeypatch):
    """If the database refuses a change, NOTHING from that request is saved (no half-written rows, no activity entry)."""
    monkeypatch.setattr("app.routers.employees._ensure_unique", lambda *a, **k: None)  # skip the friendly pre-check
    with SessionLocal() as db:
        before = (db.scalar(select(func.count()).select_from(Employee)), db.scalar(select(func.count()).select_from(ActivityLog)))
    r = client.post("/api/employees", json={**EMP, "employee_code": "E-0001"})  # duplicate code: only the DB catches it now
    assert r.status_code == 409 and "conflicts" in r.json()["detail"]
    assert "E-0001" not in r.text and "uq_" not in r.text  # no constraint names / SQL leaked
    with SessionLocal() as db:
        after = (db.scalar(select(func.count()).select_from(Employee)), db.scalar(select(func.count()).select_from(ActivityLog)))
    assert after == before


def test_app_refuses_to_start_without_a_database_url():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    r = subprocess.run([sys.executable, "-c", "import app.config"], cwd="/", env={**env, "PYTHONPATH": str(BACKEND)},
                       capture_output=True, text=True)
    assert r.returncode != 0 and "DATABASE_URL is not set" in r.stderr


def _config_in(env_overrides: dict, expr: str) -> subprocess.CompletedProcess:
    from tests.conftest import PRODUCTION_ENV

    env = {**os.environ, **PRODUCTION_ENV, **env_overrides}
    return subprocess.run([sys.executable, "-c", f"import app.config as c; print({expr})"], cwd=BACKEND, env=env,
                          capture_output=True, text=True)


def test_production_forces_safe_settings():
    r = _config_in({"APP_ENV": "production", "ENABLE_DEMO_RESET": "true", "COOKIE_SECURE": "false"},
                   "c.ENABLE_DEMO_RESET, c.COOKIE_SECURE")
    assert r.stdout.strip() == "False True"  # demo reset off, Secure cookies on, whatever the settings say


def test_production_refuses_insecure_settings():
    r = _config_in({"FRONTEND_ORIGINS": "http://workforceos.example.com", "AUDIT_HMAC_KEY": "",
                    "MIGRATION_DATABASE_URL": ""}, "1")
    assert r.returncode != 0 and "Refusing to start in production" in r.stderr
    for problem in ("FRONTEND_ORIGINS must list only https://", "AUDIT_HMAC_KEY must be set",
                    "must not connect as the database owner"):
        assert problem in r.stderr, problem
    assert _config_in({}, "'ok'").stdout.strip() == "ok"  # the complete production configuration is accepted


def test_wildcard_cors_is_refused_everywhere():
    r = _config_in({"APP_ENV": "development", "FRONTEND_ORIGINS": "*"}, "1")
    assert r.returncode != 0 and "'*' is not allowed" in r.stderr


def test_production_refuses_cheap_password_hashing():
    r = _config_in({"APP_ENV": "production", "PASSWORD_HASH_PROFILE": "fast"}, "1")
    assert r.returncode != 0 and "PASSWORD_HASH_PROFILE must be 'standard'" in r.stderr


def test_seed_is_idempotent(db):
    def counts():
        return [db.scalar(select(func.count()).select_from(m)) for m in (Department, Job, Candidate, Employee)]

    first = counts()
    assert sum(seed(db).values()) == 0  # fixture already seeded: nothing new
    assert counts() == first


def test_remove_sample_never_touches_real_data(client, db):
    mine = client.post("/api/employees", json=EMP).json()  # real record in a SAMPLE department
    job = client.post("/api/jobs", json={"title": "My Real Job", "department_id": "DEP-4002", "location": "Lahore",
                                          "status": "open", "openings": 1, "description": "Not sample data at all."}).json()
    removed = remove_sample(db)
    assert removed["employees"] == 13 and removed["applications"] == 20
    assert client.get(f"/api/employees/{mine['id']}").status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200
    left = {d["name"] for d in client.get("/api/departments").json()}
    assert left == {"Operations", "Product"}  # only departments still used by real records survive
    assert client.get("/api/candidates").json() == []
