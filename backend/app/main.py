from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.i18n import LanguageMiddleware, available_languages, load, t
from app.routers import admin, auth, builder, cart, catalog, orders

app = FastAPI(
    title="Technology-Store API",
    description="Educational online store for PC components. "
    "To call protected endpoints: log in via /api/auth/login, "
    "copy the token and paste it into the Authorize button.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Language"],
)
app.add_middleware(LanguageMiddleware)

for module in (auth, catalog, cart, orders, builder, admin):
    app.include_router(module.router)


@app.get("/api/health", tags=["Service"])
def health():
    return {"status": "ok"}


@app.get("/api/i18n", tags=["Service"])
def languages():
    """Available interface languages."""
    return [{"code": lang, "name": load(lang).get("meta", {}).get("name", lang)} for lang in available_languages()]


@app.get("/api/i18n/{lang}", tags=["Service"])
def translations(lang: str):
    """All interface texts for a language (the frontend can load them from here)."""
    if lang not in available_languages():
        raise HTTPException(404, t("errors.language_not_found", code=lang))
    return load(lang)
