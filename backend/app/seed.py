"""Test data. Run: python -m app.seed (runs only if the database is empty).

Creates one account per role (emails in USERS). All of them get the same password:
SEED_PASSWORD from .env, or a random one that is printed to the log once.
Passwords are never stored in the repository.
"""

import secrets

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.i18n import DEFAULT_LANGUAGE, t
from app.models import BonusHistory, Category, Fact, News, Product, User
from app.security import hash_password

USERS = [
    ("admin@store.dev", "Администратор", "admin"),
    ("manager@store.dev", "Мария Менеджер", "manager"),
    ("engineer@store.dev", "Иван Инженер", "engineer"),
    ("client@store.dev", "Пётр Покупатель", "client"),
]

CATEGORIES = [
    ("cpu", "Процессоры"),
    ("motherboard", "Материнские платы"),
    ("gpu", "Видеокарты"),
    ("ram", "Оперативная память"),
    ("storage", "Накопители"),
    ("psu", "Блоки питания"),
    ("case", "Корпуса"),
]

# (category, brand, name, price, old price, stock, specs)
PRODUCTS = [
    # CPUs
    ("cpu", "Intel", "Intel Core i3-12100F", 7990, None, 15,
     {"socket": "LGA1700", "cores": 4, "tdp": 58, "igpu": False, "score": 30}),
    ("cpu", "Intel", "Intel Core i5-12400F", 11490, 12990, 20,
     {"socket": "LGA1700", "cores": 6, "tdp": 65, "igpu": False, "score": 45}),
    ("cpu", "Intel", "Intel Core i5-13600K", 27990, None, 8,
     {"socket": "LGA1700", "cores": 14, "tdp": 125, "igpu": True, "score": 68}),
    ("cpu", "Intel", "Intel Core i7-14700K", 39990, 42990, 5,
     {"socket": "LGA1700", "cores": 20, "tdp": 125, "igpu": True, "score": 82}),
    ("cpu", "AMD", "AMD Ryzen 5 5600", 9990, None, 25,
     {"socket": "AM4", "cores": 6, "tdp": 65, "igpu": False, "score": 42}),
    ("cpu", "AMD", "AMD Ryzen 7 5700X3D", 21990, 24990, 10,
     {"socket": "AM4", "cores": 8, "tdp": 105, "igpu": False, "score": 62}),
    ("cpu", "AMD", "AMD Ryzen 5 7600", 17490, None, 12,
     {"socket": "AM5", "cores": 6, "tdp": 65, "igpu": True, "score": 55}),
    ("cpu", "AMD", "AMD Ryzen 7 7800X3D", 38990, None, 6,
     {"socket": "AM5", "cores": 8, "tdp": 120, "igpu": True, "score": 85}),
    ("cpu", "AMD", "AMD Ryzen 9 7950X", 54990, 59990, 3,
     {"socket": "AM5", "cores": 16, "tdp": 170, "igpu": True, "score": 95}),
    # Motherboards
    ("motherboard", "MSI", "MSI PRO H610M-E DDR4", 7490, None, 14,
     {"socket": "LGA1700", "ram_type": "DDR4", "ram_slots": 2, "form_factor": "mATX"}),
    ("motherboard", "ASUS", "ASUS PRIME B760-PLUS D4", 13990, None, 9,
     {"socket": "LGA1700", "ram_type": "DDR4", "ram_slots": 4, "form_factor": "ATX"}),
    ("motherboard", "Gigabyte", "Gigabyte Z790 AORUS ELITE AX", 26990, 29990, 4,
     {"socket": "LGA1700", "ram_type": "DDR5", "ram_slots": 4, "form_factor": "ATX"}),
    ("motherboard", "ASRock", "ASRock B550M Pro4", 9490, None, 11,
     {"socket": "AM4", "ram_type": "DDR4", "ram_slots": 4, "form_factor": "mATX"}),
    ("motherboard", "MSI", "MSI MAG B650 TOMAHAWK WIFI", 21990, None, 7,
     {"socket": "AM5", "ram_type": "DDR5", "ram_slots": 4, "form_factor": "ATX"}),
    ("motherboard", "ASUS", "ASUS ROG STRIX B650E-I GAMING WIFI", 28990, None, 2,
     {"socket": "AM5", "ram_type": "DDR5", "ram_slots": 2, "form_factor": "Mini-ITX"}),
    # GPUs
    ("gpu", "Palit", "Palit GeForce RTX 3050 StormX 6GB", 19990, 21990, 10,
     {"vram_gb": 6, "tdp": 70, "length_mm": 166, "score": 25}),
    ("gpu", "MSI", "MSI GeForce RTX 4060 VENTUS 2X 8GB", 32990, None, 15,
     {"vram_gb": 8, "tdp": 115, "length_mm": 199, "score": 45}),
    ("gpu", "Sapphire", "Sapphire Radeon RX 7700 XT PULSE 12GB", 44990, 49990, 6,
     {"vram_gb": 12, "tdp": 245, "length_mm": 280, "score": 62}),
    ("gpu", "Gigabyte", "Gigabyte GeForce RTX 4070 SUPER WINDFORCE 12GB", 64990, None, 5,
     {"vram_gb": 12, "tdp": 220, "length_mm": 261, "score": 72}),
    ("gpu", "ASUS", "ASUS TUF Radeon RX 7900 XTX 24GB", 104990, None, 2,
     {"vram_gb": 24, "tdp": 355, "length_mm": 352, "score": 90}),
    ("gpu", "MSI", "MSI GeForce RTX 4090 SUPRIM X 24GB", 199990, 214990, 1,
     {"vram_gb": 24, "tdp": 450, "length_mm": 336, "score": 100}),
    # RAM
    ("ram", "Kingston", "Kingston FURY Beast 8GB DDR4-3200", 2290, None, 30,
     {"ram_type": "DDR4", "size_gb": 8, "sticks": 1}),
    ("ram", "Kingston", "Kingston FURY Beast 16GB (2x8) DDR4-3200", 3990, 4490, 25,
     {"ram_type": "DDR4", "size_gb": 16, "sticks": 2}),
    ("ram", "Corsair", "Corsair Vengeance LPX 32GB (2x16) DDR4-3600", 7490, None, 12,
     {"ram_type": "DDR4", "size_gb": 32, "sticks": 2}),
    ("ram", "G.Skill", "G.Skill Flare X5 32GB (2x16) DDR5-6000", 10490, 11990, 10,
     {"ram_type": "DDR5", "size_gb": 32, "sticks": 2}),
    ("ram", "Kingston", "Kingston FURY Beast 64GB (2x32) DDR5-5600", 19990, None, 4,
     {"ram_type": "DDR5", "size_gb": 64, "sticks": 2}),
    # Storage
    ("storage", "Kingston", "Kingston NV2 500GB NVMe", 3490, None, 40,
     {"type": "NVMe", "size_gb": 500}),
    ("storage", "Samsung", "Samsung 980 1TB NVMe", 7990, 8990, 18,
     {"type": "NVMe", "size_gb": 1000}),
    ("storage", "WD", "WD Blue SA510 1TB SATA SSD", 5990, None, 20,
     {"type": "SATA SSD", "size_gb": 1000}),
    ("storage", "Seagate", "Seagate BarraCuda 2TB HDD", 5490, None, 15,
     {"type": "HDD", "size_gb": 2000}),
    ("storage", "Samsung", "Samsung 990 PRO 2TB NVMe", 16990, None, 6,
     {"type": "NVMe", "size_gb": 2000}),
    # Power supplies
    ("psu", "DEEPCOOL", "DEEPCOOL PF450 450W", 3490, None, 20, {"wattage": 450}),
    ("psu", "Cougar", "Cougar GEX 650W", 6990, None, 14, {"wattage": 650}),
    ("psu", "be quiet!", "be quiet! Pure Power 12 M 750W", 10990, 11990, 9, {"wattage": 750}),
    ("psu", "Seasonic", "Seasonic FOCUS GX-850 850W", 13990, None, 6, {"wattage": 850}),
    ("psu", "Corsair", "Corsair RM1000x 1000W", 18990, None, 3, {"wattage": 1000}),
    # Cases
    ("case", "Cooler Master", "Cooler Master MasterBox Q300L", 3990, None, 12,
     {"form_factors": ["mATX", "Mini-ITX"], "max_gpu_mm": 360}),
    ("case", "DEEPCOOL", "DEEPCOOL CH370", 5490, 5990, 10,
     {"form_factors": ["mATX", "Mini-ITX"], "max_gpu_mm": 320}),
    ("case", "Fractal Design", "Fractal Design Pop Air", 7990, None, 8,
     {"form_factors": ["ATX", "mATX", "Mini-ITX"], "max_gpu_mm": 405}),
    ("case", "Lian Li", "Lian Li LANCOOL 216", 9990, None, 7,
     {"form_factors": ["ATX", "mATX", "Mini-ITX"], "max_gpu_mm": 392}),
    ("case", "NZXT", "NZXT H1 V2", 22990, None, 2,
     {"form_factors": ["Mini-ITX"], "max_gpu_mm": 324}),
]

NEWS = [
    ("promo", "Чёрная пятница: до −15% на видеокарты",
     "Скидки на популярные видеокарты до конца месяца. Количество ограничено."),
    ("promo", "Бонусы ×2 за первую сборку",
     "Соберите ПК в конфигураторе и оформите заказ — получите двойной кешбэк бонусами."),
    ("news", "DDR5 дешевеет",
     "Цены на память DDR5 за полгода снизились почти на треть — переход на новые платформы стал выгоднее."),
    ("news", "Как выбрать блок питания",
     "Берите блок с запасом 20–30% к потреблению системы. Наш конфигуратор посчитает нужную мощность сам."),
    ("game", "Системные требования новых игр растут",
     "Для комфортной игры в 2K в новинках уже рекомендуют 12 ГБ видеопамяти."),
    ("game", "Киберспортивный турнир магазина",
     "Регистрируйтесь на турнир по шутерам — призы: видеокарта и бонусы на покупки."),
]

FACTS = [
    "Первый жёсткий диск IBM 1956 года весил около тонны и хранил всего 5 МБ.",
    "Термопаста нужна, чтобы заполнить микронеровности между процессором и кулером.",
    "Видеокарты изначально создавались только для вывода изображения, а не для вычислений.",
    "Двухканальный режим памяти может дать прирост FPS до 10–20% во встроенной графике.",
    "Слово «баг» прижилось после того, как в 1947 году в компьютере Mark II нашли мотылька.",
    "Современный процессор содержит десятки миллиардов транзисторов.",
    "SSD быстрее HDD не только при чтении — он ещё и не боится тряски.",
    "Блок питания с сертификатом 80 PLUS Gold отдаёт компонентам не меньше 87% потребляемой энергии.",
    "Первая компьютерная мышь была деревянной.",
    "Кэш L3 у процессоров AMD X3D увеличен за счёт «стопки» кристаллов памяти.",
]


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            print("seed: database is not empty — skipping")
            return

        password = settings.seed_password or secrets.token_urlsafe(9)
        password_hash = hash_password(password)
        for email, name, role in USERS:
            user = User(email=email, name=name, role=role, password_hash=password_hash, bonus_balance=0)
            db.add(user)
            if role == "client":
                db.flush()
                user.bonus_balance = settings.welcome_bonus
                db.add(BonusHistory(user_id=user.id, amount=settings.welcome_bonus,
                                    reason=t("bonus.reason.welcome", lang=DEFAULT_LANGUAGE)))

        categories = {}
        for position, (slug, name) in enumerate(CATEGORIES):
            categories[slug] = Category(slug=slug, name=name, position=position)
            db.add(categories[slug])

        for cat, brand, name, price, old_price, stock, specs in PRODUCTS:
            db.add(Product(category=categories[cat], brand=brand, name=name, price=price, old_price=old_price,
                           stock=stock, specs=specs, description=f"{name} — в наличии в Technology-Store."))

        for news_type, title, text in NEWS:
            db.add(News(type=news_type, title=title, text=text))
        for text in FACTS:
            db.add(Fact(text=text))

        db.commit()
        if not settings.seed_password:
            print("=" * 60)
            print(f"seed: password for {', '.join(e for e, _, _ in USERS)}:")
            print(f"seed:     {password}")
            print("seed: it is shown only once — save it or set SEED_PASSWORD in .env")
            print("=" * 60)
        print(f"seed: added {len(USERS)} users, {len(PRODUCTS)} products, "
              f"{len(NEWS)} news, {len(FACTS)} facts")


if __name__ == "__main__":
    seed()
