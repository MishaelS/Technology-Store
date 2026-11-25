"""PC builder rules (services/compatibility.py) on fake products, without the database."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.i18n import _current
from app.services.compatibility import check_build, missing_spec_fields


def part(category, price=1000, **specs) -> Any:
    """A fake product: check_build only reads category_slug, price and specs."""
    return SimpleNamespace(category_slug=category, price=price, specs=specs)


CPU_AM5 = part("cpu", socket="AM5", cores=6, tdp=65, igpu=True, score=55)
CPU_NO_IGPU = part("cpu", socket="AM4", cores=6, tdp=65, igpu=False, score=42)
MB_AM5 = part("motherboard", socket="AM5", ram_type="DDR5", ram_slots=4, form_factor="ATX")
MB_ITX = part("motherboard", socket="AM5", ram_type="DDR5", ram_slots=2, form_factor="Mini-ITX")
RAM_DDR5 = part("ram", ram_type="DDR5", size_gb=32, sticks=2)
RAM_DDR4 = part("ram", ram_type="DDR4", size_gb=16, sticks=2)
RAM_SMALL = part("ram", ram_type="DDR5", size_gb=8, sticks=1)
GPU_MID = part("gpu", vram_gb=8, tdp=115, length_mm=199, score=45)
GPU_TOP = part("gpu", vram_gb=24, tdp=450, length_mm=336, score=100)
PSU_650 = part("psu", wattage=650)
PSU_450 = part("psu", wattage=450)
CASE_ATX = part("case", form_factors=["ATX", "mATX", "Mini-ITX"], max_gpu_mm=405)
CASE_SMALL = part("case", form_factors=["Mini-ITX"], max_gpu_mm=300)
SSD = part("storage", type="NVMe", size_gb=1000)

GOOD = [CPU_AM5, MB_AM5, RAM_DDR5, GPU_MID, PSU_650, CASE_ATX, SSD]


@pytest.fixture(autouse=True)
def russian():
    token = _current.set("ru")
    yield
    _current.reset(token)


def statuses(result):
    return {c["code"]: c["status"] for c in result["checks"]}


def test_good_build_is_compatible_and_complete():
    result = check_build(GOOD)
    assert result["is_compatible"] and result["is_complete"]
    assert set(statuses(result).values()) == {"ok"}


def test_empty_build():
    result = check_build([])
    assert result["is_compatible"]          # nothing to conflict with
    assert not result["is_complete"]
    assert result["score"] == 0 and result["tier"] == "office"
    assert statuses(result)["socket"] == "skip"


@pytest.mark.parametrize(
    "replace, code",
    [
        ({"motherboard": part("motherboard", socket="LGA1700", ram_type="DDR5", ram_slots=4, form_factor="ATX")}, "socket"),
        ({"ram": RAM_DDR4}, "ram_type"),
        ({"psu": PSU_450, "gpu": GPU_TOP}, "psu"),
        ({"case": part("case", form_factors=["ATX"], max_gpu_mm=150)}, "gpu_length"),
        ({"case": CASE_SMALL}, "form_factor"),
    ],
)
def test_each_rule_reports_an_error(replace, code):
    build = [replace.get(p.category_slug, p) for p in GOOD]
    result = check_build(build)
    assert statuses(result)[code] == "error"
    assert not result["is_compatible"]


def test_too_many_ram_sticks():
    result = check_build([MB_ITX, RAM_DDR5, RAM_DDR5])  # 4 sticks, 2 slots
    assert statuses(result)["ram_slots"] == "error"


def test_two_cpus_are_not_allowed():
    result = check_build(GOOD + [CPU_AM5])
    assert statuses(result)["single_cpu"] == "error"


def test_two_storage_drives_are_allowed():
    result = check_build(GOOD + [SSD])
    assert result["is_compatible"]


def test_no_gpu_with_integrated_graphics_is_a_warning():
    result = check_build([CPU_AM5])
    assert statuses(result)["graphics"] == "warning"
    assert result["gpu_score"] > 0


def test_no_gpu_without_integrated_graphics_is_an_error():
    result = check_build([CPU_NO_IGPU])
    assert statuses(result)["graphics"] == "error"


def test_power_and_psu_recommendation():
    result = check_build(GOOD)
    assert result["power_draw"] == 65 + 115 + 100
    assert result["recommended_psu"] == 350          # 280 * 1.2 = 336 -> rounded up to 50 W


def test_psu_exactly_enough_is_ok():
    # need = (65 + 0 + 100) * 1.2 = 198 W
    result = check_build([CPU_AM5, part("psu", wattage=198)])
    assert statuses(result)["psu"] == "ok"


@pytest.mark.parametrize(
    "cpu_score, gpu_score, tier",
    [(10, 10, "office"), (45, 45, "gaming"), (70, 72, "powerful"), (95, 100, "top")],
)
def test_tiers(cpu_score, gpu_score, tier):
    cpu = part("cpu", socket="AM5", cores=8, tdp=100, igpu=False, score=cpu_score)
    gpu = part("gpu", vram_gb=8, tdp=100, length_mm=200, score=gpu_score)
    assert check_build([cpu, gpu])["tier"] == tier


def test_small_ram_lowers_the_score():
    with_32 = check_build([CPU_AM5, GPU_MID, RAM_DDR5])["score"]
    with_8 = check_build([CPU_AM5, GPU_MID, RAM_SMALL])["score"]
    assert with_8 == with_32 - 10


def test_total_price_counts_repeats():
    assert check_build([SSD, SSD])["total_price"] == 2000


def test_messages_follow_the_request_language():
    ru = check_build([CPU_NO_IGPU])
    token = _current.set("en")
    en = check_build([CPU_NO_IGPU])
    _current.reset(token)
    assert ru["tier_name"] == "Офисный ПК" and en["tier_name"] == "Office PC"
    graphics = lambda r: next(c["message"] for c in r["checks"] if c["code"] == "graphics")  # noqa: E731
    assert "видеокарта" in graphics(ru) and "graphics card" in graphics(en)


def test_missing_spec_fields():
    assert missing_spec_fields("psu", {"wattage": 500}) == []
    assert missing_spec_fields("cpu", {"socket": "AM5"}) == ["cores", "tdp", "score"]
    assert missing_spec_fields("unknown", {}) == []
