import pytest

pytestmark = pytest.mark.asyncio


async def test_register_user_success(client):
    response = await client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "secret123", "full_name": "Alice"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["role"] == "customer"


async def test_register_duplicate_email_fails(client):
    payload = {"email": "bob@example.com", "password": "secret123", "full_name": "Bob"}
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 400


async def test_login_success_returns_token(client):
    await client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "password": "secret123", "full_name": "Carol"},
    )
    response = await client.post(
        "/api/auth/login", json={"email": "carol@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_invalid_password_fails(client):
    await client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "password": "secret123", "full_name": "Dave"},
    )
    response = await client.post(
        "/api/auth/login", json={"email": "dave@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client):
    response = await client.get("/api/users/me")
    assert response.status_code == 401
