"""Translations: app/i18n.py and the files in resources/locales."""

import json
import string
from pathlib import Path

import pytest

from app import i18n
from app.i18n import available_languages, pick_language, t

LOCALES = Path(i18n.settings.locales_dir)


def flatten(data, prefix=""):
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_ru_and_en_exist():
    assert {"ru", "en"} <= set(available_languages())


@pytest.mark.parametrize("lang", ["en"])
def test_same_keys_and_placeholders_as_russian(lang):
    ru = flatten(json.loads((LOCALES / "ru.json").read_text(encoding="utf-8")))
    other = flatten(json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8")))
    assert ru.keys() == other.keys()
    for key in ru:
        assert placeholders(ru[key]) == placeholders(other[key]), key


def test_no_reserved_placeholder_names():
    """`lang` and `default` are parameters of t() and can't be used as placeholders."""
    for path in LOCALES.glob("*.json"):
        for key, text in flatten(json.loads(path.read_text(encoding="utf-8"))).items():
            assert not placeholders(text) & {"lang", "default"}, f"{path.name}: {key}"


def test_every_key_used_in_code_exists():
    import re

    app_dir = Path(i18n.__file__).parent
    used = set()
    for file in app_dir.rglob("*.py"):
        used |= set(re.findall(r'\bt\("([a-z_.]+)"', file.read_text(encoding="utf-8")))
    ru = flatten(json.loads((LOCALES / "ru.json").read_text(encoding="utf-8")))
    assert used, "no t() calls found"
    assert sorted(used - ru.keys()) == []


def test_every_key_used_by_the_frontend_exists():
    frontend = Path(i18n.settings.locales_dir).parents[1] / "frontend" / "src"
    if not frontend.exists():
        pytest.skip("frontend is not mounted")
    import re

    used = set()
    for file in frontend.rglob("*.js"):
        used |= set(re.findall(r'\bt\(\s*"([a-z_.]+)"', file.read_text(encoding="utf-8")))
    ru = flatten(json.loads((LOCALES / "ru.json").read_text(encoding="utf-8")))
    assert sorted(used - ru.keys()) == []


def test_translate_with_params():
    assert t("errors.bonus_limit", lang="ru", max=10) == "Можно списать не больше 10 бонусов"
    assert t("errors.bonus_limit", lang="en", max=10) == "You can spend at most 10 points"


def test_unknown_language_falls_back_to_russian():
    assert t("errors.cart_empty", lang="de") == "Корзина пуста"


def test_unknown_key_returns_default_or_key():
    assert t("no.such.key", lang="en") == "no.such.key"
    assert t("no.such.key", lang="en", default="fallback") == "fallback"


@pytest.mark.parametrize(
    "query, header, expected",
    [
        (None, None, "ru"),
        ("en", None, "en"),
        (None, "en-US,en;q=0.9", "en"),
        (None, "de-DE,de;q=0.9,en;q=0.5", "en"),   # first supported language wins
        (None, "de", "ru"),                        # nothing supported -> default
        ("ru", "en", "ru"),                        # ?lang= beats the header
        ("xx", "en", "en"),
    ],
)
def test_pick_language(query, header, expected):
    assert pick_language(query, header) == expected
