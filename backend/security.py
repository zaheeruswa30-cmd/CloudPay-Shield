"""Password hashing, JWT tokens, and role/MFA dependencies.

Passwords: PBKDF2-HMAC-SHA256 (Python standard library) with a random 16-byte salt
and a high iteration count. No third-party hashing library is needed, which avoids
compatibility problems on new Python versions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from audit import record_event
from config import settings
from database import get_db
from models import RevokedToken, User

bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- passwords
def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or settings.password_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_b64, digest_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Used to keep login timing similar for unknown usernames.
_DUMMY_HASH = hash_password("not-a-real-password", iterations=1000)


def dummy_verify() -> None:
    verify_password("x", _DUMMY_HASH)


# ---------------------------------------------------------------- tokens
def create_token(user: User, *, token_type: str = "access", mfa: bool = False, minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    minutes = minutes or (settings.mfa_pending_minutes if token_type == "mfa_pending" else settings.access_token_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": token_type,
        "mfa": mfa,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "jti", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token.")
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type.")
    return payload


class CurrentUser:
    """The authenticated user plus facts about the current session."""

    def __init__(self, user: User, payload: dict):
        self.user = user
        self.payload = payload
        self.mfa_verified = bool(payload.get("mfa"))

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def username(self) -> str:
        return self.user.username


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Not authenticated.", headers={"WWW-Authenticate": "Bearer"}
        )
    payload = decode_token(creds.credentials, "access")
    if db.get(RevokedToken, payload["jti"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been signed out.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled.")
    return CurrentUser(user, payload)


def require_roles(*roles: str):
    """Dependency factory: allow only the given roles; audit denied attempts (403)."""

    def checker(
        request: Request,
        current: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> CurrentUser:
        if current.role not in roles:
            record_event(
                db,
                actor=current.username,
                actor_role=current.role,
                action="access_denied",
                target_type="endpoint",
                target_id=f"{request.method} {request.url.path}"[:40],
                outcome="denied",
                details={"required_roles": list(roles)},
            )
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role is not permitted to perform this action.")
        return current

    return checker


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
