"""SQLAlchemy models for CloudPay Shield."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


ROLES = ("employee", "hr", "manager", "auditor", "admin")
PRIVILEGED_ROLES = ("hr", "manager", "auditor", "admin")
ROLE_LABELS = {
    "employee": "Employee", "hr": "HR officer", "manager": "Payroll manager",
    "auditor": "Auditor", "admin": "Security administrator",
}


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(80), index=True)
    job_title: Mapped[str] = mapped_column(String(120), default="")
    # Whole PKR. Integers avoid floating-point rounding problems for money.
    current_salary: Mapped[int] = mapped_column(Integer)
    salary_version: Mapped[int] = mapped_column(Integer, default=1)
    is_demo_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="employee")
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    mfa_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_last_used_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recovery_code_hashes: Mapped[list] = mapped_column(JSON, default=list)

    employee: Mapped[Employee | None] = relationship()


class SalaryHistory(Base):
    """Every applied salary change. source = 'approved_request' | 'seed_demo'."""

    __tablename__ = "salary_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    old_salary: Mapped[int] = mapped_column(Integer)
    new_salary: Mapped[int] = mapped_column(Integer)
    pct_change: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), default="approved_request")
    request_id: Mapped[int | None] = mapped_column(ForeignKey("salary_change_requests.id"), nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    employee: Mapped[Employee] = relationship()


class SalaryChangeRequest(Base):
    __tablename__ = "salary_change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    current_salary: Mapped[int] = mapped_column(Integer)
    proposed_salary: Mapped[int] = mapped_column(Integer)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    base_salary_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="Low", index=True)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_assessment: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee] = relationship()
    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])


class AuditEvent(Base):
    """Append-only, SHA-256 hash-chained audit log. No API can update or delete rows."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[str] = mapped_column(String(40), index=True)  # ISO-8601 UTC string, hashed as-is
    actor: Mapped[str] = mapped_column(String(60))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    outcome: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    """ETL staging. Rows here never change salaries directly."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(200), default="upload.csv")
    status: Mapped[str] = mapped_column(String(20), default="previewed")  # previewed | submitted | discarded
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    """In-app notification for one user. Created by the backend when something needs their attention."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # request_submitted | high_risk | decision | role_change | access_request | security
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info | success | warning | critical
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(200), default="")  # frontend hash route, e.g. #/requests/12
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccessRequest(Base):
    """A signed-in user asks for a privileged role; a security administrator decides (with MFA)."""

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requested_role: Mapped[str] = mapped_column(String(20))
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | approved | rejected | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id])
