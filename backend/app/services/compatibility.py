"""PC builder: compatibility checks and build performance score.

Works on the products.specs field. Required specs keys per category: see SPEC_FIELDS.
"""

import math
from collections import defaultdict

from app.i18n import t
from app.models import Product

# Required specs keys per category (validated when a product is created in the admin panel)
SPEC_FIELDS: dict[str, tuple[str, ...]] = {
    "cpu": ("socket", "cores", "tdp", "score"),          # + optional igpu: bool
    "cooler": ("type", "sockets", "tdp"),                # tdp: how much heat it can take away, W; + optional radiator_mm
    "motherboard": ("socket", "ram_type", "ram_slots", "form_factor"),
    "ram": ("ram_type", "size_gb", "sticks"),
    "gpu": ("vram_gb", "tdp", "length_mm", "score"),
    "psu": ("wattage",),
    "case": ("form_factors", "max_gpu_mm"),
    "storage": ("type", "size_gb"),
}

REQUIRED = ("cpu", "cooler", "motherboard", "ram", "psu", "storage")      # a PC can't be built without these
SINGLE = ("cpu", "cooler", "motherboard", "gpu", "psu", "case")           # at most one of each

TIERS = (  # (min score, code); names are in locales: builder.tiers.<code>
    (80, "top"),
    (55, "powerful"),
    (30, "gaming"),
    (0, "office"),
)

BASE_POWER = 100      # W for motherboard, drives, fans
PSU_RESERVE = 1.2     # PSU headroom
IGPU_SCORE = 8        # "performance" of integrated graphics


# Value kind of every specs field. Wrong types used to crash check_build (e.g. "650" instead of 650).
SPEC_KINDS: dict[str, str] = {
    "socket": "text", "ram_type": "text", "form_factor": "text", "type": "text",
    "cores": "number", "tdp": "number", "ram_slots": "number", "size_gb": "number", "sticks": "number",
    "vram_gb": "number", "length_mm": "number", "wattage": "number", "max_gpu_mm": "number", "radiator_mm": "number",
    "score": "score",
    "igpu": "flag",
    "form_factors": "text_list", "sockets": "text_list",
}
OPTIONAL_SPEC_FIELDS: dict[str, tuple[str, ...]] = {"cpu": ("igpu",), "cooler": ("radiator_mm",)}


def _is_valid(kind: str, value) -> bool:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "text":
        return isinstance(value, str) and value.strip() != ""
    if kind == "number":
        return is_number and value > 0
    if kind == "score":
        return is_number and 0 <= value <= 100
    if kind == "flag":
        return isinstance(value, bool)
    if kind == "text_list":
        return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)
    return False


def missing_spec_fields(category: str, specs: dict) -> list[str]:
    return [f for f in SPEC_FIELDS.get(category, ()) if f not in specs]


def invalid_spec_fields(category: str, specs: dict) -> list[str]:
    """Known fields that are present but have a wrong type or value."""
    known = SPEC_FIELDS.get(category, ()) + OPTIONAL_SPEC_FIELDS.get(category, ())
    return [f for f in known if f in specs and not _is_valid(SPEC_KINDS[f], specs[f])]


def _part(category: str) -> str:
    return t(f"builder.parts.{category}")


def _check(code: str, status: str, message_key: str, **params) -> dict:
    """message_key is a key inside builder.checks in the locale files."""
    return {"code": code, "status": status, "message": t(f"builder.checks.{message_key}", **params)}


def check_build(products: list[Product]) -> dict:
    """products: selected items; a repeated id means several pieces (e.g. 2 RAM kits)."""
    by_cat: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by_cat[p.category_slug].append(p)

    def one(cat: str) -> Product | None:
        return by_cat[cat][0] if by_cat[cat] else None

    cpu, mb, gpu, psu, case = one("cpu"), one("motherboard"), one("gpu"), one("psu"), one("case")
    cooler = one("cooler")
    rams = by_cat["ram"]
    checks: list[dict] = []

    # 0. Extra parts
    for cat in SINGLE:
        if len(by_cat[cat]) > 1:
            checks.append(_check(f"single_{cat}", "error", "single", part=_part(cat)))

    # 1. Socket
    if cpu and mb:
        s_cpu, s_mb = cpu.specs["socket"], mb.specs["socket"]
        checks.append(
            _check("socket", "ok", "socket_ok", socket=s_cpu)
            if s_cpu == s_mb
            else _check("socket", "error", "socket_error", cpu_socket=s_cpu, mb_socket=s_mb)
        )
    else:
        checks.append(_check("socket", "skip", "socket_skip"))

    # 1b. Cooler: fits the CPU socket and takes away the CPU heat
    if cpu and cooler:
        socket = cpu.specs["socket"]
        if socket not in cooler.specs["sockets"]:
            checks.append(_check("cooler", "error", "cooler_socket_error", socket=socket,
                                 supported=", ".join(cooler.specs["sockets"])))
        elif cooler.specs["tdp"] < cpu.specs["tdp"]:
            checks.append(_check("cooler", "warning", "cooler_weak", cooler=cooler.specs["tdp"], cpu=cpu.specs["tdp"]))
        else:
            checks.append(_check("cooler", "ok", "cooler_ok", socket=socket, cooler=cooler.specs["tdp"], cpu=cpu.specs["tdp"]))
    else:
        checks.append(_check("cooler", "skip", "cooler_skip"))

    # 2. RAM type
    if mb and rams:
        wrong = [r for r in rams if r.specs["ram_type"] != mb.specs["ram_type"]]
        checks.append(
            _check("ram_type", "ok", "ram_type_ok", ram_type=mb.specs["ram_type"])
            if not wrong
            else _check(
                "ram_type", "error", "ram_type_error",
                mb_type=mb.specs["ram_type"], ram_type=wrong[0].specs["ram_type"],
            )
        )
    else:
        checks.append(_check("ram_type", "skip", "ram_skip"))

    # 3. RAM slots
    sticks = sum(r.specs["sticks"] for r in rams)
    if mb and rams:
        slots = mb.specs["ram_slots"]
        checks.append(
            _check("ram_slots", "ok", "ram_slots_ok", sticks=sticks, slots=slots)
            if sticks <= slots
            else _check("ram_slots", "error", "ram_slots_error", sticks=sticks, slots=slots)
        )
    else:
        checks.append(_check("ram_slots", "skip", "ram_skip"))

    # 4. PSU wattage
    cpu_tdp = cpu.specs["tdp"] if cpu else 0
    gpu_tdp = gpu.specs["tdp"] if gpu else 0
    power_draw = cpu_tdp + gpu_tdp + BASE_POWER
    need = power_draw * PSU_RESERVE
    recommended_psu = math.ceil(need / 50) * 50
    if psu and (cpu or gpu):
        w = psu.specs["wattage"]
        checks.append(
            _check("psu", "ok", "psu_ok", watts=w, need=recommended_psu)
            if w >= need
            else _check("psu", "error", "psu_error", watts=w, need=recommended_psu)
        )
    else:
        checks.append(_check("psu", "skip", "psu_skip"))

    # 5. GPU length
    if gpu and case:
        length, max_len = gpu.specs["length_mm"], case.specs["max_gpu_mm"]
        checks.append(
            _check("gpu_length", "ok", "gpu_length_ok", length=length, max=max_len)
            if length <= max_len
            else _check("gpu_length", "error", "gpu_length_error", length=length, max=max_len)
        )
    else:
        checks.append(_check("gpu_length", "skip", "gpu_length_skip"))

    # 6. Form factor
    if mb and case:
        ff = mb.specs["form_factor"]
        checks.append(
            _check("form_factor", "ok", "form_factor_ok", form_factor=ff)
            if ff in case.specs["form_factors"]
            else _check(
                "form_factor", "error", "form_factor_error",
                form_factor=ff, supported=", ".join(case.specs["form_factors"]),
            )
        )
    else:
        checks.append(_check("form_factor", "skip", "form_factor_skip"))

    # 7. Graphics: no GPU and no integrated graphics
    if cpu and not gpu:
        checks.append(
            _check("graphics", "warning", "graphics_igpu")
            if cpu.specs.get("igpu")
            else _check("graphics", "error", "graphics_error")
        )

    # 8. Completeness
    missing = [_part(c) for c in REQUIRED if not by_cat[c]]
    if not case:
        missing.append(_part("case"))
    checks.append(
        _check("complete", "ok", "complete_ok")
        if not missing
        else _check("complete", "warning", "complete_missing", parts=", ".join(missing))
    )

    # Performance score
    cpu_score = cpu.specs["score"] if cpu else 0
    if gpu:
        gpu_score = gpu.specs["score"]
    else:
        gpu_score = IGPU_SCORE if cpu and cpu.specs.get("igpu") else 0
    score = 0.4 * cpu_score + 0.6 * gpu_score
    ram_total = sum(r.specs["size_gb"] for r in rams)
    if rams and ram_total < 16:
        score -= 10
    score = max(0, min(100, round(score)))
    tier = next(code for low, code in TIERS if score >= low)

    return {
        "checks": checks,
        "is_compatible": not any(c["status"] == "error" for c in checks),
        "is_complete": not missing,
        "cpu_score": cpu_score,
        "gpu_score": gpu_score,
        "score": score,
        "tier": tier,
        "tier_name": t(f"builder.tiers.{tier}"),
        "total_price": sum(p.price for p in products),
        "power_draw": power_draw,
        "recommended_psu": recommended_psu,
        "ram_total_gb": ram_total,
    }
