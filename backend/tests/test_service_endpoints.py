"""Service endpoints and app setup: health, languages, CORS (main.py), migrations vs models."""

import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database import Base, engine


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_language_list(client):
    languages = {item["code"]: item["name"] for item in client.get("/api/i18n").json()}
    assert languages["ru"] == "Русский" and languages["en"] == "English"


def test_language_texts(client):
    assert client.get("/api/i18n/en").json()["nav"]["catalog"] == "Catalog"
    missing = client.get("/api/i18n/de", headers={"Accept-Language": "en"})
    assert missing.status_code == 404 and missing.json()["detail"] == 'Language "de" not found'


def test_cors_allows_the_frontend(client):
    origin = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")[0]
    response = client.options("/api/products", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
    })
    assert response.headers["access-control-allow-origin"] == origin


def test_migrations_match_models():
    """If this fails: you changed models.py but forgot to create a migration."""
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
