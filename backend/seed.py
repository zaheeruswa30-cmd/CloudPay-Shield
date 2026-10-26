"""Create demo data in an EMPTY database. Safe to run more than once.

    python seed.py

- If users already exist, nothing is changed (no reset, no overwrite).
- All people and salaries are fictional demonstration data and are flagged
  is_demo_seed / source = 'seed_demo' so they are never confused with real history.
- Demo passwords below are for LOCAL TESTING ONLY.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from audit import record_event
from database import SessionLocal, init_db
from models import Employee, SalaryChangeRequest, SalaryHistory, User
from risk_engine import percentage_change
from security import hash_password
from services import assess_for_employee

EMPLOYEES = [
    # code, name, department, title, salary (PKR / month)
    ("EMP-001", "Ayesha Khan", "Engineering", "Software Engineer", 250_000),
    ("EMP-002", "Hamza Ali", "Finance", "Financial Analyst", 180_000),
    ("EMP-003", "Sara Ahmed", "Human Resources", "HR Officer", 150_000),
    ("EMP-004", "Bilal Hussain", "Engineering", "Senior Engineer", 320_000),
    ("EMP-005", "Fatima Noor", "Engineering", "QA Engineer", 190_000),
    ("EMP-006", "Usman Tariq", "Finance", "Accountant", 140_000),
    ("EMP-007", "Zainab Raza", "Operations", "Operations Lead", 210_000),
    ("EMP-008", "Ali Raza", "Operations", "Logistics Officer", 120_000),
    ("EMP-009", "Mariam Siddiqui", "Finance", "Payroll Specialist", 165_000),
    ("EMP-010", "Omar Farooq", "Engineering", "DevOps Engineer", 280_000),
]

# Past (fictional) annual increments in percent, used for historical statistics.
SEED_HISTORY = {
    "EMP-001": [8, 10], "EMP-002": [7, 6], "EMP-003": [5, 8], "EMP-004": [12, 9], "EMP-005": [6, 7],
    "EMP-006": [5, 6], "EMP-007": [9, 8], "EMP-008": [6, 5], "EMP-009": [7, 9], "EMP-010": [10, 11],
}

DEMO_USERS = [
    # username, password, role, full name, linked employee code
    ("employee01", "EmployeeDemo!123", "employee", "Ayesha Khan", "EMP-001"),
    ("hr01", "HrDemo!123", "hr", "Hina Malik (HR)", None),
    ("manager01", "ManagerDemo!123", "manager", "Kamran Sheikh (Manager)", None),
    ("auditor01", "AuditorDemo!123", "auditor", "Nadia Qureshi (Auditor)", None),
    ("admin01", "AdminDemo!123", "admin", "Omar Siddiqui (Security Admin)", None),
]


def seed(session_factory=SessionLocal, bind=None) -> None:
    init_db(bind)
    db = session_factory()
    try:
        if db.execute(select(func.count(User.id))).scalar_one() > 0:
            print("Database already has users - nothing changed.")
            return

        now = datetime.now(timezone.utc)
        by_code: dict[str, Employee] = {}
        for code, name, dept, title, salary in EMPLOYEES:
            # Work backwards from today's salary to build two prior yearly increments.
            increments = SEED_HISTORY.get(code, [])
            amounts = [salary]
            for pct in reversed(increments):
                amounts.insert(0, round(amounts[0] / (1 + pct / 100)))
            emp = Employee(employee_code=code, full_name=name, department=dept, job_title=title,
                           current_salary=salary, salary_version=1, is_demo_seed=True)
            db.add(emp)
            db.flush()
            for i, pct in enumerate(increments):
                db.add(SalaryHistory(
                    employee_id=emp.id, old_salary=amounts[i], new_salary=amounts[i + 1],
                    pct_change=percentage_change(amounts[i], amounts[i + 1]), source="seed_demo",
                    effective_at=now - timedelta(days=365 * (len(increments) - i)),
                ))
            by_code[code] = emp

        users: dict[str, User] = {}
        for username, password, role, full_name, emp_code in DEMO_USERS:
            u = User(username=username, full_name=full_name, password_hash=hash_password(password), role=role,
                     employee_id=by_code[emp_code].id if emp_code else None)
            db.add(u)
            db.flush()
            users[username] = u
            record_event(db, actor="seed-script", actor_role="system", action="user_created", outcome="success",
                         target_type="user", target_id=u.id, details={"username": username, "assigned_role": role})

        # A few pending demo requests so the dashboard has something to review.
        hr = users["hr01"]
        demo_requests = [
            ("EMP-002", 194_400, "Annual performance review 2026: rated 'exceeds expectations', 8% merit increase per policy HR-12."),
            ("EMP-003", 240_000, "adjustment"),
            ("EMP-008", 78_000, "Reduced hours"),
        ]
        for code, proposed, reason in demo_requests:
            emp = by_code[code]
            assessment = assess_for_employee(db, emp, proposed, reason, "hr", emp.salary_version)
            req = SalaryChangeRequest(
                employee_id=emp.id, requested_by_id=hr.id, current_salary=emp.current_salary, proposed_salary=proposed,
                pct_change=percentage_change(emp.current_salary, proposed), reason=reason,
                base_salary_version=emp.salary_version, status="pending", source="seed_demo",
                risk_score=assessment["score"], risk_level=assessment["level"],
                manual_review_required=True, risk_assessment=assessment,
            )
            db.add(req)
            db.flush()
            record_event(db, actor="seed-script", actor_role="system", action="risk_assessment",
                         outcome=assessment["level"], target_type="salary_change_request", target_id=req.id,
                         details={"score": assessment["score"], "source": "seed_demo"})
        db.commit()
        print(f"Seeded {len(EMPLOYEES)} demo employees, {len(DEMO_USERS)} demo users and {len(demo_requests)} demo requests.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
