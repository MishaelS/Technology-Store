"""Demo data on top of the seed, to see how the site looks when it's full. Run: ./run.sh demo

Adds products with pictures, news and events, facts, clients with orders in every status,
saved builds, repairs and stock receipts. Pictures of all products (the seed ones too)
come from resources/demo (scripts/make_demo_images.py draws them).

Runs once: if the demo products are already there, it does nothing. To start over: ./run.sh reset
Random choices use a fixed seed, so every run creates the same data.
"""

import random
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.demo_data import (
    ADDRESSES, BUILD_COMMENTS, BUILD_NAMES, DEMO_CLIENTS, DEMO_FACTS, DEMO_NEWS, DEMO_PRODUCTS, ORDER_COMMENTS, OUT_OF_STOCK,
    RECEIPT_COMMENTS, REPAIR_PROBLEM_CLIENTS, REPAIRS, SUPPLIERS,
)
from app.i18n import DEFAULT_LANGUAGE, t
from app.models import (
    BonusHistory, Build, BuildItem, Category, Fact, News, Order, OrderItem, Product, Repair, StockReceipt, User,
)
from app.security import hash_password
from app.seed import PRODUCTS

NOW = datetime.now(timezone.utc)


def slug(name: str) -> str:
    """File name of a product picture: "AMD Ryzen 5 5600" -> "amd-ryzen-5-5600"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def picture(name: str, view: int = 1) -> str:
    """Demo picture of a product; views 2 and 3 are the extra photos of the gallery."""
    return f"/resources/demo/products/{slug(name)}{'' if view == 1 else f'-{view}'}.svg"


def sold_out(db) -> None:
    """A few products are always out of stock, so the catalog shows how such a card looks."""
    for product in db.scalars(select(Product).where(Product.name.in_(OUT_OF_STOCK))):
        product.stock = 0


def fill_pictures(db) -> int:
    """Real photos where resources/photos has some, the placeholder picture for the rest (app/photos.py)."""
    from app.photos import apply_photos  # here, not on top: app.photos imports this module

    real, placeholder = apply_photos(db, commit=False)
    return real + placeholder


def description(category: str, name: str, specs: dict) -> str:
    """A short readable text from the specs, so product pages don't look empty."""
    s = specs
    match category:
        case "cpu":
            graphics = "есть встроенная графика" if s.get("igpu") else "нужна отдельная видеокарта"
            return (f"{name} — {s['cores']}-ядерный процессор для сокета {s['socket']}. "
                    f"Тепловыделение {s['tdp']} Вт, {graphics}. Оценка мощности в конфигураторе: {s['score']} из 100.")
        case "cooler":
            radiator = f", радиатор {s['radiator_mm']} мм" if s.get("radiator_mm") else ""
            return (f"Кулер для процессора ({s['type'].lower()}{radiator}): отводит до {s['tdp']} Вт тепла. "
                    f"Сокеты: {', '.join(s['sockets'])}.")
        case "motherboard":
            return (f"Материнская плата формата {s['form_factor']} под сокет {s['socket']}. "
                    f"{s['ram_slots']} слота под память {s['ram_type']}.")
        case "gpu":
            return (f"Видеокарта с {s['vram_gb']} ГБ видеопамяти, потребление {s['tdp']} Вт, длина {s['length_mm']} мм — "
                    f"проверьте, что она помещается в корпус. Оценка мощности: {s['score']} из 100.")
        case "ram":
            return f"Комплект памяти {s['ram_type']} на {s['size_gb']} ГБ ({s['sticks']} шт.)."
        case "storage":
            size = f"{s['size_gb'] // 1000} ТБ" if s["size_gb"] >= 1000 else f"{s['size_gb']} ГБ"
            return f"Накопитель {s['type']} объёмом {size}."
        case "psu":
            return f"Блок питания мощностью {s['wattage']} Вт."
        case "case":
            return (f"Корпус для плат {', '.join(s['form_factors'])}. "
                    f"Видеокарта длиной до {s['max_gpu_mm']} мм.")
    return name


def demo() -> None:
    rng = random.Random(2026)
    with SessionLocal() as db:
        if not db.scalar(select(User.id).limit(1)):
            print("demo: the database is empty — start the project first (./run.sh start)")
            return
        if db.scalar(select(Product.id).where(Product.name == DEMO_PRODUCTS[0][2])):
            # already there: only add what newer versions of the demo have (new products, extra photos)
            categories = {c.slug: c for c in db.scalars(select(Category))}
            names = set(db.scalars(select(Product.name)))
            for cat, brand, name, price, old_price, stock, specs in DEMO_PRODUCTS:
                if name not in names and cat in categories:
                    db.add(Product(category=categories[cat], brand=brand, name=name, price=price, old_price=old_price,
                                   stock=stock, specs=specs, image_url=picture(name), description=description(cat, name, specs)))
            db.flush()
            # details added to the lists later (threads, clocks, speeds…) reach the products already in the database;
            # values someone changed in the admin panel stay
            lists = {name: specs for _c, _b, name, *_rest, specs in PRODUCTS + DEMO_PRODUCTS}
            for product in db.scalars(select(Product).where(Product.name.in_(list(lists)))):
                extra = {k: v for k, v in lists[product.name].items() if k not in (product.specs or {})}
                if extra:
                    product.specs = {**(product.specs or {}), **extra}
            for product in db.scalars(select(Product).where(Product.description.endswith("в наличии в Technology-Store."))):
                product.description = description(product.category.slug, product.name, product.specs)
            changed = fill_pictures(db)
            sold_out(db)
            db.commit()
            print(f"demo: demo data is already there — pictures checked for {changed} products "
                  "(start over: ./run.sh reset, then ./run.sh demo)")
            return

        categories = {c.slug: c for c in db.scalars(select(Category))}
        staff = {u.role: u for u in db.scalars(select(User).where(User.role != "client"))}

        # ---------- products: new ones, pictures and descriptions for all ----------
        for cat, brand, name, price, old_price, stock, specs in DEMO_PRODUCTS:
            db.add(Product(category=categories[cat], brand=brand, name=name, price=price, old_price=old_price,
                           stock=stock, specs=specs, image_url=picture(name),
                           description=description(cat, name, specs),
                           created_at=NOW - timedelta(days=rng.randint(0, 40))))
        db.flush()
        products = list(db.scalars(select(Product)))
        fill_pictures(db)
        for product in products:
            if product.description.endswith("в наличии в Technology-Store."):
                product.description = description(product.category.slug, product.name, product.specs)
        by_category: dict[str, list[Product]] = {}
        for product in products:
            by_category.setdefault(product.category.slug, []).append(product)

        # ---------- news, events and facts ----------
        # the news feed is sorted by id (newest added first), so dates must grow with ids:
        # the seed news become the oldest ones, demo news are added from old to new
        for i, news in enumerate(db.scalars(select(News).order_by(News.id))):
            news.created_at = NOW - timedelta(days=70 - i * 2)
        for news_type, days, title, text, pic in sorted(DEMO_NEWS, key=lambda n: -n[1]):
            db.add(News(type=news_type, title=title, text=text, created_at=NOW - timedelta(days=days, hours=rng.randint(1, 20)),
                        image_url=f"/resources/demo/news/{news_type}-{pic}.svg" if pic else None))
        for text in DEMO_FACTS:
            db.add(Fact(text=text))

        # ---------- clients ----------
        password_hash = hash_password(settings.seed_password or secrets.token_urlsafe(12))
        clients = []
        for i, (name, email, phone) in enumerate(DEMO_CLIENTS):
            joined = NOW - timedelta(days=rng.randint(1, 90))
            user = User(email=email, name=name, phone=phone, role="client", password_hash=password_hash,
                        bonus_balance=settings.welcome_bonus, created_at=joined, is_blocked=i == len(DEMO_CLIENTS) - 1)
            db.add(user)
            db.flush()
            db.add(BonusHistory(user_id=user.id, amount=settings.welcome_bonus, created_at=joined,
                                reason=t("bonus.reason.welcome", lang=DEFAULT_LANGUAGE)))
            clients.append(user)

        # ---------- orders in every status ----------
        statuses = ["new"] * 6 + ["confirmed"] * 5 + ["assembling"] * 4 + ["shipped"] * 5 + ["done"] * 16 + ["cancelled"] * 4
        rng.shuffle(statuses)
        for status in statuses:
            user = rng.choice(clients)
            created = max(user.created_at, NOW - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23)))
            picked = rng.sample(products, rng.randint(1, 4))
            items = [OrderItem(product_id=p.id, product_name=p.name, quantity=rng.choice([1, 1, 1, 2]), price=p.price)
                     for p in picked]
            subtotal = sum(i.price * i.quantity for i in items)
            bonus_used = min(user.bonus_balance, subtotal * settings.max_bonus_percent // 100) if rng.random() < 0.3 else 0
            total = subtotal - bonus_used
            earned = total * settings.cashback_percent // 100 if status == "done" else 0
            order = Order(user_id=user.id, status=status, subtotal=subtotal, bonus_used=bonus_used, total=total,
                          bonus_earned=earned, address=rng.choice(ADDRESSES), phone=user.phone,
                          comment=rng.choice(ORDER_COMMENTS), created_at=created, items=items)
            db.add(order)
            db.flush()
            if bonus_used and status != "cancelled":
                user.bonus_balance -= bonus_used
                db.add(BonusHistory(user_id=user.id, amount=-bonus_used, order_id=order.id, created_at=created,
                                    reason=t("bonus.reason.order_payment", lang=DEFAULT_LANGUAGE, id=order.id)))
            if earned:
                user.bonus_balance += earned
                db.add(BonusHistory(user_id=user.id, amount=earned, order_id=order.id, created_at=created + timedelta(days=3),
                                    reason=t("bonus.reason.order_cashback", lang=DEFAULT_LANGUAGE, id=order.id)))

        # ---------- saved builds: compatible parts, half of them with an engineer's comment ----------
        for i in range(12):
            cpu = rng.choice(by_category["cpu"])
            cooler = rng.choice([c for c in by_category.get("cooler", []) if cpu.specs["socket"] in c.specs["sockets"]
                                 and c.specs["tdp"] >= cpu.specs["tdp"]] or [None])
            boards = [b for b in by_category["motherboard"] if b.specs["socket"] == cpu.specs["socket"]]
            if not boards:
                continue
            board = rng.choice(boards)
            ram = rng.choice([r for r in by_category["ram"] if r.specs["ram_type"] == board.specs["ram_type"]])
            gpu = rng.choice(by_category["gpu"])
            case = rng.choice([c for c in by_category["case"] if board.specs["form_factor"] in c.specs["form_factors"]])
            psu = rng.choice(by_category["psu"])
            storage = rng.choice(by_category["storage"])
            user = rng.choice(clients)
            commented = i % 2 == 0
            db.add(Build(user_id=user.id, name=rng.choice(BUILD_NAMES), created_at=NOW - timedelta(days=rng.randint(0, 30)),
                         engineer_comment=rng.choice(BUILD_COMMENTS) if commented else None,
                         engineer_id=staff["employee"].id if commented and "employee" in staff else None,
                         items=[BuildItem(product_id=p.id) for p in (cpu, cooler, board, ram, gpu, case, psu, storage) if p]))

        # ---------- repairs in every status ----------
        repair_statuses = ["accepted", "accepted", "diagnostics", "diagnostics", "repairing", "repairing",
                           "ready", "ready", "issued", "issued", "issued", "cancelled"]
        engineer = staff.get("engineer")
        for (device, problem, comment), status in zip(REPAIRS, repair_statuses):
            if rng.random() < 0.5:
                client = rng.choice(clients)
                who = {"client_id": client.id, "client_name": client.name, "client_phone": client.phone}
            else:
                name, phone = rng.choice(REPAIR_PROBLEM_CLIENTS)
                who = {"client_id": None, "client_name": name, "client_phone": phone}
            priced = status in ("repairing", "ready", "issued") or (status == "diagnostics" and comment)
            db.add(Repair(**who, device=device, problem=problem, status=status,
                          price=rng.choice([1500, 2500, 3500, 4900, 7900, 12900]) if priced else None,
                          engineer_comment=comment if status != "accepted" else "",
                          engineer_id=engineer.id if engineer and status != "accepted" else None,
                          created_at=NOW - timedelta(days=rng.randint(0, 25), hours=rng.randint(0, 23))))

        # ---------- stock receipts: the stock of those products grows ----------
        receiver = staff.get("employee") or staff.get("manager")
        for _ in range(25):
            product = rng.choice(products)
            quantity = rng.choice([2, 3, 5, 5, 10, 10, 20])
            product.stock += quantity
            db.add(StockReceipt(product_id=product.id, quantity=quantity, supplier=rng.choice(SUPPLIERS),
                                comment=rng.choice(RECEIPT_COMMENTS), received_by_id=receiver.id if receiver else None,
                                created_at=NOW - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 23))))

        sold_out(db)
        db.commit()
        print(f"demo: added {len(DEMO_PRODUCTS)} products, {len(DEMO_NEWS)} news, {len(DEMO_FACTS)} facts, "
              f"{len(clients)} clients, {len(statuses)} orders, 12 builds, {len(REPAIRS)} repairs, 25 stock receipts")
        print(f"demo: clients log in with the same password as the seed accounts (./run.sh password), e.g. {clients[0].email}")


if __name__ == "__main__":
    demo()
