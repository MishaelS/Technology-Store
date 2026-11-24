"""Edge cases and bad input across the API: whitespace, wrong types, unsafe links, error format."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADDRESS = {"address": "Москва, ул. Тестовая, 1", "phone": "+7 (999) 123-45-67"}


@pytest.fixture
def cart_with_ssd(client, client_user, product):
    _, headers = client_user
    client.post("/api/cart", json={"product_id": product("Kingston NV2 500GB NVMe").id}, headers=headers)
    return headers


# ---------- whitespace-only text ----------

@pytest.mark.parametrize("field", ["address", "phone"])
def test_order_fields_cannot_be_only_spaces(client, cart_with_ssd, field):
    response = client.post("/api/orders", json={**ADDRESS, field: "        "}, headers=cart_with_ssd)
    assert response.status_code == 422


def test_register_name_cannot_be_only_spaces(client):
    response = client.post("/api/auth/register", json={"email": "a@b.dev", "password": "secret123", "name": "   "})
    assert response.status_code == 422


def test_build_name_cannot_be_only_spaces(client, client_user, ids):
    _, headers = client_user
    response = client.post("/api/builds", json={"name": "   ", "product_ids": ids(["Cougar GEX 650W"])}, headers=headers)
    assert response.status_code == 422


def test_news_title_cannot_be_only_spaces(client, manager_headers):
    response = client.post("/api/admin/news", json={"title": "  ", "text": "Текст"}, headers=manager_headers)
    assert response.status_code == 422


def test_text_is_trimmed(client, cart_with_ssd):
    order = client.post("/api/orders", json={"address": "  Москва, 1  ", "phone": " +79990001122 "},
                        headers=cart_with_ssd).json()
    assert order["address"] == "Москва, 1" and order["phone"] == "+79990001122"


# ---------- phone ----------

@pytest.mark.parametrize("phone", ["abcdefgh", "+7 (999) <script>", "12-34"])
def test_bad_phone(client, cart_with_ssd, phone):
    assert client.post("/api/orders", json={**ADDRESS, "phone": phone}, headers=cart_with_ssd).status_code == 422


@pytest.mark.parametrize("phone", ["+7 (999) 123-45-67", "89991234567", "+1 202 555 0100"])
def test_good_phone(client, cart_with_ssd, phone):
    assert client.post("/api/orders", json={**ADDRESS, "phone": phone}, headers=cart_with_ssd).status_code == 201


def test_bad_phone_in_profile(client, client_user):
    _, headers = client_user
    assert client.patch("/api/auth/me", json={"phone": "call me"}, headers=headers).status_code == 422


# ---------- product specs types (wrong types used to crash the PC builder) ----------

PSU = {"category": "psu", "name": "БП", "brand": "Test", "price": 5000, "stock": 1}


@pytest.mark.parametrize(
    "category, specs",
    [
        ("psu", {"wattage": "650"}),                                                      # string instead of number
        ("psu", {"wattage": -5}),
        ("cpu", {"socket": "AM5", "cores": 6, "tdp": 65, "score": 150}),                  # score is 0..100
        ("cpu", {"socket": "AM5", "cores": 6, "tdp": 65, "score": 50, "igpu": "yes"}),
        ("cpu", {"socket": 5, "cores": 6, "tdp": 65, "score": 50}),
        ("case", {"form_factors": "ATX", "max_gpu_mm": 300}),                             # must be a list
        ("case", {"form_factors": ["ATX", 1], "max_gpu_mm": 300}),
        ("ram", {"ram_type": "DDR5", "size_gb": 16, "sticks": True}),                     # bool is not a number
    ],
)
def test_wrong_spec_types_are_rejected(client, engineer_headers, category, specs):
    response = client.post("/api/admin/products", json={**PSU, "category": category, "specs": specs},
                           headers=engineer_headers)
    assert response.status_code == 422


def test_builder_survives_product_with_float_specs(client, engineer_headers, ids):
    created = client.post("/api/admin/products", json={**PSU, "specs": {"wattage": 650.5}}, headers=engineer_headers)
    assert created.status_code == 201
    check = client.post("/api/builder/check", json={"product_ids": ids(["AMD Ryzen 5 7600"]) + [created.json()["id"]]})
    assert check.status_code == 200


def test_wrong_specs_rejected_on_update(client, engineer_headers, product):
    p = product("Cougar GEX 650W")
    response = client.patch(f"/api/admin/products/{p.id}", json={"specs": {"wattage": "a lot"}}, headers=engineer_headers)
    assert response.status_code == 422


# ---------- links ----------

@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "ftp://x.dev/a.png", "img.png"])
def test_unsafe_image_links_are_rejected(client, engineer_headers, manager_headers, url):
    product = client.post("/api/admin/products", json={**PSU, "specs": {"wattage": 500}, "image_url": url},
                          headers=engineer_headers)
    news = client.post("/api/admin/news", json={"title": "A", "text": "B", "image_url": url}, headers=manager_headers)
    assert product.status_code == 422 and news.status_code == 422


@pytest.mark.parametrize("url", ["https://cdn.example.com/a.png", "http://localhost/a.png", "/images/a.png"])
def test_safe_image_links_are_accepted(client, engineer_headers, url):
    response = client.post("/api/admin/products", json={**PSU, "specs": {"wattage": 500}, "image_url": url},
                           headers=engineer_headers)
    assert response.status_code == 201


# ---------- error format ----------

def test_validation_error_has_text_detail_and_fields(client):
    response = client.post("/api/auth/register", json={"email": "bad", "password": "1", "name": "A"})
    body = response.json()
    assert response.status_code == 422
    assert isinstance(body["detail"], str)
    assert {f["field"] for f in body["fields"]} == {"email", "password"}


def test_validation_error_is_translated(client):
    ru = client.post("/api/auth/register", json={}).json()["detail"]
    en = client.post("/api/auth/register?lang=en", json={}).json()["detail"]
    assert ru != en and en.startswith("Check")


def test_unexpected_error_returns_json(client, monkeypatch):
    import app.routers.catalog as catalog

    def boom(db):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(catalog, "_random_fact", boom)
    with TestClient(app, raise_server_exceptions=False) as raw:
        response = raw.get("/api/facts/random?lang=en")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error. Please try again later"}
    assert "exploded" not in response.text          # internal details are not leaked


# ---------- login ----------

def test_login_checks_a_password_even_for_unknown_email(client, monkeypatch):
    """Otherwise unknown emails answer faster and can be detected by timing."""
    import app.routers.auth as auth

    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, h: calls.append(1) or real(p, h))
    client.post("/api/auth/login", json={"email": "ghost@nowhere.dev", "password": "secret123"})
    assert calls == [1]


# ---------- stats ----------

def test_stats_list_every_order_status(client, manager_headers):
    statuses = client.get("/api/admin/stats", headers=manager_headers).json()["orders_by_status"]
    assert set(statuses) == {"new", "confirmed", "assembling", "shipped", "done", "cancelled"}
    assert all(isinstance(v, int) for v in statuses.values())
