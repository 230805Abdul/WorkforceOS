import pytest


async def _login(client, email, password):
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def _register(client, email, password, role):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test", "role": role},
    )


@pytest.mark.asyncio
async def test_candidate_cannot_create_job(client):
    await _register(client, "cand1@test.com", "StrongPass123!", "candidate")
    token = await _login(client, "cand1@test.com", "StrongPass123!")

    resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "...", "department": "Eng", "location": "Remote"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recruiter_can_create_job(client):
    await _register(client, "rec1@test.com", "StrongPass123!", "recruiter")
    token = await _login(client, "rec1@test.com", "StrongPass123!")

    resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "...", "department": "Eng", "location": "Remote"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_candidate_cannot_read_audit_logs(client):
    await _register(client, "cand2@test.com", "StrongPass123!", "candidate")
    token = await _login(client, "cand2@test.com", "StrongPass123!")

    resp = await client.get("/api/v1/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_read_audit_logs(client):
    await _register(client, "admin1@test.com", "StrongPass123!", "admin")
    token = await _login(client, "admin1@test.com", "StrongPass123!")

    resp = await client.get("/api/v1/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_token_rejected_everywhere(client):
    resp = await client.get("/api/v1/admin/audit-logs", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
