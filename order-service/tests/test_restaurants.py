import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


async def test_create_restaurant_requires_admin(client):
    token = make_token("user-1", "customer")
    response = await client.post(
        "/api/restaurants",
        json={"name": "Pizza Place", "address": "Main St 1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_admin_can_create_restaurant_and_list_it(client):
    token = make_token("admin-1", "admin")
    create_resp = await client.post(
        "/api/restaurants",
        json={"name": "Sushi Bar", "address": "Second St 2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201

    list_resp = await client.get("/api/restaurants")
    assert list_resp.status_code == 200
    names = [r["name"] for r in list_resp.json()]
    assert "Sushi Bar" in names


async def test_add_menu_item_and_fetch_restaurant(client):
    token = make_token("admin-2", "admin")
    create_resp = await client.post(
        "/api/restaurants",
        json={"name": "Burger House", "address": "Third St 3"},
        headers={"Authorization": f"Bearer {token}"},
    )
    restaurant_id = create_resp.json()["id"]

    menu_resp = await client.post(
        f"/api/restaurants/{restaurant_id}/menu",
        json={"name": "Cheeseburger", "description": "Tasty", "price": "9.99"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert menu_resp.status_code == 201

    detail_resp = await client.get(f"/api/restaurants/{restaurant_id}")
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["menu_items"]) == 1


async def test_get_unknown_restaurant_returns_404(client):
    response = await client.get("/api/restaurants/does-not-exist")
    assert response.status_code == 404
