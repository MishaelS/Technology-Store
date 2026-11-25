# Иконки

Набор иконок сайта. Посмотреть все сразу: http://localhost:5173/resources/icons/preview.html (после `./run.sh start`).

## Правила

- Размер 24×24 (`viewBox="0 0 24 24"`), контурные линии толщиной 2, скруглённые концы.
- Цвет не задан жёстко: `stroke="currentColor"`. Если вставить SVG прямо в HTML, иконка берёт цвет текста. Через `<img>` она будет чёрной.
- Одна иконка — один файл, имя файла на английском через дефис.
- Новая иконка: нарисовать в том же стиле, положить в нужную папку и добавить строку в таблицу ниже.
- `logo.svg` — логотип и иконка вкладки браузера (цветной, 32×32).

## Как подключить во фронтенде

```js
import { icon } from "./ui.js";
icon("navigation/cart");           // <img src="/resources/icons/navigation/cart.svg">
icon("categories/gpu", "Видеокарты"); // с подписью для экранных читалок
```

## Список

### Навигация и вкладки (`navigation/`)

| Файл | Где используется |
|---|---|
| `navigation/home.svg` | Главная |
| `navigation/catalog.svg` | Каталог |
| `navigation/builder.svg` | Конфигуратор ПК |
| `navigation/news.svg` | Новости |
| `navigation/cart.svg` | Корзина |
| `navigation/account.svg` | Личный кабинет |
| `navigation/admin.svg` | Админка |
| `navigation/login.svg` | Войти |
| `navigation/logout.svg` | Выйти |
| `navigation/register.svg` | Регистрация |
| `navigation/language.svg` | Переключатель языка |
| `navigation/menu.svg` | Меню (на телефоне) |
| `navigation/arrow-up.svg` | Наверх |
| `navigation/arrow-left.svg` | Назад |
| `navigation/arrow-right.svg` | Вперёд, подробнее |
| `navigation/chevron-down.svg` | Раскрыть список |
| `navigation/chevron-right.svg` | Перейти, следующая страница |
| `navigation/chevron-left.svg` | Предыдущая страница |
| `navigation/external.svg` | Открыть товар |

### Кнопки (`actions/`)

| Файл | Где используется |
|---|---|
| `actions/search.svg` | Поиск |
| `actions/filter.svg` | Фильтры |
| `actions/sort.svg` | Сортировка |
| `actions/reset.svg` | Сбросить фильтры, обновить |
| `actions/plus.svg` | Добавить, увеличить количество |
| `actions/minus.svg` | Уменьшить количество |
| `actions/add-to-cart.svg` | В корзину |
| `actions/edit.svg` | Изменить |
| `actions/delete.svg` | Удалить, убрать |
| `actions/save.svg` | Сохранить |
| `actions/close.svg` | Закрыть, отмена |
| `actions/check.svg` | Готово, подтвердить |
| `actions/show.svg` | Показать, вернуть в каталог |
| `actions/hide.svg` | Скрыть из каталога |
| `actions/block.svg` | Заблокировать пользователя |
| `actions/unlock.svg` | Разблокировать |

### Состояния и проверки (`feedback/`)

| Файл | Где используется |
|---|---|
| `feedback/success.svg` | Успех, всё совместимо |
| `feedback/error.svg` | Ошибка, несовместимо |
| `feedback/warning.svg` | Предупреждение |
| `feedback/info.svg` | Подсказка |
| `feedback/skip.svg` | Проверка ещё не выполнена |
| `feedback/loading.svg` | Загрузка |

### Категории товаров (`categories/`)

| Файл | Где используется |
|---|---|
| `categories/cpu.svg` | Процессоры |
| `categories/motherboard.svg` | Материнские платы |
| `categories/gpu.svg` | Видеокарты |
| `categories/ram.svg` | Оперативная память |
| `categories/storage.svg` | Накопители |
| `categories/psu.svg` | Блоки питания |
| `categories/case.svg` | Корпуса |

### Заказы (`orders/`)

| Файл | Где используется |
|---|---|
| `orders/order.svg` | Заказ |
| `orders/status-new.svg` | Статус «Новый» |
| `orders/status-confirmed.svg` | Статус «Подтверждён» |
| `orders/status-assembling.svg` | Статус «Собирается» |
| `orders/status-shipped.svg` | Статус «Отправлен» |
| `orders/status-done.svg` | Статус «Выполнен» |
| `orders/status-cancelled.svg` | Статус «Отменён» |
| `orders/address.svg` | Адрес доставки |
| `orders/payment.svg` | Оплата при получении |

### Магазин и бонусы (`shop/`)

| Файл | Где используется |
|---|---|
| `shop/bonus.svg` | Бонусы |
| `shop/discount.svg` | Скидка |
| `shop/percent.svg` | Процент скидки |
| `shop/hit.svg` | Хит продаж |
| `shop/in-stock.svg` | В наличии |
| `shop/out-of-stock.svg` | Нет в наличии |
| `shop/price.svg` | Цена, сумма |
| `shop/power.svg` | Мощность, потребление |

### Контент (`content/`)

| Файл | Где используется |
|---|---|
| `content/promo.svg` | Акции |
| `content/game.svg` | Игровые новости |
| `content/fact.svg` | Интересный факт |
| `content/comment.svg` | Комментарий инженера |
| `content/calendar.svg` | Дата |

### Личный кабинет (`account/`)

| Файл | Где используется |
|---|---|
| `account/profile.svg` | Профиль |
| `account/email.svg` | Email |
| `account/phone.svg` | Телефон |
| `account/password.svg` | Пароль |
| `account/builds.svg` | Мои сборки |

### Админка (`admin/`)

| Файл | Где используется |
|---|---|
| `admin/dashboard.svg` | Дашборд, статистика |
| `admin/users.svg` | Пользователи |
| `admin/products.svg` | Товары |
| `admin/client-builds.svg` | Сборки клиентов |
| `admin/content.svg` | Новости и факты |
| `admin/roles.svg` | Роли и права |
| `admin/low-stock.svg` | Заканчивается на складе |
| `admin/repairs.svg` | Ремонт техники |
| `admin/receipts.svg` | Приёмка товара |
| `admin/system.svg` | Техподдержка: сервер и база |

### Роли (`roles/`)

| Файл | Где используется |
|---|---|
| `roles/role-client.svg` | Клиент |
| `roles/role-manager.svg` | Менеджер |
| `roles/role-employee.svg` | Сотрудник (продавец-консультант) |
| `roles/role-engineer.svg` | Инженер (ремонт) |
| `roles/role-senior_engineer.svg` | Старший инженер (сервер, база, ошибки) |
| `roles/role-admin.svg` | Администратор |

### Уровни ПК (`tiers/`)

| Файл | Где используется |
|---|---|
| `tiers/tier-office.svg` | Офисный ПК |
| `tiers/tier-gaming.svg` | Игровой ПК |
| `tiers/tier-powerful.svg` | Мощный ПК |
| `tiers/tier-top.svg` | Топовый ПК |
