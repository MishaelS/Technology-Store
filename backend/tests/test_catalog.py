"""Catalog, infinite scroll, news, facts and the home page: routers/catalog.py."""

import pytest

TOTAL_PRODUCTS = 43


def scroll(client, url):
    """Load every chunk like an infinite-scroll frontend would."""
    items, cursor, total = [], None, None
    while True:
        page = client.get(url + (f"&cursor={cursor}" if cursor else "")).json()
        items += page["items"]
        total = page.get("total")
        cursor = page["next_cursor"]
        if cursor is None:
            return items, total


def test_categories_are_translated(client):
    ru = client.get("/api/categories").json()
    en = client.get("/api/categories?lang=en").json()
    assert [c["slug"] for c in ru][:4] == ["cpu", "cooler", "motherboard", "gpu"]
    assert ru[0]["name"] == "Процессоры" and en[0]["name"] == "Processors"


@pytest.mark.parametrize("sort", ["new", "price_asc", "price_desc", "name"])
def test_infinite_scroll_returns_everything_once(client, sort):
    items, total = scroll(client, f"/api/products?limit=7&sort={sort}")
    ids = [p["id"] for p in items]
    assert len(ids) == len(set(ids)) == total == TOTAL_PRODUCTS


def test_sorting(client):
    asc, _ = scroll(client, "/api/products?limit=10&sort=price_asc")
    desc, _ = scroll(client, "/api/products?limit=10&sort=price_desc")
    names, _ = scroll(client, "/api/products?limit=10&sort=name")
    new, _ = scroll(client, "/api/products?limit=10&sort=new")
    assert [p["price"] for p in asc] == sorted(p["price"] for p in asc)
    assert [p["price"] for p in desc] == sorted((p["price"] for p in desc), reverse=True)
    assert [p["name"] for p in names] == sorted((p["name"] for p in names), key=lambda n: n)  # DB collation may differ
    assert [p["id"] for p in new] == sorted((p["id"] for p in new), reverse=True)


def test_new_product_during_scroll_is_not_duplicated(client, db, product):
    """A product added between chunks must not shift or duplicate the list."""
    first = client.get("/api/products?limit=10&sort=price_asc").json()
    clone = product("Kingston NV2 500GB NVMe")
    from app.models import Product
    db.add(Product(category_id=clone.category_id, name="Cheap one", brand="X", price=1, stock=1, specs={}))
    db.flush()
    rest, _ = scroll(client, f"/api/products?limit=10&sort=price_asc&cursor={first['next_cursor']}")
    ids = [p["id"] for p in first["items"] + rest]
    assert len(ids) == len(set(ids)) == TOTAL_PRODUCTS   # the new cheapest one is before the cursor


def test_last_chunk_has_no_cursor(client):
    page = client.get(f"/api/products?limit={TOTAL_PRODUCTS}").json()
    assert len(page["items"]) == TOTAL_PRODUCTS and page["next_cursor"] is None


@pytest.mark.parametrize(
    "query, expected",
    [
        ("category=gpu", 6),
        ("category=motherboard&socket=AM5", 2),
        ("category=ram&ram_type=DDR4", 3),
        ("search=ryzen", 5),
        ("search=RYZEN 7", 2),
        ("brand=samsung", 2),
        ("min_price=100000", 2),
        ("max_price=3000", 2),
        ("category=cpu&min_price=10000&max_price=30000", 4),
        ("search=%25", 0),          # % is escaped, not a wildcard
        ("search=_", 0),
    ],
)
def test_filters(client, query, expected):
    assert client.get(f"/api/products?{query}&limit=100").json()["total"] == expected


def test_discount_filter(client):
    items = client.get("/api/products?discount=true&limit=100").json()["items"]
    assert items and all(p["discount_percent"] > 0 and p["old_price"] > p["price"] for p in items)


def test_in_stock_filter_and_hidden_products(client, db, product):
    p = product("Kingston NV2 500GB NVMe")
    p.stock = 0
    hidden = product("NZXT H1 V2")
    hidden.is_active = False
    db.flush()
    in_stock = client.get("/api/products?in_stock=true&limit=100").json()
    assert p.id not in [x["id"] for x in in_stock["items"]]
    assert in_stock["total"] == TOTAL_PRODUCTS - 2
    assert client.get(f"/api/products/{hidden.id}").status_code == 404


def test_bad_params(client):
    assert client.get("/api/products?cursor=garbage").status_code == 400
    assert client.get("/api/products?limit=0").status_code == 422
    assert client.get("/api/products?limit=101").status_code == 422
    assert client.get("/api/products?sort=random").status_code == 422


def test_product_card(client, product):
    p = product("Intel Core i5-12400F")
    body = client.get(f"/api/products/{p.id}?lang=en").json()
    assert body["category"] == "cpu" and body["category_name"] == "Processors"
    assert body["specs"]["socket"] == "LGA1700"
    assert body["discount_percent"] == round((12990 - 11490) * 100 / 12990)
    assert client.get("/api/products/999999").status_code == 404


def test_brands(client):
    brands = client.get("/api/products/brands?category=cpu").json()
    assert brands == ["AMD", "Intel"]


def test_news_scroll_and_filter(client):
    items, _ = scroll(client, "/api/news?limit=4")
    assert len(items) == 6
    promos = client.get("/api/news?type=promo").json()["items"]
    assert len(promos) == 2 and all(n["type"] == "promo" for n in promos)
    assert client.get(f"/api/news/{items[0]['id']}").status_code == 200
    assert client.get("/api/news/999999").status_code == 404


def test_random_fact(client):
    assert client.get("/api/facts/random").json()["text"]


def test_home_page(client):
    home = client.get("/api/home").json()
    assert len(home["promos"]) == 2
    assert len(home["news"]) == 4                     # news + game
    assert 0 < len(home["discounts"]) <= 8
    assert len(home["hits"]) == 8
    assert home["fact"]["text"]
    percents = [p["discount_percent"] for p in home["discounts"]]
    assert percents == sorted(percents, reverse=True)
