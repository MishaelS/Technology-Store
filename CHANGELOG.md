# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Server mode: `./run.sh deploy` with `docker-compose.prod.yml` — only Caddy is open outside (80/443) and gives HTTPS
  by itself for a domain (`SITE_ADDRESS`); the database, the API and Adminer are closed; the API runs without reload;
  everything restarts by itself; passwords and `JWT_SECRET` are generated. Every `./run.sh` command keeps the mode.
- `docs/DEPLOY.md`: step by step from renting a VPS to updating the site.
- CPU coolers: a new category (`cooler`) with 8 products (tower, low profile, liquid), the rule "the cooler fits
  the CPU socket and takes away its heat" in the builder check, and the cooler is a required part of a complete build.
  An existing database gets the category on the next start (`app.seed`), `./run.sh demo` adds the demo coolers.
- The PC builder is a 3D case now: an open case in the middle (three.js), the sections of parts under it in the order
  of an assembly (motherboard → CPU → cooler → RAM → PSU → GPU → drives → case) and a strip of parts of the open section.
  A chosen part flies into its place inside the case; parts that don't fit glow red; a complete compatible build
  powers on (fans spin, RGB lights up). The case turns with the mouse or a finger.
- 3D models of the case and the parts are built in Blender by `scripts/make_builder_models.py`
  (`./run.sh models` → `resources/models/builder.glb`); three.js r187 is in `frontend/vendor/three`.

- The fields the 3D case shows a part by (board form factor, case boards, cooler type, drive type) take only known
  values; the product editor shows them as a choice, a liquid cooler needs its radiator size. A new product added
  in the admin panel goes into the case by itself.

- More specs of the products (CPU threads and clocks, GPU chip and memory, RAM timings, drive speeds, PSU certificate,
  board chipset and Wi-Fi, cooler height and noise) and the size, front panel and colour of cases; the colour of
  GPUs, RAM and coolers. `./run.sh demo` adds them to an existing database without touching edited values.
- Builder checks: a tower cooler must not be higher than the case allows, a liquid cooler's radiator must fit the case.
- Parts out of stock in the builder list are wrapped in the barrier tape, like the catalog cards.
- More detailed 3D models and more variants: GPU styles by brand, single and dual tower coolers, flat and round
  low coolers, two pump styles, three RAM styles, PSU lengths, M.2 with a heatsink, sleeved power cables;
  the case follows its size, front panel (mesh, glass, solid, wood) and colour, parts take their colour;
  a part that doesn't fit gets a red outline. No part of a compatible build intersects another.
- The first slide of the home page shows an assembled 3D PC instead of a picture: it swings around its open side
  (or follows the mouse over the slide) and keeps changing its parts, one compatible part every few seconds.
- The model file is Draco-compressed (1.8 MB instead of 4.5 MB); the decoder is in `frontend/vendor/three`.

### Changed

- The builder sections: no progress line and no list of steps any more, the summary stays on the right.

### Fixed

- Backups larger than 6 MB could not be uploaded through the site (the proxy limit was 6 MB for the whole API).

## [0.4.0] - 2026-11-26

Real product photos with a fast image loader, barrier tape for products out of stock, softer home page slides
and documents about the technologies and the photos.

### Added

- `docs/TECH.md`: the technologies of the project, their versions and what each one is for.
- `docs/PHOTOS.md`: what product photos are needed (format, size, background, angles per category) and how to add them.
- Real product photos: `scripts/prepare_product_photos.py` makes web versions (1600x1200 WebP, white background,
  product whole and centered) of `resources/photos/products`; `./run.sh photos` (`app/photos.py`) gives them to
  the products, the rest get the placeholder; photos uploaded by hand are kept. The demo uses them too.
- A picture that fails to load is replaced with a grey placeholder (`resources/demo/placeholder.svg`).
- The "build your PC" slide shows real parts lying together on its circle instead of the wrench icon
  (`scripts/make_hero_collage.py`: backgrounds cut out, soft shadows, transparent WebP); the icon stays
  while it loads or when there is no such file.
- Our own image loader (`images.js`): small copies in cards and lists, the big photo only on the product page;
  loading starts 800 px before the screen, at most 6 at once, the nearest first; pictures are decoded before
  they fade in, a shimmer shows meanwhile; loaded pictures show at once next time; the photos of a card and
  the big photo of its page are preloaded while the mouse rests on the card.
- Small copies: 480x360 `-sm.webp` next to every prepared photo and every upload (avatars 256x256); Pillow in the backend.
- nginx compresses text (CSS 88 KB -> 20 KB, catalog answer 10.5 KB -> 1.8 KB) and lets the browser keep pictures
  (a day for the repository's pictures, a year for uploads with their random names).

### Changed

- Products out of stock: yellow barrier tape across the picture ("out of stock" band and a striped one crossing it)
  instead of the black badge, on cards and on the product page; the demo keeps 6 products sold out to see it.
- Cards pop in faster (shorter animation and delays), the next chunk of a list is asked for 1200 px before its end.
- Softer home page slides: the circles are gradients with a light corner and a soft shadow; promotions are violet
  and peach instead of red, the small circle of other slides is mint.

### Fixed

- A picture of a slide that went over its circle showed at the edge of the next slide.

## [0.3.0] - 2026-11-25

Dark theme, a new home page and a layout for phones on every page.

### Added

- Dark theme: a second set of color variables, a sun/moon switch in the header; the new theme opens as a circle
  from the switch. The choice is remembered, until then the site follows the system theme; set before the first
  paint, so a dark page never flashes white. The hex background and pictures follow the theme.
- `navigation/theme-dark` and `navigation/theme-light` icons.

### Changed

- Phones: the catalog filters always start collapsed; rows of tabs (account) and admin sections scroll sideways
  with the current one in view; admin tables become cards with column titles over the values;
  the slider bars fit the narrowest screens.
- New home page: a wide first screen (a big colored title, a product photo on two colored circles, bar indicators),
  catalog sections as tiles, news in three columns under a thick line, a band of big numbers that count up,
  an "about the store" block over a dark band, a question band; the categories sidebar is gone from the home page.
- Dark footer with columns of links: the catalog sections, for buyers, service.

### Fixed

- The wrench icon (`navigation/builder`): its jaw was drawn crooked, visible at large sizes.

## [0.2.0] - 2026-11-25

New design of the whole site, admin panel with infinite lists, picture uploads, product galleries,
avatars, backups, demo data and a phone layout.

### Added

- Backups (admin panel, permission `system.backup`, only for the admin): the whole database
  and the uploaded pictures in one .zip; make, download, upload, restore (only the same database version,
  in one transaction) and delete. Auto backup on a schedule with rotation, off by default (a checkbox).
  Files in `backups/`.
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

[Unreleased]: https://github.com/MishaelS/Technology-Store/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/MishaelS/Technology-Store/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MishaelS/Technology-Store/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MishaelS/Technology-Store/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MishaelS/Technology-Store/releases/tag/v0.1.0
