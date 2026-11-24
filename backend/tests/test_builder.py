"""PC builder API and saved builds: routers/builder.py (rules themselves: test_compatibility.py)."""

from tests.conftest import BAD_BUILD, GOOD_BUILD


def check(client, product_ids, lang="ru"):
    return client.post(f"/api/builder/check?lang={lang}", json={"product_ids": product_ids})


def errors(result):
    return {c["code"] for c in result["checks"] if c["status"] == "error"}


def test_good_build(client, ids):
    result = check(client, ids(GOOD_BUILD)).json()
    assert result["is_compatible"] and result["is_complete"]
    assert result["tier"] == "gaming" and result["tier_name"] == "Игровой ПК (Full HD)"
    assert result["total_price"] == sum(
        p["price"] for p in client.get("/api/products?limit=100").json()["items"] if p["name"] in GOOD_BUILD
    )


def test_bad_build_finds_all_problems(client, ids):
    result = check(client, ids(BAD_BUILD)).json()
    assert errors(result) == {"socket", "ram_type", "psu", "gpu_length", "form_factor"}
    assert not result["is_compatible"]


def test_check_in_english(client, ids):
    result = check(client, ids(BAD_BUILD), lang="en").json()
    socket = next(c for c in result["checks"] if c["code"] == "socket")
    assert socket["message"] == "CPU socket AM5 doesn't fit a motherboard with socket LGA1700"


def test_guest_can_check_and_unknown_ids_fail(client, ids):
    assert check(client, ids(GOOD_BUILD)).status_code == 200
    assert check(client, [999999]).status_code == 400
    assert check(client, []).json()["is_complete"] is False


def test_save_list_get_delete_build(client, client_user, ids):
    _, headers = client_user
    created = client.post("/api/builds", json={"name": " Игровой ", "product_ids": ids(GOOD_BUILD)}, headers=headers)
    assert created.status_code == 201
    build = created.json()
    assert build["name"] == "Игровой" and len(build["items"]) == len(GOOD_BUILD)
    assert build["check"]["is_compatible"]
    assert [b["id"] for b in client.get("/api/builds", headers=headers).json()] == [build["id"]]
    assert client.get(f"/api/builds/{build['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/builds/{build['id']}", headers=headers).status_code == 204
    assert client.get("/api/builds", headers=headers).json() == []


def test_builds_are_private_but_visible_to_staff(client, make_user, engineer_headers, ids):
    _, alice = make_user()
    _, bob = make_user()
    build_id = client.post("/api/builds", json={"name": "A", "product_ids": ids(GOOD_BUILD)}, headers=alice).json()["id"]
    assert client.get(f"/api/builds/{build_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/builds/{build_id}", headers=bob).status_code == 404
    assert client.get(f"/api/builds/{build_id}", headers=engineer_headers).status_code == 200
    assert client.delete(f"/api/builds/{build_id}", headers=engineer_headers).status_code == 403


def test_save_requires_login_and_valid_data(client, client_user, ids):
    _, headers = client_user
    assert client.post("/api/builds", json={"name": "A", "product_ids": ids(GOOD_BUILD)}).status_code == 401
    assert client.post("/api/builds", json={"name": "", "product_ids": ids(GOOD_BUILD)}, headers=headers).status_code == 422
    assert client.post("/api/builds", json={"name": "A", "product_ids": []}, headers=headers).status_code == 422
