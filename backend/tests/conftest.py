"""Shared test setup.

* A separate database `<name>_test` is created from scratch for every test run
  (via Alembic migrations, so migrations are tested too) and filled by app.seed.
* Every test runs inside a transaction that is rolled back afterwards,
  so tests don't affect each other and can be run in any order.
"""

import os

from sqlalchemy import create_engine, text

# --- point the app to the test database BEFORE importing it ---
MAIN_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://store:store@localhost:5432/store")
TEST_DB = MAIN_URL.rsplit("/", 1)[1] + "_test"
TEST_URL = MAIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB
os.environ["DATABASE_URL"] = TEST_URL
os.environ["SEED_PASSWORD"] = SEED_PASSWORD = "seed-password-for-tests"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Product, User  # noqa: E402
from app.security import create_token, hash_password  # noqa: E402
from app.seed import seed  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Recreate the test database, apply migrations and load seed data."""
    admin = create_engine(MAIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()

    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.upgrade(config, "head")
    seed()
    yield
    engine.dispose()


@pytest.fixture
def db():
    """DB session inside a transaction that is rolled back after the test.

    Code under test may call commit(): with create_savepoint it only commits a savepoint.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    """HTTP client for the API that uses the test session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------- helpers ----------

_PASSWORD_HASH = hash_password("secret123")  # hashing is slow, do it once


@pytest.fixture
def make_user(db):
    """Creates a user directly in the DB. Returns (user, auth headers)."""
    counter = iter(range(1, 10_000))

    def factory(role: str = "client", bonus: int = 0, blocked: bool = False):
        user = User(
            email=f"{role}{next(counter)}@test.dev", name=f"Test {role}", role=role,
            password_hash=_PASSWORD_HASH, bonus_balance=bonus, is_blocked=blocked,
        )
        db.add(user)
        db.flush()
        return user, {"Authorization": f"Bearer {create_token(user)}"}

    return factory


@pytest.fixture
def client_user(make_user):
    return make_user("client", bonus=500)


@pytest.fixture
def admin_headers(make_user):
    return make_user("admin")[1]


@pytest.fixture
def manager_headers(make_user):
    return make_user("manager")[1]


@pytest.fixture
def engineer_headers(make_user):
    return make_user("engineer")[1]


@pytest.fixture
def employee_headers(make_user):
    return make_user("employee")[1]


@pytest.fixture
def senior_engineer_headers(make_user):
    return make_user("senior_engineer")[1]


@pytest.fixture
def product(db):
    """Find a seeded product by its exact name."""

    def find(name: str) -> Product:
        found = db.scalar(select(Product).where(Product.name == name))
        assert found is not None, f"no product {name!r} in seed data"
        return found

    return find


# Builds from seed data, used in several test files
GOOD_BUILD = [
    "AMD Ryzen 5 7600",
    "MSI MAG B650 TOMAHAWK WIFI",
    "G.Skill Flare X5 32GB (2x16) DDR5-6000",
    "MSI GeForce RTX 4060 VENTUS 2X 8GB",
    "Cougar GEX 650W",
    "Fractal Design Pop Air",
    "Samsung 980 1TB NVMe",
]

BAD_BUILD = [
    "AMD Ryzen 5 7600",                          # AM5 ...
    "ASUS PRIME B760-PLUS D4",                   # ... on an LGA1700 / DDR4 / ATX board
    "G.Skill Flare X5 32GB (2x16) DDR5-6000",    # DDR5 memory
    "ASUS TUF Radeon RX 7900 XTX 24GB",          # 352 mm, 355 W
    "DEEPCOOL PF450 450W",                       # too weak
    "NZXT H1 V2",                                # Mini-ITX only, GPU up to 324 mm
    "Samsung 980 1TB NVMe",
]


@pytest.fixture
def ids(product):
    """Product names -> ids."""
    return lambda names: [product(n).id for n in names]
