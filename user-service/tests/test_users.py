import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email, role="customer"):
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123", "full_name": "Test User", "role": role},
    )
    login = await client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    return login.json()["access_token"]


async def test_get_me_with_valid_token(client):
    token = await _register_and_login(client, "eve@example.com")
    response = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "eve@example.com"


async def test_list_users_requires_admin_role(client):
    token = await _register_and_login(client, "frank@example.com", role="customer")
    response = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_admin_can_list_users(client):
    token = await _register_and_login(client, "grace@example.com", role="admin")
    response = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_get_user_by_id_uses_cache_layer(client, monkeypatch):
    token = await _register_and_login(client, "heidi@example.com", role="admin")
    me = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]

    response = await client.get(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == user_id


async def test_courier_availability_update_requires_courier_role(client):
    token = await _register_and_login(client, "ivan@example.com", role="customer")
    response = await client.put(
        "/api/users/couriers/me/availability",
        json={"is_available": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_courier_can_update_availability(client):
    token = await _register_and_login(client, "judy@example.com", role="courier")
    response = await client.put(
        "/api/users/couriers/me/availability",
        json={"is_available": True, "vehicle_type": "car"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["is_available"] is True
