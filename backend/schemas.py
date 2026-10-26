"""Pydantic request bodies with validation."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class MfaLoginIn(Strict):
    mfa_token: str = Field(min_length=10, max_length=2000)
    code: str = Field(min_length=6, max_length=12)


class RegisterIn(Strict):
    username: str
    full_name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    # Accepted only so we can reject it explicitly; public sign-up is employee-only.
    role: str | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-32 characters: letters, numbers, _ . -")
        return v.lower()

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address.")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        checks = [r"[a-z]", r"[A-Z]", r"[0-9]", r"[^a-zA-Z0-9]"]
        if sum(bool(re.search(c, v)) for c in checks) < 3:
            raise ValueError("Password needs at least 3 of: lowercase, uppercase, digit, symbol.")
        return v


def _check_password_strength(v: str) -> str:
    checks = [r"[a-z]", r"[A-Z]", r"[0-9]", r"[^a-zA-Z0-9]"]
    if sum(bool(re.search(c, v)) for c in checks) < 3:
        raise ValueError("Password needs at least 3 of: lowercase, uppercase, digit, symbol.")
    return v


class ChangePasswordIn(Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return _check_password_strength(v)


class RoleChangeIn(Strict):
    role: str = Field(pattern="^(employee|hr|manager|auditor|admin)$")
    reason: str = Field(min_length=10, max_length=500)
    mfa_code: str | None = Field(default=None, max_length=12)


class LinkEmployeeIn(Strict):
    employee_id: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=5, max_length=500)


class AdminReasonIn(Strict):
    reason: str = Field(min_length=5, max_length=500)
    mfa_code: str | None = Field(default=None, max_length=12)


class AccountStatusIn(Strict):
    is_active: bool
    reason: str = Field(min_length=5, max_length=500)
    mfa_code: str | None = Field(default=None, max_length=12)


class AccessRequestIn(Strict):
    requested_role: str = Field(pattern="^(hr|manager|auditor)$")
    justification: str = Field(min_length=20, max_length=1000)


class AccessDecisionIn(Strict):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=10, max_length=500)
    mfa_code: str | None = Field(default=None, max_length=12)


class MfaCodeIn(Strict):
    code: str = Field(min_length=6, max_length=12)


class SalaryChangeIn(Strict):
    employee_id: int = Field(gt=0)
    proposed_salary: int = Field(gt=0, le=100_000_000, description="Whole PKR")
    # Mandatory. Short or generic reasons are still accepted here but raise the risk score.
    reason: str = Field(min_length=5, max_length=1000)
    expected_salary_version: int = Field(gt=0, description="Salary version the HR user was looking at")


class RiskPreviewIn(Strict):
    employee_id: int = Field(gt=0)
    proposed_salary: int = Field(gt=0, le=100_000_000)
    reason: str = Field(default="", max_length=1000)


class DecisionIn(Strict):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(min_length=10, max_length=1000)
    mfa_code: str | None = Field(default=None, max_length=12)


class CsvPreviewIn(Strict):
    filename: str = Field(default="upload.csv", max_length=200)
    csv_text: str = Field(min_length=1, max_length=2_000_000)
