"""API behaviour tests (run against whatever database tests/conftest.py selected)."""
from app.db import engine

JOB = {"title": "QA Engineer", "department_id": "DEP-4001", "location": "Remote", "employment_type": "full_time",
       "status": "open", "openings": 1, "description": "Test our product thoroughly."}
CAND = {"full_name": "Test Person", "email": "test.person@example.com", "phone": "", "source": "referral"}


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert "active" in client.get("/api/meta").json()["employment_statuses"]


def test_job_crud_and_validation(client):
    r = client.post("/api/jobs", json=JOB)
    assert r.status_code == 201
    jid = r.json()["id"]
    assert client.get(f"/api/jobs/{jid}").json()["title"] == "QA Engineer"

    r = client.put(f"/api/jobs/{jid}", json={**JOB, "title": "Senior QA Engineer"})
    assert r.status_code == 200 and r.json()["title"] == "Senior QA Engineer"

    bad = client.post("/api/jobs", json={**JOB, "title": "x", "openings": 0})
    assert bad.status_code == 422
    assert set(bad.json()["errors"]) == {"title", "openings"}
    bad_dept = client.post("/api/jobs", json={**JOB, "department_id": "DEP-9999"})
    assert bad_dept.status_code == 422 and "department_id" in bad_dept.json()["errors"]

    assert client.delete(f"/api/jobs/{jid}").status_code == 204
    assert client.get(f"/api/jobs/{jid}").status_code == 404
    assert client.delete(f"/api/jobs/{jid}").status_code == 404


def test_job_search_filter_sort(client):
    assert all("Engineer" in j["title"] for j in client.get("/api/jobs", params={"search": "engineer"}).json())
    assert all(j["status"] == "draft" for j in client.get("/api/jobs", params={"status": "draft"}).json())
    titles = [j["title"] for j in client.get("/api/jobs", params={"sort": "title", "order": "asc"}).json()]
    assert titles == sorted(titles, key=str.lower)
    assert client.get("/api/jobs", params={"sort": "bogus"}).status_code == 422


def test_candidate_crud_and_duplicate_email(client):
    r = client.post("/api/candidates", json=CAND)
    assert r.status_code == 201 and r.json()["phone"] is None
    cid = r.json()["id"]
    dup = client.post("/api/candidates", json={**CAND, "email": "TEST.PERSON@example.com"})
    assert dup.status_code == 409 and "email" in dup.json()["errors"]
    assert client.post("/api/candidates", json={**CAND, "email": "not-an-email"}).json()["errors"]["email"]
    assert client.put(f"/api/candidates/{cid}", json={**CAND, "full_name": "Renamed Person"}).status_code == 200
    assert client.delete(f"/api/candidates/{cid}").status_code == 204


def test_application_flow_and_state_machine(client):
    cid = client.post("/api/candidates", json=CAND).json()["id"]
    jid = client.post("/api/jobs", json=JOB).json()["id"]
    r = client.post("/api/applications", json={"candidate_id": cid, "job_id": jid})
    assert r.status_code == 201 and r.json()["allowed_next"] == ["screening", "rejected"]
    aid = r.json()["id"]

    assert client.post("/api/applications", json={"candidate_id": cid, "job_id": jid}).status_code == 409
    assert client.patch(f"/api/applications/{aid}/status", json={"status": "hired"}).status_code == 400
    for step in ("screening", "interview", "offer", "hired"):
        assert client.patch(f"/api/applications/{aid}/status", json={"status": step}).status_code == 200
    assert client.patch(f"/api/applications/{aid}/status", json={"status": "applied"}).status_code == 400

    # openings (1) are now filled: a second hire must be refused
    cid2 = client.post("/api/candidates", json={**CAND, "email": "second@example.com"}).json()["id"]
    aid2 = client.post("/api/applications", json={"candidate_id": cid2, "job_id": jid}).json()["id"]
    for step in ("screening", "interview", "offer"):
        client.patch(f"/api/applications/{aid2}/status", json={"status": step})
    assert client.patch(f"/api/applications/{aid2}/status", json={"status": "hired"}).status_code == 409
    # and openings can't drop below the hires already made
    assert client.put(f"/api/jobs/{jid}", json={**JOB, "openings": 1}).status_code == 200


def test_cannot_apply_to_non_open_job(client):
    cid = client.post("/api/candidates", json=CAND).json()["id"]
    draft = client.post("/api/jobs", json={**JOB, "status": "draft"}).json()["id"]
    assert client.post("/api/applications", json={"candidate_id": cid, "job_id": draft}).status_code == 409
    assert client.post("/api/applications", json={"candidate_id": "CAN-0", "job_id": draft}).status_code == 404


def test_cascade_delete_keeps_data_consistent(client):
    job = client.get("/api/jobs", params={"search": "Senior Backend"}).json()[0]
    assert job["applications_count"] > 0
    before = len(client.get("/api/applications").json())
    client.delete(f"/api/jobs/{job['id']}")
    after = client.get("/api/applications").json()
    assert len(after) == before - job["applications_count"]
    assert all(a["job_id"] != job["id"] for a in after)


def test_dashboard_matches_underlying_data(client):
    d = client.get("/api/dashboard").json()
    rec = d["recruiting"]
    assert rec["kpis"]["total_candidates"] == len(client.get("/api/candidates").json())
    assert rec["kpis"]["open_roles"] == len(client.get("/api/jobs", params={"status": "open"}).json())
    assert sum(p["count"] for p in rec["pipeline"]) == len(client.get("/api/applications").json())
    client.post("/api/candidates", json=CAND)
    assert client.get("/api/dashboard").json()["recruiting"]["kpis"]["total_candidates"] == rec["kpis"]["total_candidates"] + 1


def test_reset_and_unknown_route(client):
    client.post("/api/jobs", json=JOB)
    client.post("/api/demo/reset")
    jobs = client.get("/api/jobs", params={"sort": "created_at", "order": "asc"}).json()
    assert len(jobs) == 8 and min(j["id"] for j in jobs) == "JOB-1001"  # ID counters restart too
    r = client.get("/api/nope")
    assert r.status_code == 404 and "detail" in r.json()


def test_counts_and_count_sorting_match_the_real_applications(client):
    apps = client.get("/api/applications").json()
    for order in ("asc", "desc"):
        jobs = client.get("/api/jobs", params={"sort": "applications_count", "order": order}).json()
        counts = [j["applications_count"] for j in jobs]
        assert counts == sorted(counts, reverse=order == "desc")
        for j in jobs:
            mine = [a for a in apps if a["job_id"] == j["id"]]
            assert j["applications_count"] == len(mine)
            assert j["hired_count"] == sum(a["status"] == "hired" for a in mine)
    cands = client.get("/api/candidates", params={"sort": "applications_count", "order": "desc"}).json()
    assert cands[0]["applications_count"] == max(len([a for a in apps if a["candidate_id"] == c["id"]]) for c in cands)
