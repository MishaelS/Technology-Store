"""Tech support page for the senior engineer: server, database and recent errors."""

import platform
import time

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_permission
from app.models import ErrorLog, Order, Product, Repair, User
from app.schemas import SystemOut

router = APIRouter(prefix="/api/admin/system", tags=["Tech support"])
can_view_system = require_permission("system.view")

STARTED_AT = time.monotonic()
API_VERSION = "0.3.0"


@router.get("", response_model=SystemOut, dependencies=[Depends(can_view_system)])
def system_info(db: Session = Depends(get_db)):
    try:
        version = db.scalar(text("SHOW server_version")) or ""
        size = db.scalar(text("SELECT pg_size_pretty(pg_database_size(current_database()))")) or ""
        migration = db.scalar(text("SELECT version_num FROM alembic_version"))
        database = {"ok": True, "version": f"PostgreSQL {version}", "size": size, "migration": migration}
    except Exception:  # the page must open even when the database is in trouble
        db.rollback()
        database = {"ok": False, "version": "", "size": "", "migration": None}

    day_ago = func.now() - text("interval '1 day'")
    counts = {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "products": db.scalar(select(func.count(Product.id))) or 0,
        "orders": db.scalar(select(func.count(Order.id))) or 0,
        "repairs": db.scalar(select(func.count(Repair.id))) or 0,
        "errors_24h": db.scalar(select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= day_ago)) or 0,
    }
    errors = db.scalars(select(ErrorLog).order_by(ErrorLog.id.desc()).limit(20)).all()
    return {
        "api_version": API_VERSION,
        "python_version": platform.python_version(),
        "uptime_seconds": int(time.monotonic() - STARTED_AT),
        "database": database,
        "counts": counts,
        "recent_errors": errors,
    }


@router.delete("/errors", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(can_view_system)])
def clear_errors(db: Session = Depends(get_db)):
    """Clear the error log (after the problems are fixed)."""
    db.execute(delete(ErrorLog))
    db.commit()
