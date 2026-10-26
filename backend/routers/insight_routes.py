"""Audit log, chain verification, analytics and ETL preview."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from audit import audit_lock, record_event, verify_chain
from database import get_db
from etl import validate_csv
from models import AuditEvent, Employee, ImportBatch, SalaryChangeRequest, SalaryHistory
from notifications import notify_roles
from risk_engine import percentage_change
from security import CurrentUser, require_roles
from services import assess_for_employee

router = APIRouter(tags=["insights"])
SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample_data" / "payroll_changes_sample.csv"


AUDIT_ROLES = ("auditor", "manager", "admin")
# Fields hidden from non-auditor viewers (managers and admins see what happened, auditors see everything).
_RESTRICTED_DETAIL_KEYS = {"ip"}


def _related_request(e: AuditEvent) -> int | None:
    if e.target_type == "salary_change_request" and str(e.target_id).isdigit():
        return int(e.target_id)
    rid = (e.details or {}).get("request_id")
    return rid if isinstance(rid, int) else None


def _event_dict(e: AuditEvent, viewer_role: str = "auditor", integrity: str | None = None) -> dict:
    details = dict(e.details or {})
    if viewer_role != "auditor":
        details = {k: v for k, v in details.items() if k not in _RESTRICTED_DETAIL_KEYS}
    return {
        "id": e.id, "timestamp": e.timestamp, "actor": e.actor, "actor_role": e.actor_role, "action": e.action,
        "target_type": e.target_type, "target_id": e.target_id, "outcome": e.outcome, "details": details,
        "related_request_id": _related_request(e), "integrity": integrity,
        "prev_hash": e.prev_hash, "hash": e.hash,
    }


@router.get("/audit-events")
def audit_events(
    limit: int = Query(default=200, ge=1, le=2000),
    action: str | None = Query(default=None, max_length=60),
    outcome: str | None = Query(default=None, max_length=20),
    actor: str | None = Query(default=None, max_length=60),
    actor_role: str | None = Query(default=None, max_length=20),
    search: str | None = Query(default=None, max_length=80),
    request_id: int | None = Query(default=None, gt=0),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current: CurrentUser = Depends(require_roles(*AUDIT_ROLES)),
    db: Session = Depends(get_db),
):
    """Searchable audit log. Each event carries an integrity status from a fresh chain check:
    verified (hash recomputed and linked), broken (first failing event) or unverifiable (after a break)."""
    q = select(AuditEvent).order_by(AuditEvent.id.desc())
    if action:
        q = q.where(AuditEvent.action == action)
    if outcome:
        q = q.where(AuditEvent.outcome == outcome)
    if actor:
        q = q.where(AuditEvent.actor == actor)
    if actor_role:
        q = q.where(AuditEvent.actor_role == actor_role)
    if date_from:
        q = q.where(AuditEvent.timestamp >= date_from)
    if date_to:
        q = q.where(AuditEvent.timestamp < date_to + "T99")  # inclusive of the whole end day (ISO strings sort)
    if request_id:
        q = q.where((AuditEvent.target_type == "salary_change_request") & (AuditEvent.target_id == str(request_id)))
    if search:
        like = f"%{search.lower()}%"
        q = q.where(AuditEvent.actor.ilike(like) | AuditEvent.action.ilike(like) | AuditEvent.target_type.ilike(like)
                    | AuditEvent.target_id.ilike(like) | AuditEvent.outcome.ilike(like))
    rows = db.execute(q.limit(limit)).scalars().all()

    chain = verify_chain(db)  # read-only; does not add an event

    def status_for(event_id: int) -> str:
        broken = chain["broken_at_id"]
        if broken is None:
            return "verified"
        return "verified" if event_id < broken else "broken" if event_id == broken else "unverifiable"

    actions = db.execute(select(AuditEvent.action).distinct().order_by(AuditEvent.action)).scalars().all()
    return {
        "events": [_event_dict(e, current.role, status_for(e.id)) for e in rows],
        "chain": {k: chain.get(k) for k in ("valid", "checked", "total", "broken_at_id", "problem", "latest_hash")},
        "actions": actions,
        "detail_scope": "full" if current.role == "auditor" else "restricted (network details hidden)",
    }


@router.get("/audit/verify")
def audit_verify(current: CurrentUser = Depends(require_roles(*AUDIT_ROLES)), db: Session = Depends(get_db)):
    result = verify_chain(db)
    result["verified_at"] = datetime.now(timezone.utc).isoformat()
    result["limitation"] = ("The chain is stored in the same database. It detects modified, removed or reordered events, "
                            "but someone with full database access could rebuild the whole chain. Anchor the latest hash "
                            "externally for stronger guarantees.")
    record_event(db, actor=current.username, actor_role=current.role, action="audit_verify",
                 outcome="valid" if result["valid"] else "invalid", target_type="audit_chain",
                 target_id=str(result["total"]), details={"broken_at_id": result["broken_at_id"]})
    if not result["valid"]:
        notify_roles(db, ["auditor", "admin"], kind="security", severity="critical",
                     title="Audit chain verification FAILED",
                     body=f"First broken event #{result['broken_at_id']}: {result['problem']}", link="#/audit")
    db.commit()
    return result


@router.get("/analytics/summary")
def analytics_summary(current: CurrentUser = Depends(require_roles("hr", "manager", "auditor")), db: Session = Depends(get_db)):
    """Aggregates computed from live database rows on every call (no cached or hardcoded figures)."""
    reqs = db.execute(select(SalaryChangeRequest)).scalars().all()
    status_counts = Counter(r.status for r in reqs)
    risk_counts = Counter(r.risk_level for r in reqs)
    pending = [r for r in reqs if r.status == "pending"]
    indicator_counts: Counter = Counter()
    for r in reqs:
        for ind in (r.risk_assessment or {}).get("indicators", []):
            if ind.get("points", 0) > 0:
                indicator_counts[ind["title"]] += 1

    history = db.execute(
        select(SalaryHistory, Employee.full_name, Employee.department).join(Employee).order_by(SalaryHistory.effective_at)
    ).all()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    audit_24h = db.execute(select(func.count(AuditEvent.id)).where(AuditEvent.timestamp >= since)).scalar_one()
    denied_24h = db.execute(
        select(func.count(AuditEvent.id)).where(AuditEvent.timestamp >= since, AuditEvent.outcome.in_(["denied", "failure", "blocked"]))
    ).scalar_one()

    dept: dict[str, dict] = {}
    for r in reqs:
        d = dept.setdefault(r.employee.department, {"department": r.employee.department, "requests": 0, "high_or_critical": 0})
        d["requests"] += 1
        d["high_or_critical"] += 1 if r.risk_level in ("High", "Critical") else 0

    # Request activity for the last 14 days (submitted per day, and decisions per day).
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    activity = {d.isoformat(): {"date": d.isoformat(), "submitted": 0, "approved": 0, "rejected": 0} for d in days}
    for r in reqs:
        c = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        if c.date().isoformat() in activity:
            activity[c.date().isoformat()]["submitted"] += 1
        if r.decided_at is not None and r.status in ("approved", "rejected"):
            d = r.decided_at if r.decided_at.tzinfo else r.decided_at.replace(tzinfo=timezone.utc)
            if d.date().isoformat() in activity:
                activity[d.date().isoformat()][r.status] += 1

    return {
        "request_activity": list(activity.values()),
        "total_employees": db.execute(select(func.count(Employee.id))).scalar_one(),
        "total_requests": len(reqs),
        "status_counts": {s: status_counts.get(s, 0) for s in ("pending", "approved", "rejected")},
        "risk_counts": {lvl: risk_counts.get(lvl, 0) for lvl in ("Low", "Medium", "High", "Critical")},
        "pending_high_risk": sum(1 for r in pending if r.risk_level == "High"),
        "pending_critical": sum(1 for r in pending if r.risk_level == "Critical"),
        "pending_avg_risk": round(sum(r.risk_score for r in pending) / len(pending), 1) if pending else 0,
        "pending_max_risk": max((r.risk_score for r in pending), default=0),
        "stale_pending": sum(1 for r in pending if r.employee.salary_version != r.base_salary_version),
        "top_indicators": [{"indicator": k, "count": v} for k, v in indicator_counts.most_common(8)],
        "departments": sorted(dept.values(), key=lambda d: -d["requests"]),
        "salary_change_history": [
            {"date": h.effective_at.date().isoformat(), "employee": name, "department": department,
             "pct_change": h.pct_change, "source": h.source}
            for h, name, department in history
        ],
        "history_sources": dict(Counter(h.source for h, _, _ in history)),
        "audit_events_24h": audit_24h,
        "security_events_24h": denied_24h,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------- ETL
from schemas import CsvPreviewIn  # noqa: E402


@router.get("/etl/sample")
def etl_sample(current: CurrentUser = Depends(require_roles("hr"))):
    if not SAMPLE_CSV.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample file missing.")
    return {"filename": SAMPLE_CSV.name, "csv_text": SAMPLE_CSV.read_text(encoding="utf-8"),
            "note": "Fictional demonstration data only."}


@router.post("/etl/preview")
def etl_preview(body: CsvPreviewIn, current: CurrentUser = Depends(require_roles("hr")), db: Session = Depends(get_db)):
    result = validate_csv(db, body.csv_text)
    batch = ImportBatch(uploaded_by_id=current.id, filename=body.filename, status="previewed",
                        summary=result["summary"], rows=result["rows"])
    db.add(batch)
    db.flush()
    record_event(db, actor=current.username, actor_role=current.role, action="etl_preview", outcome="success",
                 target_type="import_batch", target_id=batch.id,
                 details={k: result["summary"][k] for k in ("total_rows", "valid_rows", "invalid_rows", "suspicious_rows")})
    db.commit()
    return {"batch_id": batch.id, "status": batch.status, **result}


@router.post("/etl/batches/{batch_id}/submit")
def etl_submit(batch_id: int, current: CurrentUser = Depends(require_roles("hr")), db: Session = Depends(get_db)):
    """Turn valid staged rows into PENDING salary-change requests. Salaries are not changed."""
    with audit_lock:
        batch = db.get(ImportBatch, batch_id)
        if batch is None or batch.uploaded_by_id != current.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found.")
        if batch.status != "previewed":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Batch already {batch.status}.")
        created, skipped = [], []
        for row in batch.rows:
            if not row.get("submittable"):
                continue
            emp = db.get(Employee, row["employee_id"])
            if emp is None or emp.salary_version != row["salary_version"]:
                skipped.append({"row_number": row["row_number"], "why": "salary changed since preview"})
                continue
            assessment = assess_for_employee(db, emp, row["proposed_salary"], row["reason"], "hr", emp.salary_version)
            req = SalaryChangeRequest(
                employee_id=emp.id, requested_by_id=current.id, current_salary=emp.current_salary,
                proposed_salary=row["proposed_salary"], pct_change=percentage_change(emp.current_salary, row["proposed_salary"]),
                reason=row["reason"], base_salary_version=emp.salary_version, status="pending", source="csv_import",
                risk_score=assessment["score"], risk_level=assessment["level"],
                manual_review_required=True, risk_assessment=assessment,
            )
            db.add(req)
            db.flush()
            created.append(req.id)
            record_event(db, actor="risk-engine", actor_role="system", action="risk_assessment", outcome=assessment["level"],
                         target_type="salary_change_request", target_id=req.id,
                         details={"score": assessment["score"], "source": "csv_import"})
        batch.status = "submitted"
        if created:
            notify_roles(db, ["manager"], kind="request_submitted", severity="info",
                         title=f"{len(created)} imported salary change(s) need review",
                         body=f"CSV import {batch.filename} by {current.username}.", link="#/requests")
        record_event(db, actor=current.username, actor_role=current.role, action="etl_submit", outcome="success",
                     target_type="import_batch", target_id=batch.id,
                     details={"requests_created": len(created), "skipped": len(skipped)})
        db.commit()
        return {"batch_id": batch.id, "status": batch.status, "created_request_ids": created, "skipped": skipped,
                "detail": f"{len(created)} pending request(s) created for manager review. No salary was changed."}


@router.post("/etl/batches/{batch_id}/discard")
def etl_discard(batch_id: int, current: CurrentUser = Depends(require_roles("hr")), db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.uploaded_by_id != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch not found.")
    if batch.status != "previewed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Batch already {batch.status}.")
    batch.status = "discarded"
    record_event(db, actor=current.username, actor_role=current.role, action="etl_discard", outcome="success",
                 target_type="import_batch", target_id=batch.id)
    db.commit()
    return {"batch_id": batch.id, "status": batch.status}
