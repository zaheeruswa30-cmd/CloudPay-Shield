"""Authentication: login (+MFA step), logout, safe registration, profile, MFA enrollment."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import mfa
from audit import record_event
from config import settings
from database import get_db
from models import ROLE_LABELS, RevokedToken, User
from notifications import notify_users
from schemas import ChangePasswordIn, LoginIn, MfaCodeIn, MfaLoginIn, RegisterIn
from security import (
    CurrentUser, client_ip, create_token, decode_token, dummy_verify, get_current_user,
    hash_password, verify_password,
)

router = APIRouter(tags=["auth"])

# Simple in-memory per-IP limiter for failed logins (single process, resets on restart).
_ip_failures: dict[str, deque] = defaultdict(deque)
IP_WINDOW_SECONDS = 300
IP_MAX_FAILURES = 20


def _ip_limited(ip: str) -> bool:
    q = _ip_failures[ip]
    now = time.time()
    while q and now - q[0] > IP_WINDOW_SECONDS:
        q.popleft()
    return len(q) >= IP_MAX_FAILURES


def _as_utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def user_profile(user: User, mfa_verified: bool = False) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "employee_id": user.employee_id,
        "employee_code": user.employee.employee_code if user.employee else None,
        "created_at": _as_utc(user.created_at).isoformat() if user.created_at else None,
        "mfa_enabled": user.mfa_enabled,
        "mfa_verified_session": mfa_verified,
        "recovery_codes_remaining": len(user.recovery_code_hashes or []),
        "mfa_required_for_decisions": settings.require_mfa_for_decisions and user.role == "manager",
        "mfa_required_for_role": (settings.require_mfa_for_decisions and user.role == "manager")
                                 or (settings.require_mfa_for_admin and user.role == "admin"),
    }


def _token_response(user: User, mfa_verified: bool) -> dict:
    return {
        "access_token": create_token(user, mfa=mfa_verified),
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
        "mfa_required": False,
        "user": user_profile(user, mfa_verified),
    }


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if _ip_limited(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed sign-in attempts. Try again later.")

    username = body.username.strip().lower()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")

    if user is None:
        dummy_verify()
        _ip_failures[ip].append(time.time())
        record_event(db, actor=username[:60], actor_role="none", action="login", outcome="failure",
                     target_type="user", target_id=username[:40], details={"why": "unknown user", "ip": ip})
        db.commit()
        raise generic

    locked = _as_utc(user.login_locked_until)
    if locked and locked > datetime.now(timezone.utc):
        record_event(db, actor=user.username, actor_role=user.role, action="login", outcome="blocked",
                     target_type="user", target_id=user.id, details={"why": "account temporarily locked", "ip": ip})
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Account temporarily locked after failed attempts. Try again in a few minutes.")

    if not user.is_active or not verify_password(body.password, user.password_hash):
        _ip_failures[ip].append(time.time())
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.max_login_failures:
            user.login_locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_attempts = 0
        record_event(db, actor=user.username, actor_role=user.role, action="login", outcome="failure",
                     target_type="user", target_id=user.id, details={"why": "wrong password or inactive", "ip": ip})
        db.commit()
        raise generic

    user.failed_login_attempts = 0
    user.login_locked_until = None

    if user.mfa_enabled:
        record_event(db, actor=user.username, actor_role=user.role, action="login_password_ok", outcome="mfa_pending",
                     target_type="user", target_id=user.id, details={"ip": ip})
        db.commit()
        return {"mfa_required": True, "mfa_token": create_token(user, token_type="mfa_pending"), "token_type": "mfa_pending"}

    record_event(db, actor=user.username, actor_role=user.role, action="login", outcome="success",
                 target_type="user", target_id=user.id, details={"mfa": False, "ip": ip})
    db.commit()
    return _token_response(user, mfa_verified=False)


@router.post("/auth/mfa/login")
def mfa_login(body: MfaLoginIn, request: Request, db: Session = Depends(get_db)):
    payload = decode_token(body.mfa_token, "mfa_pending")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA sign-in is not available for this account.")
    method = mfa.verify_user_code(user, body.code)
    if method is None:
        record_event(db, actor=user.username, actor_role=user.role, action="mfa_verify", outcome="failure",
                     target_type="user", target_id=user.id, details={"stage": "login"})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code.")
    record_event(db, actor=user.username, actor_role=user.role, action="login", outcome="success",
                 target_type="user", target_id=user.id, details={"mfa": True, "method": method, "ip": client_ip(request)})
    db.commit()
    return _token_response(user, mfa_verified=True)


@router.post("/auth/logout")
def logout(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    exp = datetime.fromtimestamp(current.payload["exp"], tz=timezone.utc)
    if not db.get(RevokedToken, current.payload["jti"]):
        db.add(RevokedToken(jti=current.payload["jti"], expires_at=exp))
    record_event(db, actor=current.username, actor_role=current.role, action="logout", outcome="success",
                 target_type="user", target_id=current.id)
    db.commit()
    return {"detail": "Signed out."}


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if body.role and body.role.lower() != "employee":
        record_event(db, actor=body.username, actor_role="none", action="register", outcome="denied",
                     target_type="user", target_id=body.username,
                     details={"why": "attempted to self-assign privileged role", "requested_role": body.role[:20]})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Public sign-up creates employee accounts only. Privileged roles are assigned by an administrator.")
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken.")
    user = User(username=body.username, full_name=body.full_name, email=body.email,
                password_hash=hash_password(body.password), role="employee", employee_id=None)
    db.add(user)
    db.flush()
    record_event(db, actor=user.username, actor_role="employee", action="register", outcome="success",
                 target_type="user", target_id=user.id, details={"assigned_role": "employee", "ip": client_ip(request)})
    db.commit()
    return {"detail": "Account created. You can now sign in.", "user": user_profile(user)}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)):
    return user_profile(current.user, current.mfa_verified)


@router.post("/auth/mfa/setup")
def mfa_setup(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = current.user
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already enabled.")
    secret = mfa.new_secret()
    user.mfa_pending_secret_enc = mfa.encrypt_secret(secret)
    uri = mfa.provisioning_uri(secret, user.username)
    record_event(db, actor=user.username, actor_role=user.role, action="mfa_enroll_start", outcome="success",
                 target_type="user", target_id=user.id)
    db.commit()
    # The secret is returned once so it can be typed manually if QR scanning fails.
    return {"otpauth_uri": uri, "manual_entry_key": secret, "qr_svg": mfa.qr_svg(uri), "issuer": mfa.ISSUER}


@router.post("/auth/mfa/enable")
def mfa_enable(body: MfaCodeIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = current.user
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already enabled.")
    mfa.ensure_not_locked(user)
    secret = mfa.decrypt_secret(user.mfa_pending_secret_enc)
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start MFA setup first.")
    if not mfa.verify_totp(secret, body.code, user):
        mfa.register_failure(user)
        record_event(db, actor=user.username, actor_role=user.role, action="mfa_enroll_verify", outcome="failure",
                     target_type="user", target_id=user.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code. Check your device clock and try again.")
    codes, hashes = mfa.new_recovery_codes()
    user.mfa_secret_enc = user.mfa_pending_secret_enc
    user.mfa_pending_secret_enc = None
    user.mfa_enabled = True
    user.mfa_failed_attempts = 0
    user.recovery_code_hashes = hashes
    record_event(db, actor=user.username, actor_role=user.role, action="mfa_enabled", outcome="success",
                 target_type="user", target_id=user.id, details={"recovery_codes_issued": len(codes)})
    db.commit()
    resp = _token_response(user, mfa_verified=True)
    resp["recovery_codes"] = codes
    resp["detail"] = "MFA enabled. Save your recovery codes now; they will not be shown again."
    return resp


@router.post("/auth/mfa/disable")
def mfa_disable(body: MfaCodeIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = current.user
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA is not enabled.")
    if (user.role == "manager" and settings.require_mfa_for_decisions) or (user.role == "admin" and settings.require_mfa_for_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Your role must keep MFA enabled. If a device is lost, a security administrator can reset it.")
    method = mfa.verify_user_code(user, body.code)
    if method is None:
        record_event(db, actor=user.username, actor_role=user.role, action="mfa_disable", outcome="failure",
                     target_type="user", target_id=user.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code.")
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.recovery_code_hashes = []
    record_event(db, actor=user.username, actor_role=user.role, action="mfa_disabled", outcome="success",
                 target_type="user", target_id=user.id)
    db.commit()
    return _token_response(user, mfa_verified=False)


@router.post("/auth/change-password")
def change_password(body: ChangePasswordIn, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = current.user
    if not verify_password(body.current_password, user.password_hash):
        record_event(db, actor=user.username, actor_role=user.role, action="password_change", outcome="failure",
                     target_type="user", target_id=user.id, details={"why": "wrong current password"})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a password different from the current one.")
    user.password_hash = hash_password(body.new_password)
    # Sign out this session; the user signs in again with the new password.
    exp = datetime.fromtimestamp(current.payload["exp"], tz=timezone.utc)
    db.add(RevokedToken(jti=current.payload["jti"], expires_at=exp))
    record_event(db, actor=user.username, actor_role=user.role, action="password_change", outcome="success",
                 target_type="user", target_id=user.id)
    notify_users(db, [user.id], kind="security", severity="info", title="Your password was changed",
                 body="If this was not you, contact a security administrator.", link="#/security")
    db.commit()
    return {"detail": "Password changed. Please sign in again."}
