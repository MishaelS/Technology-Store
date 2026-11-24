"""Checks that all locale files in resources/locales have the same keys and placeholders.

Run: python3 backend/scripts/check_locales.py
Compares every language with the reference one (ru). Exit code 1 if something is missing.
"""

import json
import string
import sys
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[2] / "resources" / "locales"
REFERENCE = "ru"


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    out = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, full + "."))
        else:
            out[full] = value
    return out


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def main() -> int:
    files = {p.stem: flatten(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(LOCALES.glob("*.json"))}
    reference = files[REFERENCE]
    errors = []
    for lang, keys in files.items():
        if lang == REFERENCE:
            continue
        for key in sorted(reference.keys() - keys.keys()):
            errors.append(f"{lang}: missing key {key}")
        for key in sorted(keys.keys() - reference.keys()):
            errors.append(f"{lang}: extra key {key} (not in {REFERENCE})")
        for key in sorted(reference.keys() & keys.keys()):
            if placeholders(reference[key]) != placeholders(keys[key]):
                errors.append(f"{lang}: placeholders differ in {key}")
    for error in errors:
        print(error)
    print(f"Languages: {', '.join(files)}; keys: {len(reference)}; problems: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
