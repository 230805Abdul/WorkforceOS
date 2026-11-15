import pytest


@pytest.mark.asyncio
async def test_register_new_user(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "StrongPass123!", "full_name": "New User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@test.com"
    assert "hashed_password" not in body  # never leak the hash


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(client):
    payload = {"email": "dupe@test.com", "password": "StrongPass123!", "full_name": "Dupe"}
    first = await client.post("/api/v1/auth/register", json=payload)
    second = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_success_returns_tokens(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@test.com", "password": "StrongPass123!", "full_name": "Login Test"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": "login@test.com", "password": "StrongPass123!"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpw@test.com", "password": "StrongPass123!", "full_name": "T"},
    )
    resp = await client.post("/api/v1/auth/login", json={"email": "wrongpw@test.com", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_valid_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401  # no Authorization header at all


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "me@test.com", "password": "StrongPass123!", "full_name": "Me"},
    )
    login = await client.post("/api/v1/auth/login", json={"email": "me@test.com", "password": "StrongPass123!"})
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"
