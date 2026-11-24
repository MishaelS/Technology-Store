from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.i18n import t
from app.models import User
from app.schemas import LoginIn, ProfileUpdate, RegisterIn, TokenOut, UserOut
from app.security import create_token, hash_password, verify_password
from app.services.bonus import add_bonus

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Checked when the email is unknown, so a wrong email takes as long as a wrong password
# and nobody can find out which emails are registered by measuring response time.
_DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    """Register a client. Credits the welcome bonus and returns a token."""
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, t("errors.email_taken"))
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name.strip(),
        phone=data.phone,
        role="client",
        bonus_balance=0,
    )
    db.add(user)
    db.flush()  # so that user.id is assigned
    add_bonus(db, user, settings.welcome_bonus, t("bonus.reason.welcome"))
    try:
        db.commit()
    except IntegrityError:  # the same email registered by a parallel request
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, t("errors.email_taken"))
    return TokenOut(token=create_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    password_ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.invalid_credentials"))
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.account_blocked"))
    return TokenOut(token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(data: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return user
