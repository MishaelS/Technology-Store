"""Repairs: routers/repairs.py."""

import pytest

NEW_REPAIR = {
    "client_name": "Анна Клиент",
    "client_phone": "+7 900 111-22-33",
    "device": "Ноутбук ASUS",
    "problem": "Не включается",
}


def create(client, headers, **extra):
    return client.post("/api/admin/repairs", json={**NEW_REPAIR, **extra}, headers=headers)


def move(client, headers, repair_id, **body):
    return client.patch(f"/api/admin/repairs/{repair_id}", json=body, headers=headers)


def test_engineer_accepts_a_device(client, make_user):
    engineer, headers = make_user("engineer")
    response = create(client, headers)
    assert response.status_code == 201
    repair = response.json()
    assert repair["status"] == "accepted"
    assert repair["client_id"] is None
    assert repair["engineer"]["id"] == engineer.id


def test_full_repair_lifecycle(client, engineer_headers):
    repair_id = create(client, engineer_headers).json()["id"]
    assert move(client, engineer_headers, repair_id, status="diagnostics").status_code == 200
    updated = move(client, engineer_headers, repair_id, status="repairing", price=3500,
                   engineer_comment="Замена разъёма питания").json()
    assert updated["price"] == 3500 and updated["engineer_comment"] == "Замена разъёма питания"
    assert move(client, engineer_headers, repair_id, status="ready").json()["status"] == "ready"
    assert move(client, engineer_headers, repair_id, status="issued").json()["status"] == "issued"


def test_ready_needs_a_price(client, engineer_headers):
    repair_id = create(client, engineer_headers).json()["id"]
    move(client, engineer_headers, repair_id, status="diagnostics")
    response = move(client, engineer_headers, repair_id, status="ready")
    assert response.status_code == 400
    assert response.json()["detail"] == "Сначала укажите стоимость ремонта"
    assert move(client, engineer_headers, repair_id, status="ready", price=0).status_code == 200  # free repair


@pytest.mark.parametrize(
    "path, bad",
    [([], "ready"), ([], "issued"), (["diagnostics"], "accepted"), (["cancelled"], "diagnostics")],
)
def test_forbidden_transitions(client, engineer_headers, path, bad):
    repair_id = create(client, engineer_headers, price=1000).json()["id"]
    for status in path:
        assert move(client, engineer_headers, repair_id, status=status).status_code == 200
    assert move(client, engineer_headers, repair_id, status=bad).status_code == 400


def test_client_sees_own_repairs(client, client_user, make_user, engineer_headers):
    user, headers = client_user
    create(client, engineer_headers, client_email=user.email.upper())
    _, other = make_user()
    assert [r["device"] for r in client.get("/api/repairs/my", headers=headers).json()] == ["Ноутбук ASUS"]
    assert client.get("/api/repairs/my", headers=other).json() == []
    assert client.get("/api/admin/repairs", headers=headers).status_code == 403


def test_unknown_client_email(client, engineer_headers):
    response = create(client, engineer_headers, client_email="ghost@nowhere.dev")
    assert response.status_code == 400


@pytest.mark.parametrize("field, value", [("client_phone", "call me"), ("device", "   "), ("price", -1)])
def test_validation(client, engineer_headers, field, value):
    assert create(client, engineer_headers, **{field: value}).status_code == 422


def test_search_and_filter(client, engineer_headers):
    repair_id = create(client, engineer_headers, device="Видеокарта MSI").json()["id"]
    create(client, engineer_headers)
    found = client.get("/api/admin/repairs?search=видеокарта", headers=engineer_headers).json()
    assert [r["id"] for r in found["items"]] == [repair_id]
    assert client.get(f"/api/admin/repairs?search=%23{repair_id}", headers=engineer_headers).json()["total"] == 1
    accepted = client.get("/api/admin/repairs?status=accepted&page_size=100", headers=engineer_headers).json()
    assert all(r["status"] == "accepted" for r in accepted["items"])


def test_get_one_and_404(client, engineer_headers):
    repair_id = create(client, engineer_headers).json()["id"]
    assert client.get(f"/api/admin/repairs/{repair_id}", headers=engineer_headers).json()["id"] == repair_id
    assert client.get("/api/admin/repairs/999999", headers=engineer_headers).status_code == 404
