"""Registration, login, profile and access checks: routers/auth.py, deps.py."""

import pytest

from app.permissions import permissions_for
from tests.conftest import SEED_PASSWORD


def register(client, email="new@test.dev", password="secret123", name="Новый"):
    return client.post("/api/auth/register", json={"email": email, "password": password, "name": name})


def test_register_gives_token_and_welcome_bonus(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["user"]["role"] == "client"
    assert body["user"]["bonus_balance"] == 500

    history = client.get("/api/bonus", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert history["balance"] == 500
    assert history["history"][0]["amount"] == 500


def test_email_is_normalized_and_unique(client):
    assert register(client, email="  Mixed@Test.DEV ").json()["user"]["email"] == "mixed@test.dev"
    assert register(client, email="mixed@test.dev").status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "secret123", "name": "A"},
        {"email": "a@b.dev", "password": "123", "name": "A"},          # too short
        {"email": "a@b.dev", "password": "secret123", "name": ""},
    ],
)
def test_register_validation(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_login(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": "NEW@test.dev", "password": "secret123"})
    assert ok.status_code == 200 and ok.json()["token"]
    wrong = client.post("/api/auth/login", json={"email": "new@test.dev", "password": "nope"})
    assert wrong.status_code == 401
    unknown = client.post("/api/auth/login", json={"email": "ghost@test.dev", "password": "secret123"})
    assert unknown.status_code == 401


def test_seed_accounts_can_log_in(client):
    for role in ["admin", "manager", "engineer", "client"]:
        response = client.post("/api/auth/login", json={"email": f"{role}@store.dev", "password": SEED_PASSWORD})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == role
        assert response.json()["user"]["permissions"] == permissions_for(role)


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_and_profile_update(client, client_user):
    user, headers = client_user
    assert client.get("/api/auth/me", headers=headers).json()["id"] == user.id
    updated = client.patch("/api/auth/me", json={"name": "  Пётр  ", "phone": "+7999"}, headers=headers).json()
    assert updated["name"] == "Пётр" and updated["phone"] == "+7999"


def test_profile_update_cannot_change_role(client, client_user):
    _, headers = client_user
    response = client.patch("/api/auth/me", json={"role": "admin", "bonus_balance": 10**6}, headers=headers)
    assert response.json()["role"] == "client"
    assert response.json()["bonus_balance"] == 500


def test_blocked_user_is_rejected(client, make_user):
    user, headers = make_user("client", blocked=True)
    assert client.get("/api/auth/me", headers=headers).status_code == 403
    login = client.post("/api/auth/login", json={"email": user.email, "password": "secret123"})
    assert login.status_code == 403


def test_errors_follow_the_language(client):
    assert client.get("/api/auth/me").json()["detail"] == "Нужно войти в аккаунт"
    response = client.get("/api/auth/me", headers={"Accept-Language": "en"})
    assert response.json()["detail"] == "Please log in"
    assert response.headers["content-language"] == "en"
