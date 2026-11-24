"""PC builder: build check and the client's saved builds."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.i18n import t
from app.models import Build, BuildItem, Product, User
from app.permissions import has_permission
from app.schemas import BuilderIn, BuildCreate, BuildOut, CheckResult
from app.services.compatibility import check_build

router = APIRouter(tags=["PC builder"])


def load_products(db: Session, ids: list[int]) -> list[Product]:
    """Products by id list, keeping repeats (2 identical ids = 2 pieces)."""
    found = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(set(ids))))}
    missing = sorted({i for i in ids if i not in found or not found[i].is_active})
    if missing:
        raise HTTPException(400, t("errors.products_not_found", ids=", ".join(map(str, missing))))
    return [found[i] for i in ids]


def build_out(build: Build) -> dict:
    products = [item.product for item in build.items]
    return {
        "id": build.id,
        "name": build.name,
        "engineer_comment": build.engineer_comment,
        "created_at": build.created_at,
        "user": build.user,
        "items": products,
        "check": check_build(products),
    }


@router.post("/api/builder/check", response_model=CheckResult)
def check(data: BuilderIn, db: Session = Depends(get_db)):
    """Check compatibility and score performance. Available to guests too."""
    return check_build(load_products(db, data.product_ids))


@router.get("/api/builds", response_model=list[BuildOut])
def my_builds(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    builds = db.scalars(select(Build).where(Build.user_id == user.id).order_by(Build.id.desc())).unique()
    return [build_out(b) for b in builds]


@router.post("/api/builds", response_model=BuildOut, status_code=status.HTTP_201_CREATED)
def save_build(data: BuildCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    products = load_products(db, data.product_ids)
    build = Build(user_id=user.id, name=data.name.strip(), items=[BuildItem(product_id=p.id) for p in products])
    db.add(build)
    db.commit()
    db.refresh(build)
    return build_out(build)


def _get_build(db: Session, build_id: int, user: User) -> Build:
    build = db.get(Build, build_id)
    if build is None or (build.user_id != user.id and not has_permission(user, "builds.review")):
        raise HTTPException(404, t("errors.build_not_found"))
    return build


@router.get("/api/builds/{build_id}", response_model=BuildOut)
def get_build(build_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_out(_get_build(db, build_id, user))


@router.delete("/api/builds/{build_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_build(build_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    build = _get_build(db, build_id, user)
    if build.user_id != user.id:
        raise HTTPException(403, t("errors.build_owner_only"))
    db.delete(build)
    db.commit()
