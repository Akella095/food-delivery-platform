import pytest

from tests.conftest import make_token

pytestmark = pytest.mark.asyncio


async def _create_restaurant_with_menu_item(client):
    admin_token = make_token("admin-9", "admin")
    restaurant_resp = await client.post(
        "/api/restaurants",
        json={"name": "Taco Town", "address": "Fourth St 4"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    restaurant_id = restaurant_resp.json()["id"]

    menu_resp = await client.post(
        f"/api/restaurants/{restaurant_id}/menu",
        json={"name": "Taco", "description": "Spicy", "price": "4.50"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    menu_item_id = menu_resp.json()["id"]
    return restaurant_id, menu_item_id


async def test_create_order_as_customer(client):
    restaurant_id, menu_item_id = await _create_restaurant_with_menu_item(client)
    customer_token = make_token("customer-1", "customer")

    response = await client.post(
        "/api/orders",
        json={"restaurant_id": restaurant_id, "items": [{"menu_item_id": menu_item_id, "quantity": 2}]},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert float(data["total_price"]) == 9.0


async def test_create_order_requires_authentication(client):
    restaurant_id, menu_item_id = await _create_restaurant_with_menu_item(client)
    response = await client.post(
        "/api/orders",
        json={"restaurant_id": restaurant_id, "items": [{"menu_item_id": menu_item_id, "quantity": 1}]},
    )
    assert response.status_code == 401


async def test_customer_can_only_see_own_orders(client):
    restaurant_id, menu_item_id = await _create_restaurant_with_menu_item(client)
    customer_token = make_token("customer-2", "customer")
    other_customer_token = make_token("customer-3", "customer")

    await client.post(
        "/api/orders",
        json={"restaurant_id": restaurant_id, "items": [{"menu_item_id": menu_item_id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    own_orders = await client.get("/api/orders", headers={"Authorization": f"Bearer {customer_token}"})
    assert own_orders.status_code == 200
    assert len(own_orders.json()) == 1

    other_orders = await client.get(
        "/api/orders", headers={"Authorization": f"Bearer {other_customer_token}"}
    )
    assert other_orders.status_code == 200
    assert len(other_orders.json()) == 0


async def test_courier_can_update_order_status(client):
    restaurant_id, menu_item_id = await _create_restaurant_with_menu_item(client)
    customer_token = make_token("customer-4", "customer")
    courier_token = make_token("courier-1", "courier")

    order_resp = await client.post(
        "/api/orders",
        json={"restaurant_id": restaurant_id, "items": [{"menu_item_id": menu_item_id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    order_id = order_resp.json()["id"]

    status_resp = await client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "on_the_way"},
        headers={"Authorization": f"Bearer {courier_token}"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "on_the_way"
    assert status_resp.json()["courier_id"] == "courier-1"


async def test_create_order_with_invalid_menu_item_fails(client):
    restaurant_id, _ = await _create_restaurant_with_menu_item(client)
    customer_token = make_token("customer-5", "customer")

    response = await client.post(
        "/api/orders",
        json={"restaurant_id": restaurant_id, "items": [{"menu_item_id": "unknown-id", "quantity": 1}]},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 400
