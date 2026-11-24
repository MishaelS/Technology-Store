"""Translations from resources/locales/<lang>.json.

Usage:  t("errors.cart_empty")  or  t("errors.bonus_limit", max=100)

The language of a request is picked by LanguageMiddleware:
?lang=en  ->  Accept-Language header  ->  DEFAULT_LANGUAGE.
"""

import json
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import parse_qs

from app.config import settings

DEFAULT_LANGUAGE = "ru"

_current: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)
_cache: dict[str, tuple[float, dict]] = {}  # lang -> (file mtime, data)


def _dir() -> Path:
    return Path(settings.locales_dir)


def available_languages() -> list[str]:
    return sorted(p.stem for p in _dir().glob("*.json"))


def load(lang: str) -> dict:
    """Locale data; re-read automatically when the file changes."""
    path = _dir() / f"{lang}.json"
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    cached = _cache.get(lang)
    if cached is None or cached[0] != mtime:
        cached = (mtime, json.loads(path.read_text(encoding="utf-8")))
        _cache[lang] = cached
    return cached[1]


def _lookup(data: dict, key: str) -> str | None:
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def t(key: str, lang: str | None = None, default: str | None = None, **params) -> str:
    """Translate a key. Falls back to DEFAULT_LANGUAGE, then to `default`, then to the key itself."""
    lang = lang or _current.get()
    text = _lookup(load(lang), key)
    if text is None and lang != DEFAULT_LANGUAGE:
        text = _lookup(load(DEFAULT_LANGUAGE), key)
    if text is None:
        return default if default is not None else key
    return text.format(**params) if params else text


def get_language() -> str:
    return _current.get()


def pick_language(query_lang: str | None, accept_language: str | None) -> str:
    candidates = [query_lang] if query_lang else []
    if accept_language:
        candidates += [part.split(";")[0].strip() for part in accept_language.split(",")]
    available = available_languages()
    for candidate in candidates:
        code = candidate.lower().split("-")[0]
        if code in available:
            return code
    return DEFAULT_LANGUAGE


class LanguageMiddleware:
    """Sets the request language and adds a Content-Language header to the response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        query = parse_qs(scope.get("query_string", b"").decode())
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        lang = pick_language((query.get("lang") or [None])[0], headers.get("accept-language"))
        token = _current.set(lang)

        async def send_with_language(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"content-language", lang.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_language)
        finally:
            _current.reset(token)
