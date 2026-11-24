"""Cart, orders, bonuses and order statuses: routers/cart.py, routers/orders.py, services/orders.py."""

import pytest

from tests.conftest import GOOD_BUILD

ADDRESS = {"address": "Москва, ул. Тестовая, 1", "phone": "+79990000000"}


@pytest.fixture
def ssd(product):
    return product("Kingston NV2 500GB NVMe")   # 3490 ₽


def add(client, headers, product_id, quantity=1):
    return client.post("/api/cart", json={"product_id": product_id, "quantity": quantity}, headers=headers)


def order(client, headers, bonus=0):
    return client.post("/api/orders", json={**ADDRESS, "bonus_to_use": bonus}, headers=headers)


def set_status(client, headers, order_id, status):
    return client.patch(f"/api/admin/orders/{order_id}/status", json={"status": status}, headers=headers)


# ---------- cart ----------

def test_cart_requires_login(client):
    assert client.get("/api/cart").status_code == 401


def test_add_increase_set_remove(client, client_user, ssd):
    _, headers = client_user
    assert add(client, headers, ssd.id).json()["count"] == 1
    cart = add(client, headers, ssd.id, 2).json()
    assert cart["count"] == 3 and cart["total"] == 3 * 3490
    assert cart["items"][0]["sum"] == 3 * 3490
    assert client.patch(f"/api/cart/{ssd.id}", json={"quantity": 1}, headers=headers).json()["count"] == 1
    assert client.patch(f"/api/cart/{ssd.id}", json={"quantity": 0}, headers=headers).json()["count"] == 0


def test_cart_max_bonus(client, make_user, ssd):
    _, rich = make_user(bonus=10_000)
    _, poor = make_user(bonus=500)
    assert add(client, rich, ssd.id).json()["max_bonus"] == 3490 * 30 // 100   # limited by 30%
    assert add(client, poor, ssd.id).json()["max_bonus"] == 500                # limited by balance


def test_cannot_add_more_than_stock(client, client_user, ssd):
    _, headers = client_user
    assert add(client, headers, ssd.id, ssd.stock + 1).status_code == 400
    add(client, headers, ssd.id, ssd.stock)
    assert add(client, headers, ssd.id, 1).status_code == 400   # already all of it in the cart


def test_cannot_add_hidden_or_unknown_product(client, client_user, db, ssd):
    _, headers = client_user
    assert add(client, headers, 999999).status_code == 404
    ssd.is_active = False
    db.flush()
    assert add(client, headers, ssd.id).status_code == 404


def test_add_many_from_builder(client, client_user, ids):
    _, headers = client_user
    cart = client.post("/api/cart/add-many", json={"product_ids": ids(GOOD_BUILD)}, headers=headers).json()
    assert cart["count"] == len(GOOD_BUILD)


def test_clear_cart_and_remove_item(client, client_user, ssd, product):
    _, headers = client_user
    add(client, headers, ssd.id)
    add(client, headers, product("Cougar GEX 650W").id)
    assert client.delete(f"/api/cart/{ssd.id}", headers=headers).json()["count"] == 1
    assert client.delete("/api/cart", headers=headers).json()["count"] == 0


def test_carts_are_separate(client, make_user, ssd):
    _, alice = make_user()
    _, bob = make_user()
    add(client, alice, ssd.id)
    assert client.get("/api/cart", headers=bob).json()["count"] == 0


# ---------- orders ----------

def test_empty_cart_cannot_be_ordered(client, client_user):
    _, headers = client_user
    assert order(client, headers).status_code == 400


def test_order_takes_stock_and_bonuses_and_clears_cart(client, client_user, ssd):
    user, headers = client_user
    stock = ssd.stock
    add(client, headers, ssd.id, 2)
    response = order(client, headers, bonus=500)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "new"
    assert body["subtotal"] == 6980 and body["bonus_used"] == 500 and body["total"] == 6480
    assert body["items"] == [{"product_id": ssd.id, "product_name": ssd.name, "quantity": 2, "price": 3490}]
    assert client.get("/api/cart", headers=headers).json()["count"] == 0
    assert client.get(f"/api/products/{ssd.id}").json()["stock"] == stock - 2
    bonus = client.get("/api/bonus", headers=headers).json()
    assert bonus["balance"] == 0 and bonus["history"][0]["amount"] == -500


@pytest.mark.parametrize("bonus", [1048, 501])   # 30% of 3490 = 1047; balance = 500
def test_bonus_limits(client, make_user, ssd, bonus):
    _, headers = make_user(bonus=500 if bonus == 501 else 10_000)
    add(client, headers, ssd.id)
    assert order(client, headers, bonus=bonus).status_code == 400


def test_stock_ran_out_after_adding_to_cart(client, client_user, db, ssd):
    _, headers = client_user
    add(client, headers, ssd.id, 2)
    ssd.stock = 1
    db.flush()
    assert order(client, headers).status_code == 400


def test_order_validation(client, client_user, ssd):
    _, headers = client_user
    add(client, headers, ssd.id)
    response = client.post("/api/orders", json={"address": "x", "phone": "1"}, headers=headers)
    assert response.status_code == 422


def test_my_orders_and_privacy(client, make_user, ssd):
    _, alice = make_user()
    _, bob = make_user()
    add(client, alice, ssd.id)
    order_id = order(client, alice).json()["id"]
    assert [o["id"] for o in client.get("/api/orders/my", headers=alice).json()] == [order_id]
    assert client.get("/api/orders/my", headers=bob).json() == []
    assert client.get(f"/api/orders/{order_id}", headers=bob).status_code == 404
    assert client.post(f"/api/orders/{order_id}/cancel", headers=bob).status_code == 404


def test_client_cancel_returns_stock_and_bonuses(client, client_user, ssd):
    _, headers = client_user
    stock = ssd.stock
    add(client, headers, ssd.id)
    order_id = order(client, headers, bonus=300).json()["id"]
    cancelled = client.post(f"/api/orders/{order_id}/cancel", headers=headers).json()
    assert cancelled["status"] == "cancelled"
    assert client.get("/api/bonus", headers=headers).json()["balance"] == 500
    assert client.get(f"/api/products/{ssd.id}").json()["stock"] == stock


def test_client_cannot_cancel_confirmed_order(client, client_user, manager_headers, ssd):
    _, headers = client_user
    add(client, headers, ssd.id)
    order_id = order(client, headers).json()["id"]
    set_status(client, manager_headers, order_id, "confirmed")
    assert client.post(f"/api/orders/{order_id}/cancel", headers=headers).status_code == 400


def test_full_lifecycle_gives_cashback(client, client_user, manager_headers, ssd):
    _, headers = client_user
    add(client, headers, ssd.id, 2)
    created = order(client, headers, bonus=500).json()
    for status in ["confirmed", "assembling", "shipped", "done"]:
        response = set_status(client, manager_headers, created["id"], status)
        assert response.status_code == 200, status
    cashback = created["total"] * 5 // 100
    assert response.json()["bonus_earned"] == cashback
    assert client.get("/api/bonus", headers=headers).json()["balance"] == cashback


@pytest.mark.parametrize(
    "path, bad",
    [([], "done"), ([], "shipped"), (["confirmed"], "new"), (["confirmed", "assembling", "shipped"], "cancelled"),
     (["confirmed", "assembling", "shipped", "done"], "cancelled"), (["cancelled"], "confirmed")],
)
def test_forbidden_status_transitions(client, client_user, manager_headers, ssd, path, bad):
    _, headers = client_user
    add(client, headers, ssd.id)
    order_id = order(client, headers).json()["id"]
    for status in path:
        assert set_status(client, manager_headers, order_id, status).status_code == 200
    assert set_status(client, manager_headers, order_id, bad).status_code == 400


def test_manager_cancel_after_confirm_returns_everything(client, client_user, manager_headers, ssd):
    _, headers = client_user
    stock = ssd.stock
    add(client, headers, ssd.id)
    order_id = order(client, headers, bonus=200).json()["id"]
    set_status(client, manager_headers, order_id, "confirmed")
    set_status(client, manager_headers, order_id, "cancelled")
    assert client.get("/api/bonus", headers=headers).json()["balance"] == 500
    assert client.get(f"/api/products/{ssd.id}").json()["stock"] == stock


def test_order_keeps_price_at_purchase_time(client, client_user, db, ssd):
    _, headers = client_user
    add(client, headers, ssd.id)
    order_id = order(client, headers).json()["id"]
    ssd.price = 99_999
    db.flush()
    assert client.get(f"/api/orders/{order_id}", headers=headers).json()["items"][0]["price"] == 3490
