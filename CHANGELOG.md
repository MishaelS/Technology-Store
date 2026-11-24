# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project has no releases yet, so all changes are listed under **Unreleased**.

## [Unreleased]

### Added

- Project plan and commit message guidelines (`docs/COMMITS.md`).
- Docker Compose setup: PostgreSQL, backend API and Adminer.
- Backend on FastAPI with SQLAlchemy models and Alembic migrations.
- Registration and login with JWT tokens; a welcome bonus of 500 points on sign-up.
- Roles (client, manager, engineer, admin) with permissions defined in one place (`app/permissions.py`).
- `permissions` in `GET /api/auth/me`, so the frontend shows only what the user is allowed to use.
- `GET /api/admin/roles` with every role and its permissions.
- Product catalog with filters, search, sorting and cursor-based infinite scroll.
- News feed with infinite scroll, random facts and a home page endpoint.
- Cart, orders with stock control and order status workflow.
- Bonus system: pay up to 30% of an order with points, 5% cashback on completed orders, refunds on cancel.
- PC builder: compatibility checks (socket, memory type and slots, PSU wattage, GPU length, form factor, graphics) and a performance score with PC tiers.
- Saved builds with engineer comments.
- Admin panel API: stats, orders, products, client builds, news, facts, users, roles and manual bonuses.
- Seed data: 41 products, news, facts and one account per role.
- Russian and English translations in `resources/locales`, language selection by `?lang=` or `Accept-Language`, and `GET /api/i18n` endpoints.
- Locale checker script (`backend/scripts/check_locales.py`).
- Automated tests (pytest) for every part of the backend, running on a separate test database.
- Documentation: setup, API, tests and translations guides in `docs/`.
- `run.sh`: one script to set up, start, stop, test and maintain the project (`./run.sh help`). It checks Docker, creates `.env` and generates the seed password.

### Changed

- All code comments and docstrings are written in English.
- Access checks use permissions instead of hard-coded role lists.
- README now describes the project; technical guides moved to `docs/`.

### Removed

- Hard-coded password for seeded accounts: it now comes from `SEED_PASSWORD` in `.env` or is generated randomly on the first start.
- The standalone `smoke_test.py` script, replaced by the pytest suite.

### Fixed

- Row locking (`SELECT ... FOR UPDATE`) failing on queries with eager-loaded relations.
