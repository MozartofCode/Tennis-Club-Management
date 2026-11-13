"""Password hashing, JWTs and role checks."""

import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Club, User
from app.timeutil import utcnow

bearer = HTTPBearer(auto_error=False)
STAFF_ROLES = ("owner", "staff")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def new_qr_token() -> str:
    return secrets.token_urlsafe(24)


def create_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "club_id": user.club_id,
        "exp": utcnow() + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from exc
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found")
    return user


def require_roles(*roles: str):
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this")
        return user

    return check


require_staff = require_roles(*STAFF_ROLES)
require_owner = require_roles("owner")


def current_club(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Club:
    if user.club_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No club linked to this account")
    club = db.get(Club, user.club_id)
    if club is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Club not found")
    return club
