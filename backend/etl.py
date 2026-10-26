"""ETL / data validation for payroll change files (CSV).

Extract   -> parse CSV text (no file is written to disk)
Transform -> normalise headers, trim values, parse salaries ("150,000" -> 150000) and dates
Validate  -> required columns, missing values, types, duplicates, unknown employees,
             baseline mismatch with the system of record, risk assessment per row
Load      -> NOT automatic. A preview is stored in a staging table. HR may then submit
             valid rows as normal *pending salary-change requests*, which still need
             manager approval. The import never writes salaries directly.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Employee
from services import assess_for_employee

REQUIRED_COLUMNS = ["employee_code", "full_name", "department", "current_salary", "proposed_salary", "effective_date", "reason"]
MAX_ROWS = 2000


def _parse_salary(raw: str) -> tuple[int | None, str | None]:
    text = (raw or "").strip().replace(",", "").replace("PKR", "").replace("Rs", "").strip()
    if text == "":
        return None, "missing"
    try:
        value = float(text)
    except ValueError:
        return None, f"not a number ('{raw[:20]}')"
    if value <= 0:
        return None, "must be greater than zero"
    if value != int(value):
        return None, "must be whole rupees"
    if value > 100_000_000:
        return None, "unrealistically large"
    return int(value), None


def validate_csv(db: Session, csv_text: str) -> dict:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in headers]
    summary = {
        "columns_found": headers, "missing_columns": missing_cols, "total_rows": 0, "valid_rows": 0,
        "invalid_rows": 0, "rows_with_warnings": 0, "duplicate_rows": 0, "suspicious_rows": 0,
        "submittable_rows": 0, "fatal_error": None,
    }
    if missing_cols:
        summary["fatal_error"] = f"Missing required column(s): {', '.join(missing_cols)}"
        return {"summary": summary, "rows": []}

    employees = {e.employee_code.upper(): e for e in db.execute(select(Employee)).scalars().all()}
    seen_codes: dict[str, int] = {}
    rows: list[dict] = []

    for index, raw in enumerate(reader, start=2):  # row 1 is the header
        if len(rows) >= MAX_ROWS:
            summary["fatal_error"] = f"File has more than {MAX_ROWS} rows; only the first {MAX_ROWS} were checked."
            break
        rec = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        errors: list[str] = []
        warnings: list[str] = []

        for col in REQUIRED_COLUMNS:
            if col != "reason" and not rec.get(col):
                errors.append(f"{col} is missing")

        current, cur_err = _parse_salary(rec.get("current_salary", ""))
        proposed, prop_err = _parse_salary(rec.get("proposed_salary", ""))
        if cur_err and cur_err != "missing":
            errors.append(f"current_salary {cur_err}")
        if prop_err and prop_err != "missing":
            errors.append(f"proposed_salary {prop_err}")

        eff = rec.get("effective_date", "")
        if eff:
            try:
                date.fromisoformat(eff)
            except ValueError:
                errors.append("effective_date must be YYYY-MM-DD")

        code = rec.get("employee_code", "").upper()
        if code:
            if code in seen_codes:
                errors.append(f"duplicate employee_code (also on row {seen_codes[code]})")
                summary["duplicate_rows"] += 1
            else:
                seen_codes[code] = index

        emp = employees.get(code) if code else None
        if code and emp is None:
            errors.append("employee_code not found in payroll system")
        if emp is not None:
            if rec.get("full_name") and rec["full_name"].lower() != emp.full_name.lower():
                warnings.append(f"name differs from system record ('{emp.full_name}')")
            if current is not None and current != emp.current_salary:
                warnings.append(f"file current_salary {current:,} differs from system PKR {emp.current_salary:,}; "
                                "the system value is used as the baseline")
            if proposed is not None and proposed == emp.current_salary:
                warnings.append("proposed salary equals current salary (no change)")
        if not rec.get("reason"):
            warnings.append("reason is empty")

        assessment = None
        if emp is not None and proposed is not None:
            assessment = assess_for_employee(db, emp, proposed, rec.get("reason", ""), "hr", emp.salary_version)
            if assessment["level"] in ("High", "Critical"):
                summary["suspicious_rows"] += 1

        valid = not errors
        submittable = valid and emp is not None and proposed is not None and proposed != emp.current_salary
        summary["total_rows"] += 1
        summary["valid_rows" if valid else "invalid_rows"] += 1
        summary["rows_with_warnings"] += 1 if warnings else 0
        summary["submittable_rows"] += 1 if submittable else 0
        rows.append({
            "row_number": index,
            "employee_code": code,
            "full_name": rec.get("full_name", ""),
            "department": rec.get("department", ""),
            "file_current_salary": current,
            "system_current_salary": emp.current_salary if emp else None,
            "proposed_salary": proposed,
            "effective_date": eff,
            "reason": rec.get("reason", "")[:500],
            "employee_id": emp.id if emp else None,
            "salary_version": emp.salary_version if emp else None,
            "valid": valid,
            "submittable": submittable,
            "errors": errors,
            "warnings": warnings,
            "risk_score": assessment["score"] if assessment else None,
            "risk_level": assessment["level"] if assessment else None,
            "pct_change": assessment["pct_change"] if assessment else None,
            "risk_explanations": assessment["explanations"] if assessment else [],
        })
    return {"summary": summary, "rows": rows}
