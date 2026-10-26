"""TOTP multi-factor authentication helpers (RFC 6238, works with Google/Microsoft Authenticator).

- Secrets are encrypted at rest with Fernet (key from MFA_ENCRYPTION_KEY).
- A secret is shown only once, during enrollment, and never logged.
- Codes are accepted within +/- 1 time step (30 s) and cannot be reused.
- Failed attempts are counted; after too many the account's MFA is locked briefly.
- Recovery codes are stored only as SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import io
import secrets
import time
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from config import settings
from models import User

ISSUER = "CloudPay Shield"
_fernet = Fernet(settings.mfa_key)


def encrypt_secret(secret: str) -> str:
    return _fernet.encrypt(secret.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().replace("-", "").encode()).hexdigest()


def new_recovery_codes(n: int = 8) -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(n)]
    return codes, [_hash_code(c) for c in codes]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ensure_not_locked(user: User) -> None:
    locked = _as_utc(user.mfa_locked_until)
    if locked and locked > _now():
        seconds = int((locked - _now()).total_seconds())
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many MFA attempts. Try again in {seconds} seconds.")


def register_failure(user: User) -> None:
    user.mfa_failed_attempts = (user.mfa_failed_attempts or 0) + 1
    if user.mfa_failed_attempts >= settings.max_mfa_failures:
        user.mfa_locked_until = _now() + timedelta(minutes=settings.mfa_lock_minutes)
        user.mfa_failed_attempts = 0


def verify_totp(secret: str, code: str, user: User) -> bool:
    """Verify a 6-digit code, rejecting replay of an already used time step."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    totp = pyotp.TOTP(secret)
    current_step = int(time.time()) // 30
    for offset in (-1, 0, 1):
        step = current_step + offset
        if secrets.compare_digest(totp.at(step * 30), code):
            if user.mfa_last_used_step is not None and step <= user.mfa_last_used_step:
                return False  # replayed code
            user.mfa_last_used_step = step
            return True
    return False


def verify_user_code(user: User, code: str, allow_recovery: bool = True) -> str | None:
    """Check a TOTP or recovery code. Returns 'totp', 'recovery' or None (wrong code).

    Raises 429 when locked. On None the failure counter was increased; the caller
    must commit the session and then raise 401.
    """
    ensure_not_locked(user)
    secret = decrypt_secret(user.mfa_secret_enc)
    if secret and verify_totp(secret, code, user):
        user.mfa_failed_attempts = 0
        return "totp"
    if allow_recovery and code and len(code.strip()) >= 8:
        hashed = _hash_code(code)
        remaining = list(user.recovery_code_hashes or [])
        if hashed in remaining:
            remaining.remove(hashed)
            user.recovery_code_hashes = remaining
            user.mfa_failed_attempts = 0
            return "recovery"
    register_failure(user)
    return None
