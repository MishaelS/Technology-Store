"""Admin panel: role permissions, stats, products, builds, news, facts, users (routers/admin.py)."""

import pytest

from tests.conftest import GOOD_BUILD

# (method, url, roles that are allowed)
ENDPOINTS = [
    ("GET", "/api/admin/stats", {"admin", "manager"}),
    ("GET", "/api/admin/orders", {"admin", "manager"}),
    ("GET", "/api/admin/products", {"admin", "engineer"}),
    ("GET", "/api/admin/builds", {"admin", "engineer"}),
    ("GET", "/api/admin/facts", {"admin", "manager"}),
    ("GET", "/api/admin/users", {"admin"}),
]


@pytest.mark.parametrize("method, url, allowed", ENDPOINTS)
@pytest.mark.parametrize("role", ["client", "manager", "engineer", "admin"])
def test_role_permissions(client, make_user, method, url, allowed, role):
    _, headers = make_user(role)
    expected = 200 if role in allowed else 403
    assert client.request(method, url, headers=headers).status_code == expected


@pytest.mark.parametrize("method, url, allowed", ENDPOINTS)
def test_guest_gets_401(client, method, url, allowed):
    assert client.request(method, url).status_code == 401


# ---------- stats and orders ----------

def test_stats(client, manager_headers, client_user, product):
    _, headers = client_user
    ssd = product("Kingston NV2 500GB NVMe")
    client.post("/api/cart", json={"product_id": ssd.id, "quantity": 3}, headers=headers)
    client.post("/api/orders", json={"address": "Москва, 1", "phone": "+7999000"}, headers=headers)
    stats = client.get("/api/admin/stats", headers=manager_headers).json()
    assert stats["orders_by_status"]["new"] >= 1
    assert stats["revenue_active"] >= 3 * 3490
    assert stats["top_products"][0] == {"product_id": ssd.id, "name": ssd.name, "sold": 3}
    assert stats["users_total"] >= 5


def test_orders_list_filters_and_pages(client, manager_headers, make_user, product):
    user, headers = make_user()
    ssd = product("Kingston NV2 500GB NVMe")
    for _ in range(3):
        client.post("/api/cart", json={"product_id": ssd.id}, headers=headers)
        client.post("/api/orders", json={"address": "Москва, 1", "phone": "+7999000"}, headers=headers)
    page = client.get(f"/api/admin/orders?search={user.email}&page_size=2", headers=manager_headers).json()
    assert page["total"] == 3 and page["pages"] == 2 and len(page["items"]) == 2
    assert page["items"][0]["user"]["email"] == user.email
    by_number = client.get(f"/api/admin/orders?search=%23{page['items'][0]['id']}", headers=manager_headers).json()
    assert by_number["total"] >= 1
    assert client.get("/api/admin/orders?status=done", headers=manager_headers).json()["total"] == 0
    assert client.patch("/api/admin/orders/999999/status", json={"status": "confirmed"},
                        headers=manager_headers).status_code == 404


# ---------- products ----------

NEW_PSU = {"category": "psu", "name": "Тестовый БП", "brand": "Test", "price": 5000, "stock": 3,
           "specs": {"wattage": 600}}


def test_create_update_delete_product(client, engineer_headers):
    created = client.post("/api/admin/products", json=NEW_PSU, headers=engineer_headers)
    assert created.status_code == 201
    product_id = created.json()["id"]
    assert client.get(f"/api/products/{product_id}").json()["name"] == "Тестовый БП"

    updated = client.patch(f"/api/admin/products/{product_id}", json={"price": 4000, "old_price": 5000},
                           headers=engineer_headers).json()
    assert updated["discount_percent"] == 20

    assert client.delete(f"/api/admin/products/{product_id}", headers=engineer_headers).status_code == 204
    assert client.get(f"/api/products/{product_id}").status_code == 404           # hidden from the catalog
    admin_list = client.get("/api/admin/products?search=Тестовый", headers=engineer_headers).json()
    assert admin_list["items"][0]["is_active"] is False                           # but still in the admin list


@pytest.mark.parametrize(
    "change, status",
    [
        ({"specs": {}}, 422),                       # wattage is required for a PSU
        ({"category": "nope"}, 400),
        ({"price": 0}, 422),
        ({"old_price": 4000}, 422),                 # old price must be higher than price
        ({"name": None}, 422),
    ],
)
def test_product_validation(client, engineer_headers, change, status):
    assert client.post("/api/admin/products", json={**NEW_PSU, **change}, headers=engineer_headers).status_code == status


def test_update_validation(client, engineer_headers, product):
    p = product("Cougar GEX 650W")
    url = f"/api/admin/products/{p.id}"
    assert client.patch(url, json={"price": None}, headers=engineer_headers).status_code == 422
    assert client.patch(url, json={"specs": {"color": "black"}}, headers=engineer_headers).status_code == 422
    assert client.patch("/api/admin/products/999999", json={"stock": 1}, headers=engineer_headers).status_code == 404


def test_product_deleted_after_order_stays_in_order(client, client_user, engineer_headers, product):
    _, headers = client_user
    ssd = product("Kingston NV2 500GB NVMe")
    client.post("/api/cart", json={"product_id": ssd.id}, headers=headers)
    order_id = client.post("/api/orders", json={"address": "Москва, 1", "phone": "+7999000"}, headers=headers).json()["id"]
    client.delete(f"/api/admin/products/{ssd.id}", headers=engineer_headers)
    assert client.get(f"/api/orders/{order_id}", headers=headers).json()["items"][0]["product_name"] == ssd.name


# ---------- builds ----------

def test_engineer_comments_build(client, client_user, engineer_headers, ids):
    _, headers = client_user
    build_id = client.post("/api/builds", json={"name": "A", "product_ids": ids(GOOD_BUILD)}, headers=headers).json()["id"]
    waiting = client.get("/api/admin/builds?without_comment=true&page_size=100", headers=engineer_headers).json()
    assert build_id in [b["id"] for b in waiting["items"]]

    commented = client.patch(f"/api/admin/builds/{build_id}/comment", json={"comment": "Отличная сборка"},
                             headers=engineer_headers)
    assert commented.json()["engineer_comment"] == "Отличная сборка"
    assert client.get(f"/api/builds/{build_id}", headers=headers).json()["engineer_comment"] == "Отличная сборка"
    waiting = client.get("/api/admin/builds?without_comment=true&page_size=100", headers=engineer_headers).json()
    assert build_id not in [b["id"] for b in waiting["items"]]


# ---------- news and facts ----------

def test_news_crud(client, manager_headers):
    created = client.post("/api/admin/news", json={"title": "Акция", "text": "Текст", "type": "promo"},
                          headers=manager_headers).json()
    assert client.get("/api/home").json()["promos"][0]["id"] == created["id"]
    updated = client.patch(f"/api/admin/news/{created['id']}", json={"title": "Новая"}, headers=manager_headers)
    assert updated.json()["title"] == "Новая"
    assert client.patch(f"/api/admin/news/{created['id']}", json={"title": None},
                        headers=manager_headers).status_code == 422
    assert client.post("/api/admin/news", json={"title": "A", "text": "B", "type": "ads"},
                       headers=manager_headers).status_code == 422
    assert client.delete(f"/api/admin/news/{created['id']}", headers=manager_headers).status_code == 204
    assert client.get(f"/api/news/{created['id']}").status_code == 404


def test_facts_crud(client, manager_headers):
    before = len(client.get("/api/admin/facts", headers=manager_headers).json())
    fact = client.post("/api/admin/facts", json={"text": "Новый факт"}, headers=manager_headers).json()
    assert len(client.get("/api/admin/facts", headers=manager_headers).json()) == before + 1
    assert client.delete(f"/api/admin/facts/{fact['id']}", headers=manager_headers).status_code == 204
    assert client.delete(f"/api/admin/facts/{fact['id']}", headers=manager_headers).status_code == 404


# ---------- users ----------

def test_admin_changes_role_and_blocks(client, make_user):
    admin, admin_headers = make_user("admin")
    user, user_headers = make_user()
    assert client.patch(f"/api/admin/users/{user.id}", json={"role": "engineer"},
                        headers=admin_headers).json()["role"] == "engineer"
    assert client.get("/api/admin/products", headers=user_headers).status_code == 200   # new role works at once
    client.patch(f"/api/admin/users/{user.id}", json={"is_blocked": True}, headers=admin_headers)
    assert client.get("/api/auth/me", headers=user_headers).status_code == 403
    assert client.patch(f"/api/admin/users/{user.id}", json={"role": "boss"}, headers=admin_headers).status_code == 422


def test_admin_cannot_change_self(client, make_user):
    admin, headers = make_user("admin")
    assert client.patch(f"/api/admin/users/{admin.id}", json={"role": "client"}, headers=headers).status_code == 400
    assert client.patch(f"/api/admin/users/{admin.id}", json={"is_blocked": True}, headers=headers).status_code == 400


def test_users_search_and_role_filter(client, admin_headers):
    engineers = client.get("/api/admin/users?role=engineer", headers=admin_headers).json()
    assert all(u["role"] == "engineer" for u in engineers["items"])
    found = client.get("/api/admin/users?search=manager@store", headers=admin_headers).json()
    assert [u["email"] for u in found["items"]] == ["manager@store.dev"]


def test_manual_bonus(client, admin_headers, client_user):
    user, headers = client_user
    url = f"/api/admin/users/{user.id}/bonus"
    assert client.post(url, json={"amount": 100, "reason": "Подарок"}, headers=admin_headers).json()["bonus_balance"] == 600
    assert client.post(url, json={"amount": -600, "reason": "Списание"}, headers=admin_headers).json()["bonus_balance"] == 0
    assert client.post(url, json={"amount": -1, "reason": "x"}, headers=admin_headers).status_code == 400
    assert client.post(url, json={"amount": 0, "reason": "x"}, headers=admin_headers).status_code == 400
    history = client.get("/api/bonus", headers=headers).json()["history"]
    assert [h["reason"] for h in history[:2]] == ["Списание", "Подарок"]
