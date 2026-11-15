"""Departments and employees: CRUD, relationships, constraints and the hired-candidate -> employee link."""
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Department, Employee

DEPT = {"name": "Customer Success", "code": "cs", "description": "Keeps customers happy."}
EMP = {"employee_code": "e-0100", "first_name": "Zara", "last_name": "Khan", "email": "zara.khan@example.org",
       "phone": "", "job_title": "Support Specialist", "department_id": "DEP-4001", "employment_status": "active",
       "joining_date": "2026-01-15"}


# ---------- departments CRUD ----------
def test_department_crud(client):
    r = client.post("/api/departments", json=DEPT)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["code"] == "CS" and d["employees_count"] == 0 and d["is_sample"] is False  # code upper-cased, real record
    assert client.get(f"/api/departments/{d['id']}").json()["name"] == "Customer Success"

    r = client.put(f"/api/departments/{d['id']}", json={**DEPT, "name": "Customer Experience", "description": ""})
    assert r.status_code == 200 and r.json()["name"] == "Customer Experience" and r.json()["description"] is None

    assert client.delete(f"/api/departments/{d['id']}").status_code == 204
    assert client.get(f"/api/departments/{d['id']}").status_code == 404


def test_department_list_search_and_counts(client):
    rows = client.get("/api/departments").json()
    assert [r["name"] for r in rows] == sorted(r["name"] for r in rows)  # default: by name
    eng = next(r for r in rows if r["name"] == "Engineering")
    assert eng["employees_count"] == 4 and eng["active_employees_count"] == 3 and eng["jobs_count"] == 2
    assert [r["code"] for r in client.get("/api/departments", params={"search": "fin"}).json()] == ["FIN"]
    top = client.get("/api/departments", params={"sort": "employees_count", "order": "desc"}).json()[0]
    assert top["name"] == "Engineering"


def test_department_names_and_codes_are_unique(client):
    r = client.post("/api/departments", json={"name": "engineering", "code": "XYZ"})
    assert r.status_code == 409 and "name" in r.json()["errors"]
    r = client.post("/api/departments", json={"name": "Brand New", "code": "eng"})
    assert r.status_code == 409 and "code" in r.json()["errors"]
    bad = client.post("/api/departments", json={"name": "X", "code": "not ok!"})
    assert bad.status_code == 422 and {"name", "code"} <= set(bad.json()["errors"])


def test_department_in_use_cannot_be_deleted(client):
    r = client.delete("/api/departments/DEP-4001")  # Engineering: has jobs and employees
    assert r.status_code == 409
    assert "employee" in r.json()["detail"] and "job" in r.json()["detail"]
    assert client.get("/api/departments/DEP-4001").status_code == 200


def test_database_itself_restricts_deleting_a_used_department(db):
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM departments WHERE code = 'ENG'"))  # raw SQL: bypasses the API check
        db.commit()


# ---------- employees CRUD ----------
def test_employee_crud(client):
    r = client.post("/api/employees", json=EMP)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["employee_code"] == "E-0100" and e["full_name"] == "Zara Khan" and e["phone"] is None
    assert e["department"] == "Engineering" and e["candidate_id"] is None and e["is_sample"] is False
    assert client.get(f"/api/employees/{e['id']}").json()["email"] == "zara.khan@example.org"

    r = client.put(f"/api/employees/{e['id']}", json={**EMP, "employment_status": "on_leave", "department_id": "DEP-4006"})
    assert r.status_code == 200 and r.json()["employment_status"] == "on_leave" and r.json()["department"] == "Operations"

    assert client.delete(f"/api/employees/{e['id']}").status_code == 204
    assert client.get(f"/api/employees/{e['id']}").status_code == 404


def test_employee_validation(client):
    r = client.post("/api/employees", json={**EMP, "email": "nope", "first_name": "", "joining_date": "1900-01-01",
                                            "employment_status": "retired", "department_id": "DEP-9999"})
    assert r.status_code == 422
    assert {"email", "first_name", "joining_date", "employment_status"} <= set(r.json()["errors"])
    r = client.post("/api/employees", json={**EMP, "department_id": "DEP-9999"})
    assert r.status_code == 422 and r.json()["errors"] == {"department_id": "Select a valid department"}


def test_employee_codes_and_emails_are_unique(client):
    r = client.post("/api/employees", json={**EMP, "employee_code": "e-0001"})
    assert r.status_code == 409 and "employee_code" in r.json()["errors"]
    r = client.post("/api/employees", json={**EMP, "email": "OLIVIA.HART@example.com"})
    assert r.status_code == 409 and "email" in r.json()["errors"]


def test_employee_uniqueness_is_enforced_by_the_database(db):
    dept = db.query(Department).first()
    for dup in ({"employee_code": "E-0001", "email": "new1@example.org"}, {"employee_code": "E-9999", "email": "Olivia.Hart@EXAMPLE.com"}):
        db.add(Employee(first_name="A", last_name="B", job_title="X", department_id=dept.id, employment_status="active",
                        joining_date=date(2026, 1, 1), **dup))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_employee_list_search_filter_sort(client):
    assert len(client.get("/api/employees").json()) == 13
    assert [e["full_name"] for e in client.get("/api/employees", params={"search": "olivia"}).json()] == ["Olivia Hart"]
    assert [e["employee_code"] for e in client.get("/api/employees", params={"search": "e-0004"}).json()] == ["E-0004"]
    assert [e["full_name"] for e in client.get("/api/employees", params={"search": "Mei Lin Chen"}).json()] == ["Mei Lin Chen"]
    term = client.get("/api/employees", params={"employment_status": "terminated"}).json()
    assert [e["full_name"] for e in term] == ["Sara Eriksson"]
    sales = client.get("/api/employees", params={"department_id": "DEP-4004"}).json()
    assert {e["department"] for e in sales} == {"Sales"} and len(sales) == 3
    dates = [e["joining_date"] for e in client.get("/api/employees", params={"sort": "joining_date", "order": "desc"}).json()]
    assert dates == sorted(dates, reverse=True)
    assert client.get("/api/employees/next-code").json() == {"employee_code": "E-0014"}


# ---------- candidate -> employee ----------
def _hire(client, candidate_email="lucas.moreau@example.com"):
    cand = next(c for c in client.get("/api/candidates", params={"search": candidate_email}).json())
    app = next(a for a in client.get("/api/applications", params={"candidate_id": cand["id"]}).json())
    for step in ("screening", "interview", "offer", "hired"):  # Lucas starts at "applied"
        client.patch(f"/api/applications/{app['id']}/status", json={"status": step})
    return cand, app


def test_only_hired_candidates_become_employees_and_only_once(client):
    not_hired = client.get("/api/candidates", params={"search": "kenji"}).json()[0]
    r = client.post("/api/employees", json={**EMP, "candidate_id": not_hired["id"]})
    assert r.status_code == 409 and r.json()["errors"]["candidate_id"] == "This candidate has not been hired yet"

    cand, app = _hire(client)
    r = client.post("/api/employees", json={**EMP, "first_name": "Lucas", "last_name": "Moreau",
                                            "email": cand["email"], "candidate_id": cand["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["candidate_id"] == cand["id"]
    linked = client.get("/api/applications", params={"candidate_id": cand["id"]}).json()[0]
    assert linked["employee_id"] == r.json()["id"]  # the pipeline card now knows

    again = client.post("/api/employees", json={**EMP, "employee_code": "E-0200", "email": "other@example.org", "candidate_id": cand["id"]})
    assert again.status_code == 409 and "already has an employee record" in again.json()["errors"]["candidate_id"]


def test_deleting_the_candidate_keeps_the_employee(client):
    mei = client.get("/api/employees", params={"search": "Mei Lin"}).json()[0]
    assert mei["candidate_id"] == "CAN-2007"
    assert client.delete("/api/candidates/CAN-2007").status_code == 204
    after = client.get(f"/api/employees/{mei['id']}").json()
    assert after["full_name"] == "Mei Lin Chen" and after["candidate_id"] is None  # ON DELETE SET NULL


# ---------- dashboard ----------
def test_dashboard_workforce_metrics_follow_the_data(client):
    k = client.get("/api/dashboard").json()["workforce"]
    assert k["kpis"]["total_employees"] == 13 and k["kpis"]["active_employees"] == 11 and k["kpis"]["total_departments"] == 8
    assert {s["status"]: s["count"] for s in k["employment_status"]} == {"active": 11, "on_leave": 1, "terminated": 1}
    by_dept = {d["department"]: d["count"] for d in k["employees_by_department"]}
    assert by_dept["Engineering"] == 3  # the terminated engineer is not counted
    client.post("/api/employees", json=EMP)
    k2 = client.get("/api/dashboard").json()["workforce"]
    assert k2["kpis"]["total_employees"] == 14 and k2["kpis"]["active_employees"] == 12
    assert {d["department"]: d["count"] for d in k2["employees_by_department"]}["Engineering"] == 4
