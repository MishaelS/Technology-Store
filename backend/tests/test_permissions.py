"""Role permissions: app/permissions.py and how the API exposes and enforces them."""

import pytest

from app.models import ROLES
from app.permissions import PERMISSIONS, ROLE_PERMISSIONS
from tests.conftest import GOOD_BUILD


def test_every_role_has_a_permission_set():
    assert set(ROLE_PERMISSIONS) == set(ROLES)
    for role, permissions in ROLE_PERMISSIONS.items():
        assert permissions <= set(PERMISSIONS), role


def test_admin_has_everything_and_client_nothing():
    assert ROLE_PERMISSIONS["admin"] == set(PERMISSIONS)
    assert ROLE_PERMISSIONS["client"] == set()


@pytest.mark.parametrize("role", ROLES)
def test_me_returns_permissions(client, make_user, role):
    _, headers = make_user(role)
    assert set(client.get("/api/auth/me", headers=headers).json()["permissions"]) == ROLE_PERMISSIONS[role]


def test_new_role_applies_without_new_token(client, make_user, admin_headers):
    user, headers = make_user("client")
    assert client.get("/api/admin/stats", headers=headers).status_code == 403
    client.patch(f"/api/admin/users/{user.id}", json={"role": "manager"}, headers=admin_headers)
    me = client.get("/api/auth/me", headers=headers).json()
    assert "stats.view" in me["permissions"]
    assert client.get("/api/admin/stats", headers=headers).status_code == 200


def test_roles_endpoint(client, admin_headers, manager_headers):
    roles = {r["role"]: set(r["permissions"]) for r in client.get("/api/admin/roles", headers=admin_headers).json()}
    assert roles == {role: set(p) for role, p in ROLE_PERMISSIONS.items()}
    assert client.get("/api/admin/roles", headers=manager_headers).status_code == 403


def test_engineer_cannot_see_other_peoples_orders(client, client_user, engineer_headers, manager_headers, product):
    _, headers = client_user
    client.post("/api/cart", json={"product_id": product("Kingston NV2 500GB NVMe").id}, headers=headers)
    order_id = client.post("/api/orders", json={"address": "Москва, 1", "phone": "+7999000"}, headers=headers).json()["id"]
    assert client.get(f"/api/orders/{order_id}", headers=engineer_headers).status_code == 404
    assert client.get(f"/api/orders/{order_id}", headers=manager_headers).status_code == 200


def test_manager_cannot_see_other_peoples_builds(client, client_user, engineer_headers, manager_headers, ids):
    _, headers = client_user
    build_id = client.post("/api/builds", json={"name": "A", "product_ids": ids(GOOD_BUILD)}, headers=headers).json()["id"]
    assert client.get(f"/api/builds/{build_id}", headers=manager_headers).status_code == 404
    assert client.get(f"/api/builds/{build_id}", headers=engineer_headers).status_code == 200


def test_permission_error_is_translated(client, client_user):
    _, headers = client_user
    assert client.get("/api/admin/stats", headers=headers).json()["detail"] == "Недостаточно прав"
    assert client.get("/api/admin/stats?lang=en", headers=headers).json()["detail"] == "Access denied"
