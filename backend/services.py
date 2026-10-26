"""Database-aware helpers: build risk contexts, serialise requests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import Employee, SalaryChangeRequest, SalaryHistory
from risk_engine import HistoryPoint, RiskContext, assess


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_context(
    db: Session,
    employee: Employee,
    proposed_salary,
    reason: str | None,
    submitter_role: str,
    base_version: int | None,
    exclude_request_id: int | None = None,
) -> RiskContext:
    policy = settings.risk
    pending_q = select(SalaryChangeRequest).where(
        SalaryChangeRequest.employee_id == employee.id, SalaryChangeRequest.status == "pending"
    )
    if exclude_request_id is not None:
        pending_q = pending_q.where(SalaryChangeRequest.id != exclude_request_id)
    pending = db.execute(pending_q).scalars().all()

    window_start = datetime.now(timezone.utc) - timedelta(days=policy.repeated_window_days)
    unresolved_recent = [p for p in pending if (_as_utc(p.created_at) or window_start) >= window_start]

    # Salary history. Rows for this employee, its department and the organisation.
    rows = db.execute(select(SalaryHistory, Employee.department).join(Employee)).all()
    employee_hist = [HistoryPoint(h.pct_change, h.source) for h, _ in rows if h.employee_id == employee.id]
    dept_hist = [HistoryPoint(h.pct_change, h.source) for h, dept in rows if dept == employee.department]
    global_hist = [HistoryPoint(h.pct_change, h.source) for h, _ in rows]

    return RiskContext(
        current_salary=employee.current_salary,
        proposed_salary=proposed_salary,
        reason=reason,
        submitter_role=submitter_role,
        base_version=base_version,
        current_version=employee.salary_version,
        other_pending_for_employee=len(pending),
        same_amount_pending=any(p.proposed_salary == proposed_salary for p in pending),
        unresolved_recent_for_employee=len(unresolved_recent) + (1 if exclude_request_id is None else 0),
        employee_history=employee_hist,
        department_history=dept_hist,
        global_history=global_hist,
        department=employee.department,
    )


def assess_for_employee(db: Session, employee: Employee, proposed_salary, reason, submitter_role, base_version, exclude_request_id=None) -> dict:
    ctx = build_context(db, employee, proposed_salary, reason, submitter_role, base_version, exclude_request_id)
    return assess(ctx)


def serialize_request(req: SalaryChangeRequest, include_risk: bool = True, viewer_role: str = "hr") -> dict:
    data = {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": req.employee.full_name if req.employee else None,
        "employee_code": req.employee.employee_code if req.employee else None,
        "department": req.employee.department if req.employee else None,
        "current_salary": req.current_salary,
        "proposed_salary": req.proposed_salary,
        "pct_change": req.pct_change,
        "reason": req.reason,
        "status": req.status,
        "source": req.source,
        "base_salary_version": req.base_salary_version,
        "current_salary_version": req.employee.salary_version if req.employee else None,
        "is_stale": bool(req.employee and req.status == "pending" and req.employee.salary_version != req.base_salary_version),
        "risk_score": req.risk_score,
        "risk_level": req.risk_level,
        "manual_review_required": req.manual_review_required,
        "requested_by": req.requested_by.username if req.requested_by else None,
        "requested_by_id": req.requested_by_id,
        "created_at": _as_utc(req.created_at).isoformat() if req.created_at else None,
        "decided_by": req.decided_by.username if req.decided_by else None,
        "decision_reason": req.decision_reason,
        "decided_at": _as_utc(req.decided_at).isoformat() if req.decided_at else None,
    }
    if include_risk:
        data["risk_assessment"] = req.risk_assessment
    if viewer_role == "employee":
        # Employees see the status of their own requests, not reviewer details or risk internals.
        for key in ("requested_by", "requested_by_id", "decided_by", "risk_assessment", "risk_score", "risk_level"):
            data.pop(key, None)
    return data
