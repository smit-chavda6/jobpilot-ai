"""Unit and integration tests for Authentication and Session flows."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_registration_success(client: AsyncClient):
    payload = {
        "email": "candidate@example.com",
        "password": "StrongPassword123!",
        "full_name": "Jane Candidate",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "csrf_token" in data
    assert data["user"]["email"] == "candidate@example.com"
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_duplicate_registration_fails(client: AsyncClient):
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "full_name": "Test User",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    err = res2.json()
    assert "error" in err
    assert "already exists" in err["error"]["message"]


@pytest.mark.asyncio
async def test_login_success_and_failure(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@example.com",
            "password": "CorrectPassword123!",
            "full_name": "Login User",
        },
    )

    # Valid Login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@example.com", "password": "CorrectPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token

    # Invalid Password
    bad_pw_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@example.com", "password": "WrongPassword!"},
    )
    assert bad_pw_res.status_code == 401
    assert "Invalid email or password" in bad_pw_res.json()["error"]["message"]

    # Non-existent User (generic error, no enumeration)
    non_existent_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword!"},
    )
    assert non_existent_res.status_code == 401
    assert "Invalid email or password" in non_existent_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "SecretPassword123!",
            "full_name": "Me User",
        },
    )
    token = reg.json()["access_token"]

    # Call with Bearer header
    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"

    # Call without auth header or cookies
    client.cookies.clear()
    unauth = await client.get("/api/v1/auth/me")
    assert unauth.status_code == 401
