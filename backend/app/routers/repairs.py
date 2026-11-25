"""Repairs: an engineer accepts a device from a client and leads it to the end.

Statuses: accepted -> diagnostics -> repairing -> ready -> issued (or cancelled before issue).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_permission
from app.i18n import t
from app.models import Repair, User
from app.pagination import page_paginate
from app.routers.catalog import _like
from app.schemas import Page, RepairCreate, RepairOut, RepairStatus, RepairUpdate

router = APIRouter(tags=["Repairs"])
can_manage_repairs = require_permission("repairs.manage")

# Which status can follow which
REPAIR_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "accepted": ("diagnostics", "cancelled"),
    "diagnostics": ("repairing", "ready", "cancelled"),  # "ready" = nothing to repair
    "repairing": ("ready", "cancelled"),
    "ready": ("issued",),
    "issued": (),
    "cancelled": (),
}


def _status_name(value: str) -> str:
    return t(f"repairs.status.{value}")


@router.get("/api/repairs/my", response_model=list[RepairOut])
def my_repairs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Repairs of the current client (linked by account)."""
    return db.scalars(select(Repair).where(Repair.client_id == user.id).order_by(Repair.id.desc())).unique().all()


@router.get("/api/admin/repairs", response_model=Page[RepairOut], dependencies=[Depends(can_manage_repairs)])
def list_repairs(
    status: RepairStatus | None = None,
    search: str | None = Query(None, description="client name, phone, device or repair number"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Repair).order_by(Repair.id.desc())
    if status:
        stmt = stmt.where(Repair.status == status)
    if search and search.strip():
        like = _like(search)
        conds: list[ColumnElement[bool]] = [
            Repair.client_name.ilike(like, escape="\\"),
            Repair.client_phone.ilike(like, escape="\\"),
            Repair.device.ilike(like, escape="\\"),
        ]
        number = search.strip().lstrip("#")
        if number.isdigit():
            conds.append(Repair.id == int(number))
        stmt = stmt.where(or_(*conds))
    return page_paginate(db, stmt, page, page_size)


@router.post("/api/admin/repairs", response_model=RepairOut, status_code=status.HTTP_201_CREATED)
def create_repair(data: RepairCreate, user: User = Depends(can_manage_repairs), db: Session = Depends(get_db)):
    """Accept a device. If the client has an account, give their email: they will see the repair in the account."""
    client_id = None
    if data.client_email and data.client_email.strip():
        client = db.scalar(select(User).where(User.email == data.client_email.strip().lower()))
        if client is None:
            raise HTTPException(400, t("errors.client_not_found", email=data.client_email.strip()))
        client_id = client.id
    repair = Repair(
        client_id=client_id,
        client_name=data.client_name,
        client_phone=data.client_phone,
        device=data.device,
        problem=data.problem,
        price=data.price,
        status="accepted",
        engineer_comment="",
        engineer_id=user.id,
    )
    db.add(repair)
    db.commit()
    db.refresh(repair)
    return repair


def _get_repair(db: Session, repair_id: int, lock: bool = False) -> Repair:
    # lock only the repairs row: FOR UPDATE can't lock the optional (outer-joined) engineer
    repair = db.get(Repair, repair_id, with_for_update={"of": Repair} if lock else None)
    if repair is None:
        raise HTTPException(404, t("errors.repair_not_found"))
    return repair


@router.get("/api/admin/repairs/{repair_id}", response_model=RepairOut, dependencies=[Depends(can_manage_repairs)])
def get_repair(repair_id: int, db: Session = Depends(get_db)):
    return _get_repair(db, repair_id)


@router.patch("/api/admin/repairs/{repair_id}", response_model=RepairOut)
def update_repair(
    repair_id: int, data: RepairUpdate, user: User = Depends(can_manage_repairs), db: Session = Depends(get_db)
):
    """Change status, price, comment. The engineer who changes the status becomes responsible for the repair."""
    repair = _get_repair(db, repair_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    new_status = changes.pop("status", None)

    for field in ("device", "problem", "engineer_comment"):
        if field in changes and changes[field] is None:
            raise HTTPException(422, t("errors.field_required", field=field))
    for field, value in changes.items():
        setattr(repair, field, value)

    if new_status and new_status != repair.status:
        allowed = REPAIR_TRANSITIONS[repair.status]
        if new_status not in allowed:
            raise HTTPException(400, t(
                "errors.status_transition",
                from_status=_status_name(repair.status),
                to_status=_status_name(new_status),
                allowed=", ".join(map(_status_name, allowed)) or t("errors.status_none"),
            ))
        if new_status in ("ready", "issued") and repair.price is None:
            raise HTTPException(400, t("errors.repair_price_required"))
        repair.status = new_status
        repair.engineer_id = user.id
    db.commit()
    db.refresh(repair)
    return repair
