"""Employees, salary-change requests, risk assessment and manager decisions."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import mfa
from audit import audit_lock, record_event
from config import settings
from database import get_db
from models import Employee, SalaryChangeRequest, SalaryHistory, User
from notifications import notify_roles, notify_users
from risk_engine import percentage_change, policy_description
from schemas import DecisionIn, RiskPreviewIn, SalaryChangeIn
from security import CurrentUser, get_current_user, require_roles
from services import assess_for_employee, serialize_request

router = APIRouter(tags=["payroll"])


SALARY_ROLES = ("hr", "manager")          # may see salary amounts of other people
DIRECTORY_ROLES = ("hr", "manager", "auditor", "admin")  # may see the employee directory


def _employee_dict(e: Employee, show_salary: bool = True) -> dict:
    return {
        "id": e.id, "employee_code": e.employee_code, "full_name": e.full_name, "department": e.department,
        "job_title": e.job_title, "current_salary": e.current_salary if show_salary else None,
        "salary_visible": show_salary, "salary_version": e.salary_version,
        "is_demo_seed": e.is_demo_seed, "currency": "PKR",
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _open_requests(db: Session, employee_id: int) -> list[dict]:
    rows = db.execute(select(SalaryChangeRequest).where(SalaryChangeRequest.employee_id == employee_id,
                                                         SalaryChangeRequest.status == "pending")
                      .order_by(SalaryChangeRequest.created_at.desc())).scalars().all()
    return [{"id": r.id, "proposed_salary": r.proposed_salary, "pct_change": r.pct_change, "risk_level": r.risk_level,
             "requested_by": r.requested_by.username if r.requested_by else None,
             "created_at": serialize_request(r, include_risk=False)["created_at"]} for r in rows]


@router.get("/salary/me")
def my_salary(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.user.employee_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Your account is not linked to an employee payroll record yet.")
    emp = db.get(Employee, current.user.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll record not found.")
    history = db.execute(
        select(SalaryHistory).where(SalaryHistory.employee_id == emp.id).order_by(SalaryHistory.effective_at)
    ).scalars().all()
    return {
        **_employee_dict(emp),
        "history": [
            {"old_salary": h.old_salary, "new_salary": h.new_salary, "pct_change": h.pct_change,
             "source": h.source, "effective_at": h.effective_at.isoformat()}
            for h in history
        ],
    }


@router.get("/employees")
def list_employees(
    search: str | None = Query(default=None, max_length=80),
    department: str | None = Query(default=None, max_length=80),
    current: CurrentUser = Depends(require_roles(*DIRECTORY_ROLES)),
    db: Session = Depends(get_db),
):
    q = select(Employee).order_by(Employee.full_name)
    if department:
        q = q.where(Employee.department == department)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(Employee.full_name.ilike(like) | Employee.employee_code.ilike(like) | Employee.job_title.ilike(like))
    show = current.role in SALARY_ROLES
    return [_employee_dict(e, show) for e in db.execute(q).scalars().all()]


@router.get("/employees/{employee_id}")
def employee_detail(
    employee_id: int,
    current: CurrentUser = Depends(require_roles(*DIRECTORY_ROLES)),
    db: Session = Depends(get_db),
):
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    show = current.role in SALARY_ROLES
    history = db.execute(select(SalaryHistory).where(SalaryHistory.employee_id == emp.id)
                         .order_by(SalaryHistory.effective_at.desc())).scalars().all()
    requests = db.execute(select(SalaryChangeRequest).where(SalaryChangeRequest.employee_id == emp.id)
                          .order_by(SalaryChangeRequest.created_at.desc())).scalars().all()
    linked = db.execute(select(User).where(User.employee_id == emp.id)).scalar_one_or_none()
    data = _employee_dict(emp, show)
    data["history"] = [
        {"old_salary": h.old_salary if show else None, "new_salary": h.new_salary if show else None,
         "pct_change": h.pct_change, "source": h.source, "request_id": h.request_id,
         "effective_at": h.effective_at.isoformat() if h.effective_at else None}
        for h in history
    ]
    data["requests"] = [
        {k: v for k, v in serialize_request(r, include_risk=False).items()
         if show or k not in ("current_salary", "proposed_salary")}
        for r in requests
    ]
    data["open_requests"] = len([r for r in requests if r.status == "pending"])
    data["linked_username"] = linked.username if linked and current.role in ("hr", "admin") else None
    data["has_linked_account"] = linked is not None
    return data


@router.get("/risk/policy")
def risk_policy(current: CurrentUser = Depends(get_current_user)):
    return policy_description()


@router.post("/risk/assess")
def risk_preview(
    body: RiskPreviewIn,
    current: CurrentUser = Depends(require_roles("hr", "manager")),
    db: Session = Depends(get_db),
):
    """Preview a risk assessment without saving anything."""
    emp = db.get(Employee, body.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    result = assess_for_employee(db, emp, body.proposed_salary, body.reason, "hr", emp.salary_version)
    # Shown as a duplicate-request warning in the form before anything is submitted.
    result["open_requests"] = _open_requests(db, emp.id)
    return result


@router.post("/salary-change-requests", status_code=status.HTTP_201_CREATED)
def create_request(
    body: SalaryChangeIn,
    current: CurrentUser = Depends(require_roles("hr")),
    db: Session = Depends(get_db),
):
    with audit_lock:
        emp = db.get(Employee, body.employee_id)
        if emp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
        if body.expected_salary_version != emp.salary_version:
            record_event(db, actor=current.username, actor_role=current.role, action="salary_request_create",
                         outcome="conflict", target_type="employee", target_id=emp.id,
                         details={"expected_version": body.expected_salary_version, "current_version": emp.salary_version})
            db.commit()
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"The salary changed since you loaded it (version {body.expected_salary_version} -> "
                                f"{emp.salary_version}). Refresh and review the current salary before submitting.")

        # Risk assessment happens BEFORE anything is stored, and never changes the salary.
        assessment = assess_for_employee(db, emp, body.proposed_salary, body.reason, current.role, emp.salary_version)
        req = SalaryChangeRequest(
            employee_id=emp.id, requested_by_id=current.id, current_salary=emp.current_salary,
            proposed_salary=body.proposed_salary, pct_change=percentage_change(emp.current_salary, body.proposed_salary),
            reason=body.reason, base_salary_version=emp.salary_version, status="pending", source="manual",
            risk_score=assessment["score"], risk_level=assessment["level"],
            manual_review_required=assessment["manual_review_required"], risk_assessment=assessment,
        )
        db.add(req)
        db.flush()
        record_event(db, actor=current.username, actor_role=current.role, action="salary_request_create",
                     outcome="success", target_type="salary_change_request", target_id=req.id,
                     details={"employee_id": emp.id, "pct_change": req.pct_change})
        record_event(db, actor="risk-engine", actor_role="system", action="risk_assessment", outcome=assessment["level"],
                     target_type="salary_change_request", target_id=req.id,
                     details={"score": assessment["score"], "indicators": [i["code"] for i in assessment["indicators"]],
                              "policy_version": assessment["policy_version"]})
        pct = f"{req.pct_change:+.2f}%" if req.pct_change is not None else "n/a"
        notify_roles(db, ["manager"], kind="request_submitted",
                     severity="critical" if assessment["level"] == "Critical" else
                     "warning" if assessment["level"] == "High" else "info",
                     title=f"Review needed: {emp.full_name} {pct} ({assessment['level']} risk)",
                     body=f"Submitted by {current.username}. Reason: {body.reason[:120]}",
                     link=f"#/requests/{req.id}", exclude=current.id)
        if assessment["level"] in ("High", "Critical"):
            notify_roles(db, ["auditor"], kind="high_risk", severity="warning",
                         title=f"{assessment['level']} risk salary change flagged for {emp.full_name}",
                         body=f"Score {assessment['score']}/100. Flagged for review, not a fraud finding.",
                         link=f"#/anomalies/{req.id}")
        db.commit()
        db.refresh(req)
        return serialize_request(req)


@router.get("/salary-change-requests")
def list_requests(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(pending|approved|rejected)$"),
    risk_level: str | None = Query(default=None, pattern="^(Low|Medium|High|Critical)$"),
    search: str | None = Query(default=None, max_length=80),
    employee_id: int | None = Query(default=None, gt=0),
    mine: bool = False,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(SalaryChangeRequest).join(Employee).order_by(SalaryChangeRequest.created_at.desc())
    if employee_id:
        q = q.where(SalaryChangeRequest.employee_id == employee_id)
    if mine:
        q = q.where(SalaryChangeRequest.requested_by_id == current.id)
    if current.role == "employee":
        if current.user.employee_id is None:
            return []
        q = q.where(SalaryChangeRequest.employee_id == current.user.employee_id)
    elif current.role not in ("hr", "manager", "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted.")
    if status_filter:
        q = q.where(SalaryChangeRequest.status == status_filter)
    if risk_level and current.role != "employee":
        q = q.where(SalaryChangeRequest.risk_level == risk_level)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(Employee.full_name.ilike(like) | Employee.employee_code.ilike(like) | Employee.department.ilike(like))
    rows = db.execute(q).scalars().all()
    return [serialize_request(r, include_risk=True, viewer_role=current.role) for r in rows]


@router.get("/salary-change-requests/{request_id}")
def get_request(request_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    req = db.get(SalaryChangeRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    if current.role == "employee":
        if req.employee_id != current.user.employee_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    elif current.role not in ("hr", "manager", "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted.")
    data = serialize_request(req, viewer_role=current.role)
    if current.role != "employee" and req.status == "pending":
        # Live re-check so reviewers see the situation as it is now (e.g. newly stale).
        data["live_assessment"] = assess_for_employee(
            db, req.employee, req.proposed_salary, req.reason, req.requested_by.role if req.requested_by else "hr",
            req.base_salary_version, exclude_request_id=req.id,
        )
    return data


@router.post("/salary-change-requests/{request_id}/decision")
def decide(
    request_id: int,
    body: DecisionIn,
    current: CurrentUser = Depends(require_roles("manager")),
    db: Session = Depends(get_db),
):
    def deny(code: int, message: str, why: str):
        record_event(db, actor=current.username, actor_role=current.role, action=f"salary_request_{body.decision}",
                     outcome="denied", target_type="salary_change_request", target_id=request_id, details={"why": why})
        db.commit()
        raise HTTPException(code, message)

    user = current.user
    # MFA enforcement for this privileged operation.
    if settings.require_mfa_for_decisions:
        if not user.mfa_enabled:
            deny(status.HTTP_403_FORBIDDEN, "MFA must be enabled on your account before you can approve or reject requests. "
                 "Open Security settings to enrol.", "mfa not enrolled")
        if not current.mfa_verified:
            if not body.mfa_code:
                deny(status.HTTP_403_FORBIDDEN, "This action needs MFA. Enter a current 6-digit code.", "mfa step-up required")
            method = mfa.verify_user_code(user, body.mfa_code)
            if method is None:
                deny(status.HTTP_401_UNAUTHORIZED, "Invalid verification code.", "mfa step-up failed")

    with audit_lock:
        req = db.get(SalaryChangeRequest, request_id)
        if req is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
        if req.requested_by_id == user.id:
            deny(status.HTTP_403_FORBIDDEN, "Separation of duties: you cannot decide on a request you submitted.", "self-approval")
        if req.status != "pending":
            deny(status.HTTP_409_CONFLICT, f"This request was already {req.status}.", "duplicate decision")
        if req.risk_level in ("High", "Critical") and len(body.reason) < 20:
            raise HTTPException(422, "High and Critical risk decisions need a detailed reason (at least 20 characters).")

        emp = db.get(Employee, req.employee_id)
        now = datetime.now(timezone.utc)
        new_status = "approved" if body.decision == "approve" else "rejected"

        if body.decision == "approve":
            if emp.salary_version != req.base_salary_version:
                deny(status.HTTP_409_CONFLICT,
                     f"Version conflict: the request is based on salary version {req.base_salary_version} but the current "
                     f"version is {emp.salary_version}. Reject it and ask HR to resubmit.", "stale salary version")
            # Optimistic concurrency: only update if the version is still the one we checked.
            result = db.execute(
                update(Employee)
                .where(Employee.id == emp.id, Employee.salary_version == req.base_salary_version)
                .values(current_salary=req.proposed_salary, salary_version=Employee.salary_version + 1, updated_at=now)
            )
            if result.rowcount != 1:
                db.rollback()
                raise HTTPException(status.HTTP_409_CONFLICT, "The salary changed during approval. Refresh and try again.")

        # Only one decision can win: the update requires status = pending.
        result = db.execute(
            update(SalaryChangeRequest)
            .where(SalaryChangeRequest.id == req.id, SalaryChangeRequest.status == "pending")
            .values(status=new_status, decided_by_id=user.id, decision_reason=body.reason, decided_at=now)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "This request was decided by someone else.")

        if body.decision == "approve":
            db.add(SalaryHistory(employee_id=emp.id, old_salary=req.current_salary, new_salary=req.proposed_salary,
                                 pct_change=req.pct_change or 0.0, source="approved_request", request_id=req.id,
                                 effective_at=now))
            record_event(db, actor=current.username, actor_role=current.role, action="salary_updated", outcome="success",
                         target_type="employee", target_id=emp.id,
                         details={"request_id": req.id, "new_version": req.base_salary_version + 1})
        record_event(db, actor=current.username, actor_role=current.role, action=f"salary_request_{body.decision}",
                     outcome="success", target_type="salary_change_request", target_id=req.id,
                     details={"risk_level": req.risk_level, "risk_score": req.risk_score})
        verb = "approved" if body.decision == "approve" else "rejected"
        notify_users(db, [req.requested_by_id], kind="decision", severity="success" if verb == "approved" else "warning",
                     title=f"Request #{req.id} for {emp.full_name} was {verb}",
                     body=f"{current.username}: {body.reason[:160]}", link=f"#/requests/{req.id}")
        linked = db.execute(select(User.id).where(User.employee_id == emp.id)).scalars().all()
        notify_users(db, linked, kind="decision", severity="info",
                     title=f"A salary change for you was {verb}", body="Open My salary to see the details.",
                     link="#/my-salary")
        # Salary update, history row, request status and audit events commit together or not at all.
        db.commit()
        db.expire_all()
        return serialize_request(db.get(SalaryChangeRequest, req.id))
