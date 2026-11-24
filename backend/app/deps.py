"""Shared dependencies: current user and role checks."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import t
from app.models import User
from app.permissions import has_permission
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """User from the token, or None if there is no token (guest)."""
    if creds is None:
        return None
    user = db.get(User, decode_token(creds.credentials))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.user_not_found"))
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.account_blocked"))
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, t("errors.auth_required"))
    return user


def require_permission(permission: str):
    """Allows only users whose role has the permission (see app/permissions.py).

    Example: user: User = Depends(require_permission("orders.manage"))
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.forbidden"))
        return user

    return dependency
