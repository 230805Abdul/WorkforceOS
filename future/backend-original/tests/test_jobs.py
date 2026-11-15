import pytest


async def _recruiter_token(client, email="jobrec@test.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Rec", "role": "recruiter"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123!"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_and_list_jobs(client):
    token = await _recruiter_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/jobs",
        json={
            "title": "Platform Engineer",
            "description": "Build the platform",
            "department": "Eng",
            "location": "Dubai",
        },
        headers=headers,
    )
    assert create.status_code == 201

    listing = await client.get("/api/v1/jobs")
    assert listing.status_code == 200
    titles = [j["title"] for j in listing.json()]
    assert "Platform Engineer" in titles


@pytest.mark.asyncio
async def test_job_list_is_cached_then_invalidated(client, monkeypatch):
    # Patch the cache layer to an in-memory dict so the test doesn't need real Redis.
    store: dict = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ttl_seconds=60):
        store[key] = value

    async def fake_invalidate(pattern):
        store.clear()

    import app.api.v1.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "cache_get", fake_get)
    monkeypatch.setattr(jobs_module, "cache_set", fake_set)
    monkeypatch.setattr(jobs_module, "cache_invalidate", fake_invalidate)

    token = await _recruiter_token(client, email="cachetest@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.get("/api/v1/jobs")
    assert first.status_code == 200
    assert "jobs:list:open" in store  # populated on first read

    await client.post(
        "/api/v1/jobs",
        json={"title": "Cache Test Role", "description": "...", "department": "Eng", "location": "Remote"},
        headers=headers,
    )
    assert store == {}  # creating a job invalidated the cache


@pytest.mark.asyncio
async def test_update_nonexistent_job_returns_404(client):
    token = await _recruiter_token(client, email="jobrec404@test.com")
    resp = await client.patch(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        json={"title": "Whatever"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
