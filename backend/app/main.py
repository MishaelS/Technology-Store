import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import backups
from app.config import settings
from app.i18n import LanguageMiddleware, available_languages, load, pick_language, t
from app.database import SessionLocal
from app.models import ErrorLog
from app.routers import admin, auth, backups as backups_router, builder, cart, catalog, orders, repairs, stock, system, uploads

@asynccontextmanager
async def lifespan(_: FastAPI):
    """While the server runs: the auto backup check (it does nothing until auto backups are on)."""
    task = asyncio.create_task(auto_backup_loop()) if settings.backup_scheduler else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="Technology-Store API",
    description="Educational online store for PC components. "
    "To call protected endpoints: log in via /api/auth/login, "
    "copy the token and paste it into the Authorize button.",
    version=system.API_VERSION,
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

for module in (auth, catalog, cart, orders, builder, admin, repairs, stock, system, uploads, backups_router):
    app.include_router(module.router)

logger = logging.getLogger("app")


# ---------- one error format for the whole API: {"detail": "text"} ----------

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """422 with a readable text in `detail` and every bad field in `fields`."""
    fields = []
    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part not in ("body", "query", "path")]
        message = error["msg"].removeprefix("Value error, ")
        fields.append({"field": ".".join(location) or "body", "message": message})
    names = ", ".join(dict.fromkeys(f["field"] for f in fields))
    return JSONResponse(status_code=422, content={"detail": t("errors.validation", fields=names), "fields": fields})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    """500 without internal details. Runs outside LanguageMiddleware, so the language is picked here."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    try:  # keep it for the tech support page; never fail because of logging
        with SessionLocal() as db:
            db.add(ErrorLog(method=request.method, path=request.url.path[:500],
                            error=f"{type(exc).__name__}: {exc}"[:2000]))
            db.commit()
    except Exception:
        logger.exception("Could not save the error to error_log")
    lang = pick_language(request.query_params.get("lang"), request.headers.get("accept-language"))
    return JSONResponse(status_code=500, content={"detail": t("errors.internal", lang=lang)})


# ---------- auto backups ----------
# Once a minute the task checks whether an auto backup is due (app/backups.py, auto.json).
# Auto backups are off until turned on in the admin panel, so by default this does nothing.

AUTO_BACKUP_CHECK_SECONDS = 60


async def auto_backup_loop() -> None:
    def tick() -> None:
        with SessionLocal() as db:
            made = backups.run_auto(db)
            if made:
                logger.info("auto backup %s", made["name"])

    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:  # a failed backup must not stop the next ones
            logger.exception("auto backup failed")
        await asyncio.sleep(AUTO_BACKUP_CHECK_SECONDS)


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
