"""Database-level guarantees: the DATABASE enforces these, not just the API."""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db import engine, get_db
from app.main import app
from app.models import Application, Candidate, Job, utcnow

NEW_JOB = {"title": "QA Engineer", "department_id": "DEP-4001", "location": "Remote", "employment_type": "full_time",
           "status": "open", "openings": 1, "description": "Test our product thoroughly."}


def _job(**kw):
    base = dict(title="T", department_id=4, location="X", employment_type="full_time", status="open", openings=1, description="d")
    return Job(**{**base, **kw})


def _candidate(**kw):
    return Candidate(**{**dict(full_name="Test Person", email="t@example.com", source="other"), **kw})


# ---------- constraints ----------
def test_email_unique_ignoring_case(db):
    db.add(_candidate(email="AMARA.OKAFOR@EXAMPLE.COM"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_check_constraints_reject_bad_values(db):
    for bad in (_job(openings=0), _job(openings=51), _job(status="bogus"), _job(employment_type="nope")):
        db.add(bad)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    db.add(_candidate(source="telepathy"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_application_per_candidate_per_job(db):
    db.add(Application(candidate_id=1, job_id=1, status="applied"))  # seed already has candidate 1 on job 1
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_are_enforced(db):
    db.add(Application(candidate_id=9999, job_id=1, status="applied"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_database_cascades_deletes_on_its_own(db):
    before = db.scalar(text("SELECT count(*) FROM applications"))
    n = db.scalar(text("SELECT count(*) FROM applications WHERE job_id = 1"))
    assert n > 0
    db.execute(text("DELETE FROM jobs WHERE id = 1"))  # raw SQL: no ORM, no API
    db.commit()
    assert db.scalar(text("SELECT count(*) FROM applications")) == before - n


# ---------- persistence & ids ----------
def test_data_survives_dropping_every_connection(client):
    job_id = client.post("/api/jobs", json=NEW_JOB).json()["id"]
    engine.dispose()  # closes the whole connection pool, like restarting the server
    assert client.get(f"/api/jobs/{job_id}").json()["title"] == "QA Engineer"


def test_ids_are_stable_public_ids(client):
    jobs = client.get("/api/jobs").json()
    assert sorted(j["id"] for j in jobs) == [f"JOB-{1001 + i}" for i in range(8)]
    assert client.get("/api/candidates/CAN-2001").json()["full_name"] == "Amara Okafor"
    assert client.post("/api/jobs", json=NEW_JOB).json()["id"] == "JOB-1009"


@pytest.mark.parametrize("bad", ["abc", "JOB-0", "JOB-1000", "JOB-99999999999999999", "CAN-2001", "JOB-1.5", "'; DROP TABLE jobs;--"])
def test_malformed_ids_are_404_not_500(client, bad):
    assert client.get(f"/api/jobs/{bad}").status_code == 404
    assert client.delete(f"/api/jobs/{bad}").status_code == 404
    assert client.get("/api/jobs").status_code == 200  # nothing was damaged


def test_search_treats_wildcards_literally_and_resists_injection(client):
    assert client.get("/api/jobs", params={"search": "%"}).json() == []
    assert client.get("/api/jobs", params={"search": "_"}).json() == []
    assert client.get("/api/jobs", params={"search": "'; DROP TABLE jobs; --"}).json() == []
    assert len(client.get("/api/jobs").json()) == 8
    assert [j["id"] for j in client.get("/api/jobs", params={"search": "1001"}).json()] == ["JOB-1001"]
    assert len(client.get("/api/applications", params={"job_id": "nonsense"}).json()) == 0


def test_timestamps_are_timezone_aware_utc(client):
    created = client.post("/api/jobs", json=NEW_JOB).json()["created_at"]
    assert created.endswith("Z") or created.endswith("+00:00"), created


# ---------- failure behaviour ----------
def test_database_outage_gives_helpful_503_not_a_stack_trace(client):
    def broken():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken
    try:
        for path in ("/api/jobs", "/api/health", "/api/dashboard"):
            r = client.get(path)
            assert r.status_code == 503 and "PostgreSQL" in r.json()["detail"], path
            assert "Traceback" not in r.text and "connection refused" not in r.text
    finally:
        app.dependency_overrides.clear()


def test_demo_reset_is_not_even_registered_when_disabled():
    from app.main import create_app
    from tests.conftest import USERS, sign_in

    locked = sign_in(USERS["super_admin"][0], target=create_app(enable_demo_reset=False))
    assert locked.post("/api/demo/reset").status_code == 404  # the route doesn't exist, even for a Super Administrator
    assert locked.get("/api/meta").status_code == 200
    assert len(locked.get("/api/jobs").json()) == 8


def test_health_reports_database(client):
    assert client.get("/api/health").json()["database"] == "ok"


# ---------- concurrency ----------
def _offer_stage_application(client, openings=1):
    """A job with `openings` openings and one candidate sitting at the 'offer' stage."""
    job = client.post("/api/jobs", json={**NEW_JOB, "openings": openings}).json()["id"]
    cid = client.post("/api/candidates", json={"full_name": "Racer", "email": "racer@example.com"}).json()["id"]
    aid = client.post("/api/applications", json={"candidate_id": cid, "job_id": job}).json()["id"]
    for step in ("screening", "interview", "offer"):
        client.patch(f"/api/applications/{aid}/status", json={"status": step})
    return job, aid


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locks only matter on PostgreSQL")
def test_hiring_waits_for_the_job_row_lock(client):
    """Deterministic proof that 'hire' locks the job row (so two hires can't both take the last opening).

    We hold the job's row lock in one session and check the hire request really blocks until we let go.
    If someone removes `with_for_update()` from update_status, the request finishes instantly and this fails.
    """
    from fastapi.testclient import TestClient

    from app.db import SessionLocal
    from app.ids import parse_id

    job, aid = _offer_stage_application(client)
    result: list[int] = []

    from tests.conftest import USERS, sign_in

    other_browser = sign_in(USERS["super_admin"][0])  # signed in BEFORE we take the lock

    def hire():
        result.append(other_browser.patch(f"/api/applications/{aid}/status", json={"status": "hired"}).status_code)

    with SessionLocal() as holder:
        holder.execute(text("SELECT id FROM jobs WHERE id = :pk FOR UPDATE"), {"pk": parse_id("job", job)})
        t = threading.Thread(target=hire)
        t.start()
        t.join(timeout=1.0)
        assert t.is_alive(), "hire completed while the job row was locked: update_status is not locking the job"
        holder.rollback()  # release the lock
    t.join(timeout=10)
    assert result == [200]


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row locks only matter on PostgreSQL")
def test_simultaneous_hires_end_to_end_smoke_test(client):
    """Sanity check only: the race window is tiny, so this alone can't prove the lock (the test above does)."""
    from fastapi.testclient import TestClient

    job, first = _offer_stage_application(client)
    cid = client.post("/api/candidates", json={"full_name": "Racer 2", "email": "racer2@example.com"}).json()["id"]
    second = client.post("/api/applications", json={"candidate_id": cid, "job_id": job}).json()["id"]
    for step in ("screening", "interview", "offer"):
        client.patch(f"/api/applications/{second}/status", json={"status": step})

    from tests.conftest import USERS, sign_in

    barrier, codes = threading.Barrier(2), []
    browsers = {a: sign_in(USERS["super_admin"][0]) for a in (first, second)}  # two separate signed-in browsers

    def hire(aid):
        c = browsers[aid]
        barrier.wait()
        codes.append(c.patch(f"/api/applications/{aid}/status", json={"status": "hired"}).status_code)

    threads = [threading.Thread(target=hire, args=(a,)) for a in (first, second)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [200, 409]
    assert client.get(f"/api/jobs/{job}").json()["hired_count"] == 1
