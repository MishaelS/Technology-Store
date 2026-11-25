"""Stock receipts (routers/stock.py) and the tech support page (routers/system.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------- stock receipts ----------

def test_employee_receives_a_delivery(client, make_user, product):
    employee, headers = make_user("employee")
    ssd = product("Kingston NV2 500GB NVMe")
    before = ssd.stock
    response = client.post("/api/admin/stock/receipts", headers=headers,
                           json={"product_id": ssd.id, "quantity": 25, "supplier": "ООО Поставщик"})
    assert response.status_code == 201
    receipt = response.json()
    assert receipt["product"]["stock"] == before + 25
    assert receipt["received_by"]["id"] == employee.id
    assert client.get(f"/api/products/{ssd.id}").json()["stock"] == before + 25


def test_receipts_log(client, employee_headers, product):
    ssd, psu = product("Kingston NV2 500GB NVMe"), product("Cougar GEX 650W")
    for p, qty in [(ssd, 5), (psu, 3), (ssd, 7)]:
        client.post("/api/admin/stock/receipts", json={"product_id": p.id, "quantity": qty}, headers=employee_headers)
    log = client.get(f"/api/admin/stock/receipts?product_id={ssd.id}", headers=employee_headers).json()
    assert [r["quantity"] for r in log["items"]] == [7, 5]


@pytest.mark.parametrize("quantity", [0, -5, 100_001])
def test_bad_quantity(client, employee_headers, product, quantity):
    body = {"product_id": product("Cougar GEX 650W").id, "quantity": quantity}
    assert client.post("/api/admin/stock/receipts", json=body, headers=employee_headers).status_code == 422


def test_unknown_product(client, employee_headers):
    body = {"product_id": 999999, "quantity": 1}
    assert client.post("/api/admin/stock/receipts", json=body, headers=employee_headers).status_code == 404


def test_engineer_cannot_receive(client, engineer_headers, product):
    body = {"product_id": product("Cougar GEX 650W").id, "quantity": 1}
    assert client.post("/api/admin/stock/receipts", json=body, headers=engineer_headers).status_code == 403


# ---------- tech support ----------

def test_system_info(client, senior_engineer_headers):
    info = client.get("/api/admin/system", headers=senior_engineer_headers).json()
    assert info["database"]["ok"] is True
    assert info["database"]["version"].startswith("PostgreSQL")
    assert info["database"]["migration"]
    assert info["counts"]["products"] >= 41
    assert info["uptime_seconds"] >= 0


def test_server_errors_are_logged_and_can_be_cleared(client, senior_engineer_headers, monkeypatch):
    import app.routers.catalog as catalog

    def boom(db):
        raise RuntimeError("test failure for the error log")

    monkeypatch.setattr(catalog, "_random_fact", boom)
    with TestClient(app, raise_server_exceptions=False) as raw:
        assert raw.get("/api/facts/random").status_code == 500

    errors = client.get("/api/admin/system", headers=senior_engineer_headers).json()["recent_errors"]
    assert errors[0]["path"] == "/api/facts/random"
    assert "test failure for the error log" in errors[0]["error"]

    assert client.delete("/api/admin/system/errors", headers=senior_engineer_headers).status_code == 204
    assert client.get("/api/admin/system", headers=senior_engineer_headers).json()["recent_errors"] == []


def test_system_is_hidden_from_others(client, employee_headers, engineer_headers):
    assert client.get("/api/admin/system", headers=employee_headers).status_code == 403
    assert client.delete("/api/admin/system/errors", headers=engineer_headers).status_code == 403
