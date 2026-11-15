"""Audit log: the right events are recorded, without secrets, only administrators can read them, and tampering is
detected by the hash-chain verification."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session as OrmSession

from app.audit import AuditEvent, compute_hash, key_id_for, verify_chain
from app.db import engine
from tests.conftest import PASSWORD, USERS, sign_in

GOOD_NEW_PASSWORD = "lantern-pebble-quartz-77"


@pytest.fixture
def mark(db):
    """The id of the newest audit record before the test; events() returns only what the test caused."""
    start = db.scalar(select(AuditEvent.id).order_by(AuditEvent.id.desc()).limit(1)) or 0

    def events(**filters):
        db.expire_all()
        stmt = select(AuditEvent).where(AuditEvent.id > start).order_by(AuditEvent.id)
        for k, v in filters.items():
            stmt = stmt.where(getattr(AuditEvent, k) == v)
        return db.scalars(stmt).all()

    return events


def _uid(client, role):
    return next(u["id"] for u in client.get("/api/users", params={"search": USERS[role][0]}).json())


# ---------------------------------------------------------------- what gets recorded
def test_sign_in_success_and_failure(anon, mark):
    anon.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "wrong-password-guess"},
              headers={"X-Request-ID": "login-fail-0001", "User-Agent": "TestBrowser/1"})
    anon.post("/api/auth/login", json={"email": "nobody@example.org", "password": "wrong-password-guess"})
    sign_in(USERS["hr_admin"][0])
    fail, ghost, ok = mark(action="auth.login")
    assert (fail.outcome, fail.details["reason"], fail.details["email"]) == ("failure", "invalid_credentials", USERS["hr_admin"][0])
    assert fail.target_type == "user" and fail.actor_user_id is None  # not signed in, but we know whose account
    assert fail.request_id == "login-fail-0001" and fail.user_agent == "TestBrowser/1" and fail.ip
    assert ghost.details["account_exists"] is False and ghost.target_id is None
    assert ok.outcome == "success" and ok.actor_email == USERS["hr_admin"][0] and ok.details["remember"] is False


def test_logout_password_change_and_reset_are_recorded(client, anon, mark):
    me = sign_in(USERS["hr_manager"][0])
    me.post("/api/auth/change-password", json={"current_password": "nope-nope-nope", "new_password": GOOD_NEW_PASSWORD,
                                               "new_password_confirm": GOOD_NEW_PASSWORD})
    me.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": GOOD_NEW_PASSWORD,
                                               "new_password_confirm": GOOD_NEW_PASSWORD})
    me.post("/api/auth/logout")
    link = client.post(f"/api/users/{_uid(client, 'hr_manager')}/reset-link").json()
    anon.post("/api/auth/reset-password", json={"token": link["url"].split("token=")[1], "new_password": "another-quiet-river-5",
                                                "new_password_confirm": "another-quiet-river-5"})
    actions = [(e.action, e.outcome) for e in mark() if e.category in ("auth", "user")]
    assert actions[-5:] == [("auth.password_changed", "failure"), ("auth.password_changed", "success"),
                            ("auth.logout", "success"), ("user.reset_link_created", "success"), ("auth.password_reset", "success")]


def test_invitation_and_activation(client, anon, mark):
    r = client.post("/api/users", json={"full_name": "Ivy Audit", "email": "ivy.audit@example.org"}).json()
    anon.post("/api/auth/reset-password", json={"token": r["invite"]["url"].split("token=")[1], "new_password": GOOD_NEW_PASSWORD,
                                                "new_password_confirm": GOOD_NEW_PASSWORD})
    invited, activated = mark(target_id=r["user"]["id"])
    assert invited.action == "user.invited" and invited.details["roles"] == ["employee"]
    assert activated.action == "auth.account_activated" and activated.details["via"] == "invite"


def test_admin_changes_record_before_and_after(client, mark):
    uid = _uid(client, "recruiter")
    client.put(f"/api/users/{uid}/roles", json={"role_ids": ["ROL-7003"]})  # hr_manager
    client.patch(f"/api/users/{uid}/status", json={"status": "disabled"})
    client.patch(f"/api/users/{uid}/status", json={"status": "active"})
    roles, off, on = mark(target_id=uid)
    assert roles.action == "user.roles_changed" and roles.details == {"from": ["recruiter"], "to": ["hr_manager"]}
    assert off.action == "user.deactivated" and on.action == "user.reactivated"
    assert roles.actor_email == USERS["super_admin"][0]

    role = next(r for r in client.get("/api/roles").json() if r["name"] == "recruiter")
    client.put(f"/api/roles/{role['id']}", json={"label": role["label"],
                                                 "permissions": [p for p in role["permissions"] if p != "jobs:manage"] + ["employees:read"]})
    changed = mark(action="role.updated")[0]
    assert changed.details["permissions_added"] == ["employees:read"] and changed.details["permissions_removed"] == ["jobs:manage"]


def test_employee_changes_list_fields_but_not_personal_values(client, mark):
    emp = client.get("/api/employees/EMP-5004").json()
    body = {k: emp[k] for k in ("employee_code", "first_name", "last_name", "email", "phone", "job_title", "department_id",
                                "employment_status", "joining_date")}
    client.put("/api/employees/EMP-5004", json={**body, "email": "new.private@example.org", "job_title": "Head of Product",
                                                 "department_id": "DEP-4003"})
    client.delete("/api/employees/EMP-5012")
    updated, deleted = mark(category="employee")
    assert updated.details["fields"] == ["department_id", "email", "job_title"]
    assert updated.details["values"] == {"department_id": ["DEP-4002", "DEP-4003"],
                                         "job_title": ["Senior Product Manager", "Head of Product"]}
    assert "new.private@example.org" not in str(updated.details)  # personal data: only THAT it changed
    assert deleted.action == "employee.deleted" and deleted.details == {"employee_code": "E-0012"}


def test_refused_actions_are_security_events(as_role, mark):
    mgr = as_role("hr_manager")
    mgr.delete("/api/employees/EMP-5001")
    del mgr.headers["X-CSRF-Token"]
    mgr.post("/api/applications", json={"candidate_id": "CAN-2001", "job_id": "JOB-1003"})
    forbidden, csrf = mark(action="security.access_denied")
    assert forbidden.details == {"code": "forbidden", "method": "DELETE", "path": "/api/employees/EMP-5001"}
    assert forbidden.actor_email == USERS["hr_manager"][0] and csrf.details["code"] == "csrf_failed"


def test_password_guessing_is_recorded_once_not_per_attempt(anon, mark):
    for _ in range(9):
        anon.post("/api/auth/login", json={"email": USERS["recruiter"][0], "password": "guess-guess-guess"})
    blocked = mark(action="security.too_many_attempts")
    assert len(blocked) == 1 and blocked[0].details == {"kind": "login", "by": "email", "email": USERS["recruiter"][0]}
    assert len(mark(action="auth.login")) == 5  # 5 recorded failures, then refused without even checking the password


def test_new_device_sign_ins_are_flagged(mark):
    sign_in(USERS["employee"][0])                          # first ever: not flagged
    sign_in(USERS["employee"][0])                          # same browser: not flagged
    c = sign_in(USERS["employee"][0], headers={"User-Agent": "UnknownBrowser/9"})
    logins = mark(action="auth.login")
    assert [e.details["new_device"] for e in logins] == [False, False, True]
    assert len(mark(action="security.new_device_sign_in")) == 1
    history = c.get("/api/auth/me/sign-ins").json()
    assert [h["new_device"] for h in history[:3]] == [True, False, False] and history[0]["user_agent"] == "UnknownBrowser/9"


def test_sign_in_history_only_shows_your_own(as_role, anon):
    anon.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "someone-else-guessing"})
    mine = as_role("employee").get("/api/auth/me/sign-ins").json()
    assert all(h["outcome"] == "success" for h in mine)  # the failed attempt on hr_admin's account isn't there
    theirs = as_role("hr_admin").get("/api/auth/me/sign-ins").json()
    assert theirs[1]["outcome"] == "failure" and theirs[1]["reason"] == "invalid_credentials"


def test_audit_records_never_contain_secrets(client, anon, db, mark):
    anon.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "Sup3r-Secret-Guess!"})
    link = client.post(f"/api/users/{_uid(client, 'recruiter')}/reset-link").json()
    token = link["url"].split("token=")[1]
    anon.post("/api/auth/reset-password", json={"token": token, "new_password": GOOD_NEW_PASSWORD, "new_password_confirm": GOOD_NEW_PASSWORD})
    everything = " ".join(str(e.__dict__) for e in mark())
    for secret in ("Sup3r-Secret-Guess!", PASSWORD, GOOD_NEW_PASSWORD, token, client.cookies.get("wos_session"),
                   client.headers["X-CSRF-Token"], "$argon2"):
        assert secret not in everything


def test_an_audit_failure_never_breaks_the_request(anon, monkeypatch, caplog):
    def broken():
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr("app.audit.SessionLocal", broken)
    r = anon.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD})
    assert r.status_code == 200
    assert "AUDIT WRITE FAILED for auth.login" in caplog.text


# ---------------------------------------------------------------- who can read it
@pytest.mark.parametrize("role", ["hr_admin", "hr_manager", "recruiter", "employee"])
def test_only_audit_readers_can_see_the_audit_log(as_role, role):
    c = as_role(role)
    for path in ("/api/audit/events", "/api/audit/summary", "/api/audit/verify"):
        assert c.get(path).status_code == 403


def test_audit_api_filters_and_pages(client, anon, mark):
    for _ in range(3):
        anon.post("/api/auth/login", json={"email": "filter.test@example.org", "password": "wrong-password-xx"})
    page = client.get("/api/audit/events", params={"action": "auth.login", "outcome": "failure", "limit": 2}).json()
    assert len(page["items"]) == 2 and page["next_before_id"] == page["items"][-1]["id"]
    older = client.get("/api/audit/events", params={"action": "auth.login", "outcome": "failure", "limit": 2,
                                                     "before_id": page["next_before_id"]}).json()
    assert older["items"][0]["id"] < page["items"][-1]["id"]
    found = client.get("/api/audit/events", params={"search": "filter.test"}).json()["items"]
    assert len(found) == 3 and all(e["details"]["email"] == "filter.test@example.org" for e in found)
    sec = client.get("/api/audit/events", params={"category": "security"}).json()["items"]
    assert all(e["category"] == "security" for e in sec)
    assert client.get("/api/audit/events", params={"category": "nonsense"}).status_code == 422
    summary = client.get("/api/audit/summary").json()
    assert summary["failed_sign_ins"] >= 3
    assert {"email": "filter.test@example.org", "failures": 3} in summary["most_failed_emails"]


def test_the_audit_api_cannot_change_records(client):
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/audit/events").status_code == 405
        assert client.request(method, "/api/audit/events/1").status_code in (404, 405)


# ---------------------------------------------------------------- integrity
def test_database_refuses_to_change_or_delete_audit_records(db, client):
    assert db.scalar(select(AuditEvent.id).limit(1)) is not None
    for statement in (update(AuditEvent).values(action="forged"), delete(AuditEvent)):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(statement)
            db.commit()
        db.rollback()


def test_verification_passes_on_the_real_log(client):
    result = client.get("/api/audit/verify").json()
    assert result["ok"] is True and result["checked"] > 0 and result["development_key"] is True


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="owner bypass of the trigger is PostgreSQL-specific")
def test_tampering_by_a_database_owner_is_detected(client, db):
    """Even someone who can switch the trigger off (the table owner) is caught by the HMAC chain."""
    victim = db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(3)).all()[-1]
    original = dict(victim.details)
    db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete"))
    db.execute(text("UPDATE audit_events SET details = CAST(:d AS jsonb) WHERE id = :id"),
               {"d": '{"rewritten": "history"}', "id": victim.id})
    db.commit()
    try:
        result = client.get("/api/audit/verify").json()
        assert result["ok"] is False and result["first_problem_id"] == victim.id and "altered" in result["problem"]
    finally:
        import json

        db.execute(text("UPDATE audit_events SET details = CAST(:d AS jsonb) WHERE id = :id"),
                   {"d": json.dumps(original), "id": victim.id})
        db.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update_delete"))
        db.commit()
    assert client.get("/api/audit/verify").json()["ok"] is True


def _chain(session, keys: list[str]):
    """Build a small chain in a private database (no triggers) so we can attack it freely."""
    prev = None
    for i, key in enumerate(keys):
        e = AuditEvent(occurred_at=datetime(2026, 1, 1, 12, i, tzinfo=timezone.utc), category="system", action=f"test.{i}",
                       outcome="success", details={"n": i}, key_id=key_id_for(key), prev_hash=prev)
        e.hash = compute_hash(e, key)
        session.add(e)
        session.flush()
        prev = e.hash
    session.commit()


@pytest.fixture
def private_log(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/audit.db")
    AuditEvent.__table__.create(eng)
    with OrmSession(eng) as s:
        yield s


def test_verification_detects_edits_deletions_and_insertions(private_log, monkeypatch):
    key = "k" * 40
    monkeypatch.setattr("app.audit.KEYS", {key_id_for(key): key})
    _chain(private_log, [key] * 5)
    assert verify_chain(private_log)["ok"] is True

    private_log.execute(update(AuditEvent).where(AuditEvent.id == 3).values(outcome="failure"))
    private_log.commit()
    r = verify_chain(private_log)
    assert (r["ok"], r["first_problem_id"], r["checked"]) == (False, 3, 2) and "altered" in r["problem"]

    private_log.execute(update(AuditEvent).where(AuditEvent.id == 3).values(outcome="success"))
    private_log.execute(delete(AuditEvent).where(AuditEvent.id == 2))
    private_log.commit()
    r = verify_chain(private_log)
    assert (r["ok"], r["first_problem_id"]) == (False, 3) and "broken" in r["problem"]


def test_key_rotation_keeps_old_records_verifiable(private_log, monkeypatch):
    old, new = "o" * 40, "n" * 40
    _chain(private_log, [old, old, new])  # rotated after the second record
    monkeypatch.setattr("app.audit.KEYS", {key_id_for(old): old, key_id_for(new): new})
    assert verify_chain(private_log)["ok"] is True
    monkeypatch.setattr("app.audit.KEYS", {key_id_for(new): new})  # old key forgotten
    r = verify_chain(private_log)
    assert r["ok"] is False and "AUDIT_HMAC_OLD_KEYS" in r["problem"]


def test_job_and_application_changes_are_audited(client):
    from app.db import SessionLocal
    from sqlalchemy import select
    from app.audit import AuditEvent
    from sqlalchemy import func

    with SessionLocal() as db:
        start = db.scalar(select(func.max(AuditEvent.id))) or 0
    dep = client.post("/api/departments", json={"name": "Audit Jobs Dept", "code": "AJD"}).json()["id"]
    job = client.post("/api/jobs", json={"title": "Audit Engineer", "department_id": dep, "location": "Remote",
                                         "employment_type": "full_time", "status": "open", "openings": 2,
                                         "description": "A long description " * 10}).json()
    assert "id" in job, job
    body = {**{k: job[k] for k in ("title", "location", "employment_type", "status", "openings")},
            "department_id": dep, "description": "Rewritten " * 20}
    assert client.put(f"/api/jobs/{job['id']}", json=body).status_code == 200
    cand = client.post("/api/candidates", json={"full_name": "Audit Candidate", "email": "audit.cand@example.com"}).json()
    app_ = client.post("/api/applications", json={"candidate_id": cand["id"], "job_id": job["id"]}).json()
    assert client.patch(f"/api/applications/{app_['id']}/status", json={"status": "screening"}).status_code == 200
    assert client.delete(f"/api/applications/{app_['id']}").status_code == 204
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    with SessionLocal() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.category.in_(["job", "application"]), AuditEvent.id > start)
                          .order_by(AuditEvent.id)).all()
    rows = [r for r in rows if r.target_id in (job["id"], app_["id"])]
    actions = [r.action for r in rows]
    for a in ("job.created", "job.updated", "application.created", "application.status_changed",
              "application.deleted", "job.deleted"):
        assert a in actions, actions
    upd = next(r for r in rows if r.action == "job.updated")
    assert "description" in upd.details["fields"] and "description" not in upd.details.get("values", {})
    st = next(r for r in rows if r.action == "application.status_changed")
    assert st.details == {"from": "applied", "to": "screening"} and st.actor_email
