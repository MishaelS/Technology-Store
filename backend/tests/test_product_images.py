"""More photos of a product (Product.images)."""

import pytest

PSU = {"category": "psu", "name": "БП с фото", "brand": "Test", "price": 5000, "stock": 3, "specs": {"wattage": 600},
       "image_url": "/uploads/main.png"}


def test_product_with_photos(client, employee_headers):
    body = {**PSU, "images": ["/uploads/side.png", "https://example.com/back.jpg"]}
    created = client.post("/api/admin/products", json=body, headers=employee_headers)
    assert created.status_code == 201
    product_id = created.json()["id"]
    public = client.get(f"/api/products/{product_id}").json()
    assert public["image_url"] == "/uploads/main.png"
    assert public["images"] == ["/uploads/side.png", "https://example.com/back.jpg"]


def test_photos_are_empty_by_default_and_can_be_changed(client, employee_headers):
    product_id = client.post("/api/admin/products", json=PSU, headers=employee_headers).json()["id"]
    assert client.get(f"/api/products/{product_id}").json()["images"] == []
    updated = client.patch(f"/api/admin/products/{product_id}", json={"images": ["/uploads/a.png"]}, headers=employee_headers)
    assert updated.json()["images"] == ["/uploads/a.png"]
    # other changes keep the photos
    assert client.patch(f"/api/admin/products/{product_id}", json={"price": 4000}, headers=employee_headers).json()["images"] == ["/uploads/a.png"]
    assert client.patch(f"/api/admin/products/{product_id}", json={"images": []}, headers=employee_headers).json()["images"] == []


@pytest.mark.parametrize("images", [
    ["javascript:alert(1)"],          # only http(s) links or paths on the site
    ["/ok.png"] * 11,                 # at most 10
    None,                             # null is not a list
])
def test_bad_photo_lists_are_rejected(client, employee_headers, images):
    product_id = client.post("/api/admin/products", json=PSU, headers=employee_headers).json()["id"]
    response = client.patch(f"/api/admin/products/{product_id}", json={"images": images}, headers=employee_headers)
    assert response.status_code == 422
    assert "detail" in response.json()
