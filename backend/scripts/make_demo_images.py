"""Draws demo pictures (SVG) for products and news: resources/demo/products, resources/demo/news.

Run from the repository root, plain Python, no libraries needed:
    python3 backend/scripts/make_demo_images.py

Product lists are read from backend/app/seed.py and backend/app/demo_data.py without importing them
(so the database libraries aren't needed). Every product gets a picture in its category's color
with the category icon, the brand and its main spec (large: the card shows it small). app.demo links products to these files.
"""

import ast
import hashlib
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICONS = ROOT / "resources" / "icons"
OUT = ROOT / "resources" / "demo"

# category -> (main color, light background)
COLORS = {
    "cpu": ("#3B5BDB", "#EEF2FF"),
    "motherboard": ("#0C8599", "#E3FAFC"),
    "gpu": ("#7048E8", "#F3F0FF"),
    "ram": ("#E8590C", "#FFF4E6"),
    "storage": ("#1971C2", "#E7F5FF"),
    "psu": ("#E67700", "#FFF9DB"),
    "case": ("#495057", "#F1F3F5"),
}
NEWS_COLORS = {"news": ("#3B5BDB", "#EEF2FF"), "promo": ("#C92A2A", "#FFF5F5"), "game": ("#2B8A3E", "#EBFBEE")}
NEWS_ICONS = {"news": "navigation/news", "promo": "content/promo", "game": "content/game"}


def read_list(path: Path, name: str) -> list:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{name} not found in {path}")


def slug(name: str) -> str:
    # the same rule as app.demo.slug
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def icon_body(name: str) -> str:
    svg = (ICONS / f"{name}.svg").read_text()
    return svg[svg.index(">") + 1: svg.rindex("</svg>")]


def number(seed: str, low: int, high: int) -> int:
    """A stable "random" number from a text: the same product always gets the same picture."""
    return low + int(hashlib.md5(seed.encode()).hexdigest(), 16) % (high - low + 1)


def main_spec(category: str, s: dict) -> str:
    match category:
        case "cpu": return f"{s['socket']} · {s['cores']} ядер"
        case "motherboard": return f"{s['socket']} · {s['ram_type']} · {s['form_factor']}"
        case "gpu": return f"{s['vram_gb']} ГБ · {s['tdp']} Вт"
        case "ram": return f"{s['ram_type']} · {s['size_gb']} ГБ"
        case "storage": return f"{s['type']} · {s['size_gb'] // 1000} ТБ" if s["size_gb"] >= 1000 else f"{s['type']} · {s['size_gb']} ГБ"
        case "psu": return f"{s['wattage']} Вт"
        case "case": return f"до {s['max_gpu_mm']} мм"
    return ""


def product_svg(category: str, brand: str, name: str, specs: dict) -> str:
    color, light = COLORS[category]
    angle = number(name, 0, 359)
    cx, cy = number(name + "x", 420, 520), number(name + "y", 220, 250)
    # a few soft shapes in the background, placed by the name
    shapes = "".join(
        f'<rect x="{number(name + str(i) + "a", -40, 700)}" y="{number(name + str(i) + "b", -40, 520)}" '
        f'width="{number(name + str(i) + "c", 90, 200)}" height="{number(name + str(i) + "c", 90, 200)}" rx="28" '
        f'transform="rotate({number(name + str(i) + "d", -30, 30)})" fill="{color}" opacity="0.06"/>'
        for i in range(4)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" width="800" height="600">
<defs>
<linearGradient id="bg" gradientTransform="rotate({angle} .5 .5)"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{light}"/></linearGradient>
<radialGradient id="glow"><stop offset="0" stop-color="{color}" stop-opacity="0.22"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>
</defs>
<rect width="800" height="600" fill="url(#bg)"/>
{shapes}
<circle cx="{cx}" cy="{cy}" r="230" fill="url(#glow)"/>
<circle cx="{cx}" cy="{cy}" r="150" fill="#FFFFFF" opacity="0.75"/>
<g transform="translate({cx} {cy}) scale(8.5) translate(-12 -12)" fill="none" stroke="{color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">{icon_body(f"categories/{category}")}</g>
<text x="40" y="520" fill="{color}" font-family="Manrope, system-ui, sans-serif" font-size="46" font-weight="800">{escape(brand)}</text>
<text x="40" y="568" fill="#495057" font-family="Manrope, system-ui, sans-serif" font-size="32" font-weight="600">{escape(main_spec(category, specs))}</text>
</svg>
'''


def news_svg(news_type: str, variant: int) -> str:
    color, light = NEWS_COLORS[news_type]
    body = icon_body(NEWS_ICONS[news_type])
    icon = lambda x, y, size, width, opacity: (  # noqa: E731
        f'<g transform="translate({x} {y}) scale({size / 24}) translate(-12 -12)" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}">{body}</g>')
    decor = {
        1: "".join(f'<circle cx="980" cy="360" r="{r}" fill="none" stroke="{color}" stroke-width="2" opacity="{0.35 - r / 2000}"/>'
                   for r in range(120, 560, 70)) + icon(980, 360, 220, 1.4, 1),
        2: "".join(f'<rect x="{-200 + i * 140}" y="-100" width="60" height="1000" fill="{color}" opacity="0.06" transform="rotate(25)"/>'
                   for i in range(14)) + icon(640, 360, 260, 1.3, 1),
        3: "".join(f'<circle cx="{80 + (i % 16) * 75}" cy="{70 + (i // 16) * 75}" r="5" fill="{color}" opacity="0.15"/>'
                   for i in range(16 * 9)) + icon(320, 380, 240, 1.4, 1),
        4: icon(200, 200, 140, 1.6, 0.25) + icon(1080, 540, 180, 1.6, 0.25) + icon(700, 330, 260, 1.3, 1),
    }[variant]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{light}"/></linearGradient></defs>
<rect width="1280" height="720" fill="url(#bg)"/>
{decor}
</svg>
'''


def main() -> None:
    products = read_list(ROOT / "backend/app/seed.py", "PRODUCTS") + read_list(ROOT / "backend/app/demo_data.py", "DEMO_PRODUCTS")
    (OUT / "products").mkdir(parents=True, exist_ok=True)
    (OUT / "news").mkdir(parents=True, exist_ok=True)
    for category, brand, name, _price, _old, _stock, specs in products:
        (OUT / "products" / f"{slug(name)}.svg").write_text(product_svg(category, brand, name, specs))
    for news_type in NEWS_COLORS:
        for variant in range(1, 5):
            (OUT / "news" / f"{news_type}-{variant}.svg").write_text(news_svg(news_type, variant))
    print(f"made {len(products)} product pictures and {len(NEWS_COLORS) * 4} news pictures in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
