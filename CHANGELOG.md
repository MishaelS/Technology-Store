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
- `./run.sh ide` and `pyrightconfig.json`: local Python libraries for VS Code / Pylance, no more unresolved imports;
  `./run.sh typecheck` runs the same type check.
- Edge case tests (`test_edge_cases.py`): whitespace-only fields, bad phones, wrong spec types, unsafe links, error format.
- Simple frontend without design at http://localhost:5173 (nginx in Docker): home, catalog with infinite scroll
  and scroll restore, product, news, PC builder, login and sign-up, cart and checkout, personal account,
  admin panel with sections shown by permissions, ru/en language switch.
- Locale check also verifies keys used by the frontend.
- Icon set in `resources/icons`: 90 outline SVG icons in 11 groups (navigation, buttons, states, categories,
  orders, shop, content, account, admin, roles, PC tiers), a logo and favicon, a preview page and a list.
- Header shows icons; `icon()` helper in the frontend; nginx serves the `resources` folder.
- Product editor page (`#/admin/products/new`, `#/admin/products/:id`): a form with typed spec fields for each
  category, suggestions from existing products, live preview, discount hint, "save and add another",
  copy of a product and an edit link on the product page.
- New roles: employee (sales, product cards, deliveries, orders, builds advice) and senior engineer
  (server, database, errors); the engineer now handles repairs. Seed accounts for them are added
  to existing databases automatically.
- Repairs: accept a device, statuses from accepted to issued, price and engineer comment;
  clients see their repairs in the account.
- Stock receipts: an employee records a delivery, the stock grows, the log keeps who and when.
- Tech support page: server and database state, migration, counts and recent server errors (500 are logged).
- Icons for the new roles and admin sections.
- `GET /api/admin/products/spec-schema` (spec fields per category) and `GET /api/admin/products/{id}` (also hidden ones).
- `run.sh`: one script to set up, start, stop, test and maintain the project (`./run.sh help`). It checks Docker, creates `.env` and generates the seed password.

### Changed

- All code comments and docstrings are written in English.
- Access checks use permissions instead of hard-coded role lists.
- Managers can create and edit products (`products.manage`).
- Engineers no longer manage products and client builds: employees do it now.
- The JSON specs form in the admin products list is replaced by the product editor.
- README now describes the project; technical guides moved to `docs/`.

### Removed

- Hard-coded password for seeded accounts: it now comes from `SEED_PASSWORD` in `.env` or is generated randomly on the first start.
- The standalone `smoke_test.py` script, replaced by the pytest suite.

### Fixed

- Type errors reported by Pylance: text field types in schemas, filter lists, stats counts, pagination total.
- Row locking (`SELECT ... FOR UPDATE`) failing on queries with eager-loaded relations.
- Fields with only spaces (name, address, phone, build name, news title) were accepted as filled.
- Phone numbers were not validated.
- Product specs with wrong types (e.g. `"650"` instead of `650`) were saved and crashed the PC builder with error 500.
- Image links accepted any value, including `javascript:` and `data:` links.
- Validation errors (422) returned a list instead of a text `detail`; unexpected errors (500) returned plain text.
- Login answered faster for unknown emails, which allowed guessing registered emails by response time.
- Two parallel registrations with the same email could cause error 500 instead of 409.
- A client cancel and a manager cancel at the same time could refund bonuses twice.
- Admin stats skipped order statuses that had no orders.
