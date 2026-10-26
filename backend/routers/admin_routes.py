"""Security administration: users, role assignment, access requests.

This is the authorised process for privileged roles:
  * Public sign-up always creates an *employee*.
  * A signed-in user may ask for HR / manager / auditor access with a justification.
  * Only a security administrator (role ``admin``) with an MFA-verified session can grant a role,
    and never to their own account. Every change is audited and the user is notified.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import mfa
from audit import audit_lock, record_event
from config import settings
from database import get_db
from models import PRIVILEGED_ROLES, ROLE_LABELS, ROLES, AccessRequest, Employee, User
from notifications import notify_roles, notify_users
from schemas import AccessDecisionIn, AccessRequestIn, AccountStatusIn, AdminReasonIn, LinkEmployeeIn, RoleChangeIn
from security import CurrentUser, get_current_user, require_roles

router = APIRouter(tags=["administration"])


def _as_utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt):
    dt = _as_utc(dt)
    return dt.isoformat() if dt else None


def admin_user_dict(u: User) -> dict:
    locked = _as_utc(u.login_locked_until)
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
        "role": u.role, "role_label": ROLE_LABELS.get(u.role, u.role), "is_active": u.is_active,
        "mfa_enabled": u.mfa_enabled, "created_at": _iso(u.created_at),
        "locked": bool(locked and locked > datetime.now(timezone.utc)),
        "employee_id": u.employee_id,
        "employee_code": u.employee.employee_code if u.employee else None,
        "employee_name": u.employee.full_name if u.employee else None,
    }


def access_request_dict(a: AccessRequest) -> dict:
    return {
        "id": a.id, "user_id": a.user_id, "username": a.user.username if a.user else None,
        "full_name": a.user.full_name if a.user else None, "current_role": a.user.role if a.user else None,
        "requested_role": a.requested_role, "requested_role_label": ROLE_LABELS.get(a.requested_role),
        "justification": a.justification, "status": a.status, "created_at": _iso(a.created_at),
        "decided_by": a.decided_by.username if a.decided_by else None, "decision_reason": a.decision_reason,
        "decided_at": _iso(a.decided_at),
    }


def _require_admin_mfa(db: Session, current: CurrentUser, code: str | None, action: str, target_id) -> None:
    """Admin actions need MFA enrolled AND (an MFA-verified session OR a fresh code)."""
    if not settings.require_mfa_for_admin:
        return
    user = current.user

    def deny(http_code, message, why):
        record_event(db, actor=current.username, actor_role=current.role, action=action, outcome="denied",
                     target_type="user", target_id=target_id, details={"why": why})
        db.commit()
        raise HTTPException(http_code, message)

    if not user.mfa_enabled:
        deny(status.HTTP_403_FORBIDDEN, "Enable MFA on your account (Security settings) before using admin actions.",
             "mfa not enrolled")
    if current.mfa_verified:
        return
    if not code:
        deny(status.HTTP_403_FORBIDDEN, "This admin action needs MFA. Enter a current 6-digit code.", "mfa step-up required")
    if mfa.verify_user_code(user, code) is None:
        deny(status.HTTP_401_UNAUTHORIZED, "Invalid verification code.", "mfa step-up failed")


def _target(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return u


# ------------------------------------------------------------------ users

@router.get("/admin/users")
def list_users(
    search: str | None = Query(default=None, max_length=80),
    role: str | None = Query(default=None, pattern="^(employee|hr|manager|auditor|admin)$"),
    current: CurrentUser = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    q = select(User).order_by(User.created_at.desc())
    if role:
        q = q.where(User.role == role)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(User.username.ilike(like) | User.full_name.ilike(like) | User.email.ilike(like))
    users = db.execute(q).scalars().all()
    counts = dict(db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all())
    return {
        "users": [admin_user_dict(u) for u in users],
        "role_counts": {r: counts.get(r, 0) for r in ROLES},
        "roles": [{"value": r, "label": ROLE_LABELS[r]} for r in ROLES],
    }


@router.post("/admin/users/{user_id}/role")
def change_role(user_id: int, body: RoleChangeIn, current: CurrentUser = Depends(require_roles("admin")),
                db: Session = Depends(get_db)):
    _require_admin_mfa(db, current, body.mfa_code, "role_change", user_id)
    with audit_lock:
        target = _target(db, user_id)
        if target.id == current.id:
            record_event(db, actor=current.username, actor_role=current.role, action="role_change", outcome="denied",
                         target_type="user", target_id=target.id, details={"why": "self role change"})
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot change your own role. Ask another administrator.")
        if target.role == body.role:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{target.username} already has the {body.role} role.")
        if target.role == "admin":
            remaining = db.execute(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True),
                                                                   User.id != target.id)).scalar_one()
            if remaining == 0:
                raise HTTPException(status.HTTP_409_CONFLICT, "At least one active administrator must remain.")
        old = target.role
        target.role = body.role
        # Close any open access requests for this user: the role decision has been made directly.
        for a in db.execute(select(AccessRequest).where(AccessRequest.user_id == target.id,
                                                        AccessRequest.status == "pending")).scalars():
            a.status = "approved" if a.requested_role == body.role else "rejected"
            a.decided_by_id, a.decided_at = current.id, datetime.now(timezone.utc)
            a.decision_reason = f"Closed by direct role change: {body.reason}"
        record_event(db, actor=current.username, actor_role=current.role, action="role_change", outcome="success",
                     target_type="user", target_id=target.id,
                     details={"username": target.username, "old_role": old, "new_role": body.role, "reason": body.reason[:200]})
        notify_users(db, [target.id], kind="role_change", severity="warning",
                     title=f"Your role changed to {ROLE_LABELS[body.role]}",
                     body=f"Changed by {current.username}: {body.reason[:200]}", link="#/security")
        db.commit()
        return admin_user_dict(target)


@router.post("/admin/users/{user_id}/link-employee")
def link_employee(user_id: int, body: LinkEmployeeIn, current: CurrentUser = Depends(require_roles("admin")),
                  db: Session = Depends(get_db)):
    target = _target(db, user_id)
    emp = None
    if body.employee_id is not None:
        emp = db.get(Employee, body.employee_id)
        if emp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
        taken = db.execute(select(User).where(User.employee_id == emp.id, User.id != target.id)).scalar_one_or_none()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{emp.employee_code} is already linked to {taken.username}.")
    old = target.employee_id
    target.employee_id = emp.id if emp else None
    record_event(db, actor=current.username, actor_role=current.role, action="employee_link", outcome="success",
                 target_type="user", target_id=target.id,
                 details={"old_employee_id": old, "new_employee_id": target.employee_id, "reason": body.reason[:200]})
    if emp:
        notify_users(db, [target.id], kind="security", title="Your account is linked to your payroll record",
                     body=f"You can now see your salary ({emp.employee_code}).", link="#/my-salary", severity="success")
    db.commit()
    db.refresh(target)
    return admin_user_dict(target)


@router.post("/admin/users/{user_id}/unlock")
def unlock_user(user_id: int, body: AdminReasonIn, current: CurrentUser = Depends(require_roles("admin")),
                db: Session = Depends(get_db)):
    target = _target(db, user_id)
    target.login_locked_until = None
    target.failed_login_attempts = 0
    target.mfa_locked_until = None
    target.mfa_failed_attempts = 0
    record_event(db, actor=current.username, actor_role=current.role, action="account_unlock", outcome="success",
                 target_type="user", target_id=target.id, details={"reason": body.reason[:200]})
    db.commit()
    return admin_user_dict(target)


@router.post("/admin/users/{user_id}/reset-mfa")
def reset_mfa(user_id: int, body: AdminReasonIn, current: CurrentUser = Depends(require_roles("admin")),
              db: Session = Depends(get_db)):
    _require_admin_mfa(db, current, body.mfa_code, "mfa_reset", user_id)
    target = _target(db, user_id)
    if target.id == current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot reset your own MFA. Ask another administrator.")
    target.mfa_enabled = False
    target.mfa_secret_enc = None
    target.mfa_pending_secret_enc = None
    target.recovery_code_hashes = []
    target.mfa_failed_attempts = 0
    target.mfa_locked_until = None
    record_event(db, actor=current.username, actor_role=current.role, action="mfa_reset", outcome="success",
                 target_type="user", target_id=target.id, details={"reason": body.reason[:200]})
    notify_users(db, [target.id], kind="security", severity="warning", title="Your MFA was reset by an administrator",
                 body="Set up your authenticator app again from Security settings.", link="#/security")
    db.commit()
    return admin_user_dict(target)


@router.post("/admin/users/{user_id}/status")
def set_status(user_id: int, body: AccountStatusIn, current: CurrentUser = Depends(require_roles("admin")),
               db: Session = Depends(get_db)):
    _require_admin_mfa(db, current, body.mfa_code, "account_status", user_id)
    target = _target(db, user_id)
    if target.id == current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot disable your own account.")
    if not body.is_active and target.role == "admin":
        remaining = db.execute(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True),
                                                               User.id != target.id)).scalar_one()
        if remaining == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "At least one active administrator must remain.")
    target.is_active = body.is_active
    record_event(db, actor=current.username, actor_role=current.role,
                 action="account_enable" if body.is_active else "account_disable", outcome="success",
                 target_type="user", target_id=target.id, details={"reason": body.reason[:200]})
    db.commit()
    return admin_user_dict(target)


# ------------------------------------------------------------------ access requests

@router.post("/access-requests", status_code=status.HTTP_201_CREATED)
def create_access_request(body: AccessRequestIn, current: CurrentUser = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    if current.role == body.requested_role:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have that role.")
    open_req = db.execute(select(AccessRequest).where(AccessRequest.user_id == current.id,
                                                      AccessRequest.status == "pending")).scalar_one_or_none()
    if open_req:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a pending access request.")
    a = AccessRequest(user_id=current.id, requested_role=body.requested_role, justification=body.justification)
    db.add(a)
    db.flush()
    record_event(db, actor=current.username, actor_role=current.role, action="access_request_create", outcome="success",
                 target_type="access_request", target_id=a.id, details={"requested_role": body.requested_role})
    notify_roles(db, ["admin"], kind="access_request", severity="warning",
                 title=f"{current.username} requests {ROLE_LABELS[body.requested_role]} access",
                 body=body.justification[:200], link="#/admin")
    db.commit()
    db.refresh(a)
    return access_request_dict(a)


@router.get("/access-requests/mine")
def my_access_requests(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AccessRequest).where(AccessRequest.user_id == current.id)
                      .order_by(AccessRequest.created_at.desc())).scalars().all()
    return [access_request_dict(a) for a in rows]


@router.post("/access-requests/{request_id}/cancel")
def cancel_access_request(request_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(AccessRequest, request_id)
    if a is None or a.user_id != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access request not found.")
    if a.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Request already {a.status}.")
    a.status = "cancelled"
    record_event(db, actor=current.username, actor_role=current.role, action="access_request_cancel", outcome="success",
                 target_type="access_request", target_id=a.id)
    db.commit()
    return access_request_dict(a)


@router.get("/admin/access-requests")
def list_access_requests(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected|cancelled)$"),
    current: CurrentUser = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    q = select(AccessRequest).order_by(AccessRequest.created_at.desc())
    if status_filter:
        q = q.where(AccessRequest.status == status_filter)
    return [access_request_dict(a) for a in db.execute(q).scalars().all()]


@router.post("/admin/access-requests/{request_id}/decision")
def decide_access_request(request_id: int, body: AccessDecisionIn, current: CurrentUser = Depends(require_roles("admin")),
                          db: Session = Depends(get_db)):
    _require_admin_mfa(db, current, body.mfa_code, f"access_request_{body.decision}", request_id)
    with audit_lock:
        a = db.get(AccessRequest, request_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Access request not found.")
        if a.user_id == current.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot decide your own access request.")
        if a.status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {a.status}.")
        if a.requested_role not in PRIVILEGED_ROLES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role.")
        now = datetime.now(timezone.utc)
        a.status = "approved" if body.decision == "approve" else "rejected"
        a.decided_by_id, a.decision_reason, a.decided_at = current.id, body.reason, now
        target = a.user
        old_role = target.role
        if body.decision == "approve":
            target.role = a.requested_role
        record_event(db, actor=current.username, actor_role=current.role, action=f"access_request_{body.decision}",
                     outcome="success", target_type="access_request", target_id=a.id,
                     details={"username": target.username, "old_role": old_role, "requested_role": a.requested_role,
                              "reason": body.reason[:200]})
        notify_users(db, [target.id], kind="role_change", severity="success" if body.decision == "approve" else "warning",
                     title=(f"Access approved: you are now {ROLE_LABELS[a.requested_role]}" if body.decision == "approve"
                            else f"Access request for {ROLE_LABELS[a.requested_role]} was declined"),
                     body=body.reason[:200], link="#/security")
        db.commit()
        db.refresh(a)
        return access_request_dict(a)
