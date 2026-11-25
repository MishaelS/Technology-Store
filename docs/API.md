# Работа с API

Фронтенд и бэкенд — отдельные части, и общаются они только через API. Бэкенд отдаёт данные и решает, кому что можно. Фронтенд показывает их и прячет то, на что у пользователя нет прав.

Живая документация со всеми полями и кнопкой «попробовать» — http://localhost:8000/docs.

## Основное

- Все адреса начинаются с `/api`, данные в JSON, имена полей в стиле `snake_case`.
- Ошибка всегда приходит так: `{"detail": "текст ошибки"}`. Текст уже переведён на язык запроса.
- При ошибке в полях (`422`) добавляется список `fields`, чтобы подсветить их в форме:
  `{"detail": "Проверьте поля: email, phone", "fields": [{"field": "email", "message": "Некорректный email"}, ...]}`.
- При сбое сервера (`500`) приходит только общий текст, без внутренних подробностей.
- Пробелы в начале и в конце текстовых полей обрезаются, поле только из пробелов считается пустым.
- Телефон: цифры, `+`, пробелы, скобки и дефисы, от 7 до 15 цифр. Ссылка на картинку: `http://`, `https://` или путь от корня сайта (`/images/...`).
- Коды ответа: `400` — неверный запрос, `401` — нужно войти, `403` — нет прав или аккаунт заблокирован, `404` — не найдено, `409` — уже существует, `422` — неверные поля.

## Вход и токен

1. `POST /api/auth/login` с `{email, password}` или `POST /api/auth/register` с `{email, password, name}`.
2. В ответе приходят `token` и `user`.
3. Дальше токен передаётся в каждом запросе заголовком `Authorization: Bearer <token>`.
4. Токен живёт 24 часа. После этого придёт `401`, и нужно войти заново.

В `/docs` токен вставляется через кнопку **Authorize**.

## Роли и права

Токен говорит только «кто это». Что этому человеку можно, бэкенд решает по его роли **при каждом запросе**. Поэтому новая роль или блокировка действуют сразу, без повторного входа.

Права перечислены в одном месте — [`backend/app/permissions.py`](../backend/app/permissions.py):

| Право | Что даёт | client | engineer | manager | admin |
|---|---|:-:|:-:|:-:|:-:|
| `admin.access` | открыть админку | | ✓ | ✓ | ✓ |
| `stats.view` | статистика магазина | | | ✓ | ✓ |
| `orders.manage` | все заказы, смена статуса | | | ✓ | ✓ |
| `content.manage` | новости, акции, факты | | | ✓ | ✓ |
| `products.manage` | товары: создание, редактирование, скрытие | | ✓ | ✓ | ✓ |
| `builds.review` | сборки клиентов и комментарии | | ✓ | | ✓ |
| `users.manage` | пользователи, роли, блокировка, бонусы вручную | | | | ✓ |

Свою корзину, заказы, сборки и профиль может вести любой вошедший пользователь, отдельное право для этого не нужно.

**Как фронтенду этим пользоваться.** `GET /api/auth/me` (и ответ на вход) содержит `permissions`, например `["admin.access", "orders.manage", ...]`. Фронтенд показывает пункт меню, раздел или кнопку, только если нужное право есть в списке. Даже если кнопку как-то вызвать, бэкенд всё равно ответит `403`: скрытие на фронтенде — для удобства, защита — на бэкенде.

## Язык

Язык ответа выбирается так: параметр `?lang=en` → заголовок `Accept-Language` → по умолчанию `ru`. Подробнее — [TRANSLATIONS.md](TRANSLATIONS.md).

## Списки

- **Бесконечная прокрутка** (каталог, новости): первый запрос без `cursor`, следующий — с `cursor` = `next_cursor` из прошлого ответа. `next_cursor: null` — данные закончились. Ответ: `{items, next_cursor, total}`.
- **Страницы** (таблицы админки): `?page=1&page_size=20`. Ответ: `{items, total, page, pages}`.

## Все методы

Без входа:

| Метод | Что делает |
|---|---|
| `POST /api/auth/register`, `POST /api/auth/login` | регистрация (+500 бонусов) и вход |
| `GET /api/home` | всё для главной: акции, скидки, новости, хиты, факт |
| `GET /api/categories` | категории |
| `GET /api/products` | товары порциями. Фильтры: `category`, `search`, `brand`, `min_price`, `max_price`, `in_stock`, `discount`, `socket`, `ram_type`; сортировка `sort` = `new` / `price_asc` / `price_desc` / `name` |
| `GET /api/products/brands`, `GET /api/products/{id}` | бренды для фильтра, карточка товара |
| `GET /api/news`, `GET /api/news/{id}`, `GET /api/facts/random` | новости (`type` = `news` / `promo` / `game`) и факты |
| `POST /api/builder/check` | проверка сборки `{product_ids}`: совместимость, мощность, уровень ПК |
| `GET /api/i18n`, `GET /api/i18n/{lang}` | языки и все тексты интерфейса |

С токеном (любая роль):

| Метод | Что делает |
|---|---|
| `GET /api/auth/me`, `PATCH /api/auth/me` | профиль и права; изменить имя и телефон |
| `GET /api/cart`, `POST /api/cart`, `PATCH /api/cart/{product_id}`, `DELETE /api/cart/{product_id}`, `DELETE /api/cart` | корзина |
| `POST /api/cart/add-many` | «Всё в корзину» из конфигуратора |
| `POST /api/orders` | оформить заказ `{address, phone, comment, bonus_to_use}` |
| `GET /api/orders/my`, `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel` | мои заказы; отменить можно, пока статус `new` |
| `GET /api/bonus` | баланс и история бонусов |
| `GET/POST /api/builds`, `GET/DELETE /api/builds/{id}` | сохранённые сборки |

Админка (нужно право из таблицы выше):

| Метод | Право |
|---|---|
| `GET /api/admin/stats` | `stats.view` |
| `GET /api/admin/orders`, `PATCH /api/admin/orders/{id}/status` | `orders.manage` |
| `GET/POST /api/admin/products`, `GET/PATCH/DELETE /api/admin/products/{id}` | `products.manage` |
| `GET /api/admin/products/spec-schema` — поля характеристик каждой категории с подсказками (для редактора товара) | `products.manage` |
| `GET /api/admin/builds`, `PATCH /api/admin/builds/{id}/comment` | `builds.review` |
| `POST /api/admin/news`, `PATCH/DELETE /api/admin/news/{id}`, `GET/POST /api/admin/facts`, `DELETE /api/admin/facts/{id}` | `content.manage` |
| `GET /api/admin/roles`, `GET /api/admin/users`, `PATCH /api/admin/users/{id}`, `POST /api/admin/users/{id}/bonus` | `users.manage` |

## Правила, которые стоит знать

- **Бонусы:** 1 бонус = 1 ₽. Оплатить бонусами можно не больше 30% заказа и не больше баланса. В корзине поле `max_bonus` уже показывает этот предел. При статусе `done` начисляется 5% от оплаченной суммы. При отмене товар возвращается на склад, а бонусы на счёт.
- **Статусы заказа** идут только вперёд: `new → confirmed → assembling → shipped → done`. Отменить (`cancelled`) можно до отправки.
- **Удаление товара** скрывает его из каталога, но он остаётся в старых заказах и сборках.
- **Цена в заказе** фиксируется в момент покупки.
