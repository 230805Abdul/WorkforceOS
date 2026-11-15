"""Authorization: who may do what. Everything here is enforced by the BACKEND, independent of the frontend."""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Permission, Role
from app.auth.permissions import BUILTIN_ROLES, PERMISSIONS
from app.main import app
from tests.conftest import USERS, sign_in

PUBLIC = {("GET", "/api/health"), ("GET", "/api/auth/config"), ("POST", "/api/auth/register"), ("POST", "/api/auth/login"),
          ("POST", "/api/auth/logout"), ("POST", "/api/auth/reset-password")}


def _endpoints():
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method.upper(), path


@pytest.mark.parametrize("method,path", sorted(_endpoints()))
def test_every_endpoint_requires_sign_in_unless_deliberately_public(method, path):
    """Adding an endpoint and forgetting its permission check makes this test fail."""
    anonymous = TestClient(app, raise_server_exceptions=False)
    url = re.sub(r"\{[^}]+\}", "X-1", path)
    r = anonymous.request(method, url, json={})
    if (method, path) in PUBLIC:
        assert r.status_code != 401 or path == "/api/auth/login", f"{method} {path} should be public"
    else:
        assert r.status_code == 401 and r.json()["code"] == "not_authenticated", f"{method} {path} is not protected!"


def test_permission_catalog_in_database_matches_the_code(db):
    assert set(db.scalars(select(Permission.code)).all()) == set(PERMISSIONS)
    roles = {r.name: {p.code for p in r.permissions} for r in db.scalars(select(Role)).all()}
    for builtin in BUILTIN_ROLES:
        assert roles[builtin.name] == set(builtin.permissions), builtin.name


# ---------------------------------------------------------------- the role matrix
EMP = {"employee_code": "E-0700", "first_name": "Matrix", "last_name": "Test", "email": "matrix@example.org",
       "job_title": "Tester", "department_id": "DEP-4001", "employment_status": "active", "joining_date": "2026-02-02"}
DEPT = {"name": "Matrix Dept", "code": "MTX"}
JOB = {"title": "Matrix Job", "department_id": "DEP-4001", "location": "Remote", "status": "open", "openings": 1,
       "description": "A job for the access matrix."}

#  (method, path, body)                                  super   hr_adm  hr_mgr  recruit employee
MATRIX = [
    (("GET", "/api/dashboard", None),                     (200,    200,    200,    200,    403)),
    (("GET", "/api/employees", None),                     (200,    200,    200,    403,    403)),
    (("GET", "/api/employees/EMP-5001", None),            (200,    200,    200,    403,    403)),
    (("POST", "/api/employees", EMP),                     (201,    201,    403,    403,    403)),
    (("PUT", "/api/employees/EMP-5002", {**EMP, "employee_code": "E-0002", "email": "marcus.lindqvist@example.com"}),
                                                          (200,    200,    403,    403,    403)),
    (("DELETE", "/api/employees/EMP-5012", None),         (204,    403,    403,    403,    403)),
    (("GET", "/api/departments", None),                   (200,    200,    200,    200,    403)),
    (("POST", "/api/departments", DEPT),                  (201,    201,    403,    403,    403)),
    (("GET", "/api/jobs", None),                          (200,    200,    200,    200,    403)),
    (("POST", "/api/jobs", JOB),                          (201,    201,    403,    201,    403)),
    (("GET", "/api/candidates", None),                    (200,    200,    200,    200,    403)),
    (("POST", "/api/candidates", {"full_name": "Matrix Cand", "email": "mc@example.org"}),
                                                          (201,    201,    403,    201,    403)),
    (("GET", "/api/applications", None),                  (200,    200,    200,    200,    403)),
    (("PATCH", "/api/applications/APP-3004/status", {"status": "screening"}),
                                                          (200,    200,    200,    200,    403)),
    (("GET", "/api/users", None),                         (200,    403,    403,    403,    403)),
    (("GET", "/api/roles", None),                         (200,    403,    403,    403,    403)),
    (("POST", "/api/roles", {"name": "auditor", "label": "Auditor", "permissions": []}),
                                                          (201,    403,    403,    403,    403)),
    (("POST", "/api/demo/reset", None),                   (200,    403,    403,    403,    403)),
    (("GET", "/api/me/employee", None),                   (404,    200,    200,    404,    200)),  # 404 = no linked record
    (("GET", "/api/meta", None),                          (200,    200,    200,    200,    200)),
]
ROLES = ["super_admin", "hr_admin", "hr_manager", "recruiter", "employee"]


@pytest.mark.parametrize("role_index,role", list(enumerate(ROLES)))
@pytest.mark.parametrize("request_spec,expected", MATRIX, ids=[f"{m} {p}" for (m, p, _), _ in MATRIX])
def test_role_matrix(as_role, role_index, role, request_spec, expected):
    method, path, body = request_spec
    r = as_role(role).request(method, path, json=body)
    assert r.status_code == expected[role_index], f"{role}: {method} {path} -> {r.status_code} {r.text[:200]}"
    if r.status_code == 403:
        assert r.json()["code"] == "forbidden"


# ---------------------------------------------------------------- employees and their own data (IDOR)
def test_employee_sees_only_their_own_record(as_role):
    me = as_role("employee")
    own = me.get("/api/me/employee").json()
    assert own["employee_code"] == "E-0003" and own["full_name"] == "Aisha Rahman"
    for other in ("EMP-5001", "EMP-5004", own["id"]):  # even their OWN id via the HR endpoint: HR data needs HR rights
        assert me.get(f"/api/employees/{other}").status_code == 403
    assert me.get("/api/employees", params={"search": "olivia"}).status_code == 403


def test_employee_can_only_change_their_own_phone(as_role):
    me = as_role("employee")
    r = me.patch("/api/me/employee", json={"phone": "+92 61 555 0101"})
    assert r.status_code == 200 and r.json()["phone"] == "+92 61 555 0101"
    for field in ({"job_title": "CEO"}, {"employment_status": "active"}, {"department_id": "DEP-4001"}, {"employee_code": "E-1"}):
        assert me.patch("/api/me/employee", json={"phone": "+92 61 555 0101", **field}).status_code == 422


def test_account_without_linked_record_gets_a_clear_404(as_role):
    r = as_role("recruiter").get("/api/me/employee")
    assert r.status_code == 404 and r.json()["code"] == "no_employee_record"


# ---------------------------------------------------------------- dashboard filtering happens on the server
@pytest.mark.parametrize("role,workforce,recruiting", [
    ("super_admin", True, True), ("hr_admin", True, True), ("hr_manager", True, True), ("recruiter", False, True)])
def test_dashboard_sections_follow_permissions(as_role, role, workforce, recruiting):
    d = as_role(role).get("/api/dashboard").json()
    assert (d["workforce"] is not None) is workforce and (d["recruiting"] is not None) is recruiting
    if not workforce:
        assert all(a["kind"] != "employee" for a in d["activity"])  # not even employee names in the activity feed


# ---------------------------------------------------------------- privilege escalation and lock-outs
def _uid(client, role):
    return next(u["id"] for u in client.get("/api/users", params={"search": USERS[role][0]}).json())


def _rid(client, name):
    return next(r["id"] for r in client.get("/api/roles").json() if r["name"] == name)


def test_hr_admin_cannot_assign_roles_or_manage_users(client, as_role):
    hr = as_role("hr_admin")
    target = _uid(client, "employee")
    assert hr.put(f"/api/users/{target}/roles", json={"role_ids": [_rid(client, "super_admin")]}).status_code == 403
    assert hr.patch(f"/api/users/{target}/status", json={"status": "disabled"}).status_code == 403
    assert hr.post(f"/api/users/{target}/reset-link").status_code == 403


def test_nobody_can_change_their_own_roles_or_status(client):
    me = client.get("/api/auth/me").json()["id"]
    r = client.put(f"/api/users/{me}/roles", json={"role_ids": [_rid(client, "employee")]})
    assert r.status_code == 403 and r.json()["code"] == "self_change"
    assert client.patch(f"/api/users/{me}/status", json={"status": "disabled"}).json()["code"] == "self_change"


def test_demoting_a_super_admin_takes_effect_immediately(client):
    second = _uid(client, "hr_admin")
    assert client.put(f"/api/users/{second}/roles", json={"role_ids": [_rid(client, "super_admin")]}).status_code == 200
    other_admin = sign_in(USERS["hr_admin"][0])
    root = _uid(client, "super_admin")
    # with two Super Administrators, one may demote the other ...
    assert other_admin.put(f"/api/users/{root}/roles", json={"role_ids": [_rid(client, "employee")]}).status_code == 200
    # ... and the demoted one loses access on their very next request (same browser, no re-login)
    assert client.get("/api/users").status_code == 403


def test_last_super_admin_cannot_be_disabled_or_demoted(client, db):
    from app.auth.models import User

    # make a second admin, then disable the first through the second; the remaining one is protected
    hr = _uid(client, "hr_admin")
    client.put(f"/api/users/{hr}/roles", json={"role_ids": [_rid(client, "super_admin")]})
    hr_admin_client = sign_in(USERS["hr_admin"][0])
    root = _uid(client, "super_admin")
    assert hr_admin_client.patch(f"/api/users/{root}/status", json={"status": "disabled"}).status_code == 200
    # a fresh account with roles:assign (but not super admin) tries to remove the last super admin
    helper = Role(name="helper", label="Helper", is_system=False,
                  permissions=list(db.scalars(select(Permission).where(Permission.code.in_(
                      ["users:read", "users:manage", "roles:assign", "roles:manage"] + sorted(PERMISSIONS)))).all()))
    db.add(helper)
    db.flush()
    db.scalar(select(User).where(User.email == USERS["recruiter"][0])).roles = [helper]
    db.commit()
    helper_client = sign_in(USERS["recruiter"][0])
    r = helper_client.patch(f"/api/users/{hr}/status", json={"status": "disabled"})
    assert r.status_code == 409 and r.json()["code"] == "last_super_admin"
    r = helper_client.put(f"/api/users/{hr}/roles", json={"role_ids": [_rid(helper_client, "employee")]})
    assert r.status_code == 409 and r.json()["code"] == "last_super_admin"


def test_cannot_grant_permissions_you_do_not_have(client, db):
    """A delegated 'user administrator' role may assign roles, but not more power than it holds itself."""
    from app.auth.models import User

    limited = Role(name="user_admin", label="User admin", is_system=False, permissions=list(db.scalars(
        select(Permission).where(Permission.code.in_(["users:read", "users:manage", "roles:assign", "roles:manage",
                                                       "profile:own"]))).all()))
    db.add(limited)
    db.flush()
    db.scalar(select(User).where(User.email == USERS["recruiter"][0])).roles = [limited]
    db.commit()
    ua = sign_in(USERS["recruiter"][0])
    target = _uid(client, "employee")
    r = ua.put(f"/api/users/{target}/roles", json={"role_ids": [_rid(client, "super_admin")]})
    assert r.status_code == 403 and r.json()["code"] == "privilege_escalation"
    r = ua.post("/api/roles", json={"name": "sneaky", "label": "Sneaky", "permissions": ["employees:delete"]})
    assert r.status_code == 403 and r.json()["code"] == "privilege_escalation"
    r = ua.post("/api/users", json={"full_name": "Sneaky Admin", "email": "sneak@example.org", "role_ids": [_rid(client, "hr_admin")]})
    assert r.status_code == 403 and r.json()["code"] == "privilege_escalation"
    assert ua.put(f"/api/users/{target}/roles", json={"role_ids": [_rid(client, "employee")]}).status_code == 200  # within its power


def test_role_administration_rules(client):
    roles = {r["name"]: r for r in client.get("/api/roles").json()}
    assert roles["super_admin"]["locked"] and roles["super_admin"]["is_system"]
    sa = roles["super_admin"]
    r = client.put(f"/api/roles/{sa['id']}", json={"label": sa["label"], "permissions": ["profile:own"]})
    assert r.status_code == 409 and r.json()["code"] == "locked_role"
    assert client.delete(f"/api/roles/{roles['hr_manager']['id']}").json()["code"] == "system_role"

    created = client.post("/api/roles", json={"name": "Auditor", "label": "Auditor", "description": "Read-only",
                                              "permissions": ["dashboard:view", "employees:read"]})
    assert created.status_code == 201 and created.json()["name"] == "auditor"
    assert client.post("/api/roles", json={"name": "auditor", "label": "Again"}).status_code == 409
    assert client.post("/api/roles", json={"name": "bad name!", "label": "Bad"}).status_code == 422
    assert client.post("/api/roles", json={"name": "ghost", "label": "Ghost", "permissions": ["nuke:all"]}).status_code == 422
    rid = created.json()["id"]
    target = _uid(client, "employee")
    client.put(f"/api/users/{target}/roles", json={"role_ids": [rid]})
    assert client.delete(f"/api/roles/{rid}").json()["code"] == "role_in_use"
    # the new role works immediately: the employee can now read employees, but still not edit them
    auditor = sign_in(USERS["employee"][0])
    assert auditor.get("/api/employees").status_code == 200
    assert auditor.delete("/api/employees/EMP-5001").status_code == 403
    client.put(f"/api/users/{target}/roles", json={"role_ids": [_rid(client, "employee")]})
    assert client.delete(f"/api/roles/{rid}").status_code == 204


def test_editing_a_role_changes_access_immediately(client, as_role):
    rec = as_role("recruiter")
    assert rec.get("/api/employees").status_code == 403
    role = next(r for r in client.get("/api/roles").json() if r["name"] == "recruiter")
    client.put(f"/api/roles/{role['id']}", json={"label": role["label"], "permissions": role["permissions"] + ["employees:read"]})
    assert rec.get("/api/employees").status_code == 200  # no re-login needed: permissions are checked on every request


def test_admin_can_link_an_account_to_an_employee_record(client):
    uid = _uid(client, "recruiter")
    r = client.patch(f"/api/users/{uid}", json={"full_name": "Remy Recruiter", "employee_id": "EMP-5007"})
    assert r.status_code == 200 and r.json()["employee"]["employee_code"] == "E-0007"
    taken = client.patch(f"/api/users/{_uid(client, 'hr_admin')}", json={"full_name": "Hilda Admin", "employee_id": "EMP-5007"})
    assert taken.status_code == 409 and "employee_id" in taken.json()["errors"]
    assert sign_in(USERS["recruiter"][0]).get("/api/me/employee").json()["employee_code"] == "E-0007"
    # deleting the employee record unlinks the account (ON DELETE SET NULL) instead of deleting the account
    assert client.delete("/api/employees/EMP-5007").status_code == 204
    assert client.get(f"/api/users/{uid}").json()["employee"] is None
