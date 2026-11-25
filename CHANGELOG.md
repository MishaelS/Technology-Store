# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- More photos of a product (`images`, up to 10 after the main `image_url`): the card flips through them
  while the mouse rests on it, the product page shows them with thumbnails; resting the mouse on the big photo
  for a moment opens a lens that follows the mouse. In the editor several photos can be dropped at once.
  The demo gives every product two more views (close-up and the box).
- Own photo (avatar): `POST/DELETE /api/auth/me/avatar`, `avatar_url` in the user; set in the account by choosing
  a file or dropping it onto the avatar. Without a photo the avatar shows the initials on a color.
- Skeleton placeholders in the shape of cards while the catalog, the news and the first page load.
- Promo slider on the home page: the "build a PC" slide and the promotions, changes by itself
  with a progress bar on the active dot, pauses under the mouse, arrows and swipe on phones.
- `actions/copy` icon.
- Own up/down arrows for every number field (`number-field.js`): holding repeats the step,
  min/max are respected, `change` fires once when the button is released.
- `./run.sh demo` (`app/demo.py`): demo data on top of the seed — 61 more products, 24 news and events,
  facts, 12 clients with orders in every status, saved builds, repairs and stock receipts.
- Demo pictures for every product and news (`resources/demo`, drawn by `scripts/make_demo_images.py`).
- Picture upload: `POST /api/admin/uploads` (the type is checked by the file's bytes, no SVG, up to 5 MB),
  files in `uploads/` served by nginx at `/uploads/`; in the product editor and the news form a picture
  can be dropped onto the field, chosen from a file or pasted.
- "Nothing here yet" block with a button for an empty cart, orders, builds and repairs.
- `content/image` icon.
- Background of hex bytes like a memory dump (`10 AA 2A D2 ...`, `hex-background.js`): a wave runs over them
  from the click point on every page change, the bytes light up and get new values (only a wave changes them).
  At rest Perlin noise with a fixed seed sets the size and brightness of the bytes and slowly drifts
  to the bottom right corner; the background is slightly blurred;
  redrawn 15 times a second at rest, every frame during a wave, nothing in a hidden tab.
- A change of filters (catalog, news) opens the new page with the same wave as a change of section;
  a reload of the same page doesn't.

### Changed

- Cart items are small cards (photo, name, quantity, sum, remove) that fit a phone instead of a wide table.
- Builder steps on a phone: seven circles in one line with the progress line; the chosen part shows its photo.
- Faster background: drawn at a low resolution instead of a full-screen CSS blur, fewer redraws at rest
  (10/s, 6/s on phones) and none while the page scrolls; the phone section bar has a solid background.
- Phone header: one line (logo, language, cart icon with a badge, avatar) and the search under it;
  the sections moved to a bar at the bottom of the screen; the narrowest phones show the logo alone.
- The site calls the API on its own address (`/api/...`), nginx passes it to the backend: the site works
  through a tunnel or a forwarded port 5173 alone.
- The header shows the user's avatar instead of the name and the logout button; logging out is in the account.
- Only the admin (`users.manage`) sees roles: the account and the avatar tooltip no longer show the user's own role.
- Admin panel lists (orders, products, client builds, users, repairs, stock receipts, news) load more rows
  while scrolling instead of page buttons; search works while typing, filters stay in the address,
  a row is redrawn in place after a change.
- New look of the admin panel: search bar with filters and a counter, tables with spacing and status labels,
  icon buttons for row actions, dashboard tiles, collapsible create forms.
- Form fields show their name inside (floating label) instead of a line of text above.
- Product editor: form split into blocks, fields side by side, suggestions as chips under the field,
  checkboxes next to their text, a smaller picture preview, a quieter "save and create another" button.
- Promo slider: arrows and dots in one bar under the slide; promotion pictures shown whole.
- Slightly darker page background, so the white cards and panels stand out.
- The bonus limit in checkout is a hint under the field instead of a long label.

### Removed

- Page buttons of the admin tables and their texts (`common.prev`, `common.next`, `admin.page`).

### Fixed

- The footer stays at the bottom of the screen on short pages.
- Pale icons on the admin dashboard tiles.
- The promo slider stopped changing slides after a click on a dot or an arrow, and could stall on the last one.
- The product page cut its picture (square frame for a 4:3 picture).
- Parts of the account tabs (bonuses, orders, builds) had no space between them.

## [0.1.0] - 2026-11-25

First version: the store backend, the admin panel and the frontend with the new design.

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
- Custom dropdown in the site's style for every `<select>` (`frontend/src/dropdown.js`): arrow icon, open animation, keyboard support.
- Catalog filters in a sticky panel on the left: categories, sort, price, brand and availability sections with icons;
  the panel and each section can be collapsed, the choice is remembered in the browser.
- Home page categories in the same left panel.
- News page with tiles (colored badge per type) and a left panel to pick the type; the home page shows news tiles at the bottom with the fact of the day.
- Thin loading bar at the top while a slow page loads.
- "Show all" links next to section titles are pills with an arrow that moves on hover; text links get an underline that grows on hover.
- Product cards: lift on hover, discount and "out of stock" badges on the picture, category icon, stock with a colored dot (orange when 3 or less), the whole card opens the product, the cart button shows a check after adding.
- Page transition between sections (View Transitions API): the old page fades away, the new one opens as a circle wave from the click point. Product cards and news tiles pop in from the center one by one in random order. Both are off with reduced motion.
- PC builder redesign: a progress line of 7 steps, a card per step with a hint, parts as tiles with key specs and a "fits / doesn't fit" hint, the next step opens by itself; summary with a score ring, CPU/GPU bars and PSU load.
- Effects: a click wave inside buttons, home page blocks slide in while scrolling, the cart counter jumps when it grows, builder numbers count to their new values; the "to top" button fades in.

### Changed

- All code comments and docstrings are written in English.
- Access checks use permissions instead of hard-coded role lists.
- Managers can create and edit products (`products.manage`).
- Engineers no longer manage products and client builds: employees do it now.
- The JSON specs form in the admin products list is replaced by the product editor.
- README now describes the project; technical guides moved to `docs/`.
- Header: menu and account actions on the right, search on its own row under the logo.
- Pages no longer blink on navigation: the old page stays until the new one is ready, the header is redrawn only when the user, cart or language changes.
- Smoother scrolling and hover: scroll checks run once per frame, card shadows fade on a pseudo-element instead of animating box-shadow, the page transition no longer blurs the whole page; a page still appears if the transition can't start.

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

[Unreleased]: https://github.com/MishaelS/Technology-Store/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MishaelS/Technology-Store/releases/tag/v0.1.0
