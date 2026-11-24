"""Checks the translations in resources/locales.

* every language has the same keys and placeholders as the reference one (ru);
* every key used by the frontend (t("...") in frontend/src) exists.

Run: ./run.sh locales  (or python3 backend/scripts/check_locales.py)
Exit code 1 if something is missing.
"""

import json
import re
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "resources" / "locales"
FRONTEND = ROOT / "frontend" / "src"
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


def frontend_keys() -> set[str]:
    """Static keys from t("...") calls in the frontend (keys built with `...${x}` are not checked)."""
    keys = set()
    for path in FRONTEND.rglob("*.js") if FRONTEND.exists() else []:
        keys |= set(re.findall(r'\bt\(\s*"([a-z_.]+)"', path.read_text(encoding="utf-8")))
    return keys


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
    for key in sorted(frontend_keys() - reference.keys()):
        errors.append(f"frontend uses a missing key {key}")
    for error in errors:
        print(error)
    print(f"Languages: {', '.join(files)}; keys: {len(reference)}; problems: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
