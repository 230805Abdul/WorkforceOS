"""Phase 4 security tests: hostile input, response hardening, cross-site defences, rate limits, session hardening,
re-authentication. (Audit logging has its own file: test_audit.py.)"""
import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.models import Session
from app.main import app, create_app
from app.models import utcnow
from app.security.middleware import RateLimits
from tests.conftest import PASSWORD, USERS, sign_in

EMP = {"employee_code": "E-0900", "first_name": "Sec", "last_name": "Test", "email": "sec.test@example.org",
       "job_title": "Tester", "department_id": "DEP-4001", "employment_status": "active", "joining_date": "2026-03-03"}


def _browser(target=app):
    return TestClient(target, raise_server_exceptions=False)


# ---------------------------------------------------------------- hostile input
@pytest.mark.parametrize("bad", ["Bad\x00Name", "Line\nBreak", "Tab\there", "Bell\x07", "Esc\x1b[31m"])
def test_control_characters_are_refused_not_a_500(client, bad):
    r = client.post("/api/departments", json={"name": bad, "code": "CTL"})
    assert r.status_code == 422 and r.json()["errors"]["name"] == "Contains characters that aren't allowed"


def test_multiline_fields_allow_newlines_but_not_nul(client):
    ok = client.post("/api/departments", json={"name": "Multi", "code": "MLT", "description": "Line one\nLine two\ttabbed"})
    assert ok.status_code == 201 and ok.json()["description"] == "Line one\nLine two\ttabbed"
    assert client.post("/api/departments", json={"name": "Multi2", "code": "ML2", "description": "x\x00y"}).status_code == 422


def test_nul_in_search_and_overlong_search_are_rejected(client):
    assert client.get("/api/employees", params={"search": "a\x00b"}).status_code == 422
    assert client.get("/api/employees", params={"search": "a" * 101}).status_code == 422
    assert client.get("/api/employees", params={"search": "a" * 100}).status_code == 200


def test_legitimate_special_characters_are_kept_exactly(client):
    """Validation, not sanitising: quotes, angle brackets and non-Latin letters are real data."""
    name = "O'Brien & <Partners> \"Ltd\" ŻÓŁĆ 李"
    r = client.post("/api/departments", json={"name": name, "code": "OBP"})
    assert r.status_code == 201 and r.json()["name"] == name
    assert client.get(f"/api/departments/{r.json()['id']}").json()["name"] == name


@pytest.mark.parametrize("payload", ["' OR '1'='1", "x'; DROP TABLE employees; --", "\" OR 1=1 --", "1; SELECT pg_sleep(5)"])
def test_sql_injection_strings_are_stored_as_plain_text(client, payload):
    r = client.post("/api/employees", json={**EMP, "job_title": payload})
    assert r.status_code == 201 and r.json()["job_title"] == payload
    assert len(client.get("/api/employees").json()) == 14  # table intact
    found = client.get("/api/employees", params={"search": payload[:40]}).json()
    assert [e["job_title"] for e in found] == [payload]


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/departments", {"name": "Extra", "code": "EXT", "is_sample": True}),
    ("POST", "/api/jobs", {"title": "Extra Job", "department_id": "DEP-4001", "location": "X", "description": "Ten chars!!",
                           "applications_count": 99}),
    ("POST", "/api/employees", {**EMP, "id": "EMP-1"}),
    ("POST", "/api/candidates", {"full_name": "Extra Cand", "email": "ec@example.org", "created_at": "2000-01-01"}),
    ("PATCH", "/api/applications/APP-3004/status", {"status": "screening", "job_id": "JOB-1002"}),
])
def test_unknown_fields_are_rejected_everywhere(client, method, path, body):
    r = client.request(method, path, json=body)
    assert r.status_code == 422 and "This field cannot be changed here" in r.json()["errors"].values()


def test_oversized_bodies_are_refused_before_parsing(client):
    huge = {"name": "Huge", "code": "HUG", "description": "A" * 70_000}
    r = client.post("/api/departments", json=huge)
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"

    def stream():  # no Content-Length: the limit must still apply while the body arrives
        yield b'{"name": "Streamed", "code": "STR", "description": "'
        for _ in range(100):
            yield b"B" * 1024
        yield b'"}'
    r = client.post("/api/departments", content=stream(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert client.get("/api/departments", params={"search": "Huge"}).json() == []


def test_bodies_must_be_json(client):
    r = client.post("/api/departments", content=b"name=x&code=Y", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415 and r.json()["code"] == "unsupported_media_type"
    r = client.post("/api/departments", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["errors"] == {"body": "Invalid JSON"}
    assert client.post("/api/auth/logout-others").status_code == 200  # an EMPTY body needs no content type


def test_reset_tokens_must_look_like_tokens(anon):
    body = {"new_password": "lantern-pebble-quartz-77", "new_password_confirm": "lantern-pebble-quartz-77"}
    assert anon.post("/api/auth/reset-password", json={**body, "token": "../../etc/passwd" + "x" * 20}).status_code == 422


# ---------------------------------------------------------------- response hardening
EXPECTED_HEADERS = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
}


@pytest.mark.parametrize("call", [
    lambda c, a: c.get("/api/employees"),                                         # 200
    lambda c, a: a.get("/api/employees"),                                         # 401
    lambda c, a: c.get("/api/employees/EMP-9999"),                                # 404
    lambda c, a: c.post("/api/departments", json={"name": "x"}),                  # 422
    lambda c, a: c.post("/api/departments", json={"name": "y" * 70_000}),         # 413
    lambda c, a: a.post("/api/auth/login", json={}, headers={"Origin": "https://evil.example"}),  # 403 from middleware
], ids=["200", "401", "404", "422", "413", "403-middleware"])
def test_security_headers_are_on_every_response(client, anon, call):
    r = call(client, anon)
    for header, value in EXPECTED_HEADERS.items():
        assert r.headers.get(header) == value, header
    assert "camera=()" in r.headers["permissions-policy"]
    assert "strict-transport-security" not in r.headers  # development is plain http: HSTS would be wrong here
    assert len(r.headers["x-request-id"]) >= 8


def test_hsts_is_sent_when_configured(client, monkeypatch):
    monkeypatch.setattr("app.security.headers.HSTS_MAX_AGE", 31_536_000)
    assert client.get("/api/health").headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_request_ids_are_echoed_only_when_well_formed(client):
    assert client.get("/api/health", headers={"X-Request-ID": "trace-12345678"}).headers["x-request-id"] == "trace-12345678"
    forged = client.get("/api/health", headers={"X-Request-ID": "bad id\r\nX-Injected: 1"}).headers["x-request-id"]
    assert forged != "bad id" and " " not in forged and len(forged) == 32


def test_unexpected_errors_are_generic_with_a_reference(client, caplog):
    from app.routers import departments

    def boom():
        raise RuntimeError("secret internal detail: password=hunter2")

    app.dependency_overrides[departments.get_db] = boom
    try:
        with caplog.at_level(logging.ERROR, logger="workforceos"):
            r = client.get("/api/departments", headers={"X-Request-ID": "ref-abcdef12"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 500
    assert r.json() == {"detail": "Something went wrong on the server (reference: ref-abcdef12).", "code": "server_error"}
    assert "hunter2" not in r.text and "Traceback" not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "hunter2" in caplog.text  # ...but the developer can still find out what happened, by reference


def test_api_docs_can_be_switched_off(monkeypatch):
    monkeypatch.setattr("app.main.EXPOSE_API_DOCS", False)
    locked = _browser(create_app(rate_limits=None))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert locked.get(path).status_code == 404
    assert _browser().get("/docs").status_code == 200  # development default


def test_integrity_and_data_errors_never_log_the_values(client, caplog, monkeypatch):
    monkeypatch.setattr("app.routers.departments._ensure_unique", lambda *a, **k: None)
    with caplog.at_level(logging.WARNING, logger="workforceos"):
        r = client.post("/api/departments", json={"name": "Engineering", "code": "UNIQ"})  # duplicate name, DB catches it
    assert r.status_code == 409
    assert "Integrity error" in caplog.text and "Engineering" not in caplog.text.split("Integrity error")[1]


# ---------------------------------------------------------------- cross-site requests
def test_cross_site_signals_are_refused(client):
    body = {"name": "Csrf Dept", "code": "CSR"}
    r = client.post("/api/departments", json=body, headers={"Referer": "https://evil.example/page"})
    assert r.status_code == 403 and r.json()["code"] == "bad_origin"
    r = client.post("/api/departments", json=body, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = client.post("/api/departments", json=body, headers={"Referer": "http://127.0.0.1:5173/departments",
                                                            "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 201  # our own pages are fine


# ---------------------------------------------------------------- rate limiting
TIGHT = RateLimits(read="5/minute", write="3/minute", auth="4/minute", sensitive="2/minute", per_ip="40/minute")


@pytest.fixture
def limited():
    return create_app(rate_limits=TIGHT)


def test_read_limit_per_session_with_retry_after(limited):
    a = sign_in(USERS["hr_admin"][0], target=limited)  # sign-in itself counts towards the auth budget
    assert [a.get("/api/departments").status_code for _ in range(5)] == [200] * 5
    r = a.get("/api/departments")
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and 1 <= int(r.headers["retry-after"]) <= 61
    b = sign_in(USERS["hr_manager"][0], target=limited)
    assert b.get("/api/departments").status_code == 200  # another session has its own budget


def test_writes_have_a_smaller_budget_than_reads(limited):
    a = sign_in(USERS["hr_admin"][0], target=limited)
    codes = [a.post("/api/departments", json={"name": f"Rate {i}", "code": f"RT{i}"}).status_code for i in range(4)]
    assert codes == [201, 201, 201, 429]
    assert a.get("/api/departments").status_code == 200  # reads still work


def test_sign_in_attempts_are_limited_per_ip(limited):
    b = _browser(limited)
    codes = [b.post("/api/auth/login", json={"email": f"x{i}@example.org", "password": "whatever-123"}).status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 429]


def test_sensitive_admin_actions_have_the_strictest_budget(limited):
    admin = sign_in(USERS["super_admin"][0], target=limited)
    target = next(u["id"] for u in admin.get("/api/users", params={"search": USERS["recruiter"][0]}).json())
    codes = [admin.post(f"/api/users/{target}/reset-link").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_per_ip_safety_net():
    """Many sessions from ONE address share the per-IP budget (generous; catches floods using fresh sessions)."""
    roomy = create_app(rate_limits=RateLimits(read="1000/minute", write="1000/minute", auth="1000/minute",
                                              sensitive="1000/minute", per_ip="10/minute"))
    clients = [sign_in(USERS[r][0], target=roomy) for r in ("hr_admin", "hr_manager")]  # 2 requests
    codes = [c.get("/api/health").status_code for _ in range(4) for c in clients]     # 8 more = 10 in total
    assert codes.count(429) == 0
    assert clients[0].get("/api/health").status_code == 429
    assert clients[1].get("/api/health").status_code == 429  # the other session is blocked too: same address


def test_rate_limiting_is_recorded_once_per_window(limited, db):
    from app.audit import AuditEvent

    start = db.scalar(select(AuditEvent.id).order_by(AuditEvent.id.desc()).limit(1)) or 0
    a = sign_in(USERS["hr_admin"][0], target=limited)
    for _ in range(9):
        a.get("/api/departments")  # 5 allowed, 4 refused
    rows = db.scalars(select(AuditEvent).where(AuditEvent.id > start, AuditEvent.action == "security.rate_limited")).all()
    assert len(rows) == 1 and rows[0].details["limit"] == "read" and rows[0].outcome == "denied"


# ---------------------------------------------------------------- session hardening
def test_signing_in_ends_the_session_the_browser_already_had(db):
    c = sign_in(USERS["hr_admin"][0])
    old_cookie = c.cookies.get("wos_session")
    r = c.post("/api/auth/login", json={"email": USERS["hr_manager"][0], "password": PASSWORD})  # same browser, new sign-in
    assert r.status_code == 200
    replay = _browser()
    replay.cookies.set("wos_session", old_cookie)
    assert replay.get("/api/auth/me").status_code == 401  # the earlier session is gone, not just replaced in the browser
    assert len(db.scalars(select(Session.id)).all()) == 1


SENSITIVE = [
    ("POST", "/api/users", {"full_name": "Re Auth", "email": "reauth@example.org"}),
    ("PUT", "/api/users/{uid}/roles", {"role_ids": ["ROL-7005"]}),
    ("PATCH", "/api/users/{uid}/status", {"status": "disabled"}),
    ("PATCH", "/api/users/{uid}", {"full_name": "Remy Recruiter"}),
    ("POST", "/api/users/{uid}/reset-link", None),
    ("POST", "/api/users/{uid}/revoke-sessions", None),
    ("POST", "/api/roles", {"name": "reauth_role", "label": "Reauth"}),
    ("POST", "/api/demo/reset", None),
]


@pytest.mark.parametrize("method,path,body", SENSITIVE, ids=[f"{m} {p}" for m, p, _ in SENSITIVE])
def test_high_impact_actions_need_a_recent_password(client, db, method, path, body):
    uid = next(u["id"] for u in client.get("/api/users", params={"search": USERS["recruiter"][0]}).json())
    db.execute(update(Session).values(reauthenticated_at=utcnow() - timedelta(minutes=11)))
    db.commit()
    r = client.request(method, path.format(uid=uid), json=body)
    assert r.status_code == 403 and r.json()["code"] == "reauth_required"
    assert client.get("/api/employees").status_code == 200  # ordinary work is unaffected


def test_reauthentication_flow(client, db):
    from app.audit import AuditEvent

    db.execute(update(Session).values(reauthenticated_at=utcnow() - timedelta(minutes=11)))
    db.commit()
    assert client.post("/api/roles", json={"name": "after_reauth", "label": "After"}).json()["code"] == "reauth_required"
    wrong = client.post("/api/auth/reauthenticate", json={"password": "not-my-password"})
    assert wrong.status_code == 422 and wrong.json()["errors"] == {"password": "Incorrect password"}
    ok = client.post("/api/auth/reauthenticate", json={"password": PASSWORD})
    assert ok.status_code == 200 and "confirmed_until" in ok.json()
    assert client.post("/api/roles", json={"name": "after_reauth", "label": "After"}).status_code == 201
    outcomes = db.scalars(select(AuditEvent.outcome).where(AuditEvent.action == "auth.reauthenticate")
                          .order_by(AuditEvent.id.desc()).limit(2)).all()
    assert outcomes == ["success", "failure"]


def test_reauthentication_guesses_count_as_failed_sign_ins(client):
    for _ in range(5):
        client.post("/api/auth/reauthenticate", json={"password": "guess-guess-guess"})
    r = client.post("/api/auth/reauthenticate", json={"password": PASSWORD})
    assert r.status_code == 429  # a stolen session can't be used to brute-force the password either


def test_a_fresh_sign_in_counts_as_recent(client):
    assert client.post("/api/roles", json={"name": "fresh_session", "label": "Fresh"}).status_code == 201


def test_malformed_json_is_a_clear_400(client):
    r = client.post("/api/auth/login", content=b'{"email":', headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["detail"] == "The request body is not valid JSON."
