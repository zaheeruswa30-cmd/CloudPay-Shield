"""Local administrator tool (requires access to the server and its database).

This is the controlled process for privileged changes. Public sign-up can only
create 'employee' accounts; roles are assigned here, and every action is audited.

Examples (backend folder, virtual environment active):
    python admin.py list-users
    python admin.py assign-role newuser hr
    python admin.py link-employee newuser EMP-005
    python admin.py reset-mfa manager01      # demo recovery when a phone is lost
    python admin.py unlock hr01
    python admin.py verify-audit
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from audit import record_event, verify_chain
from database import SessionLocal, init_db
from models import ROLES, Employee, User


def _user(db, username: str) -> User:
    user = db.execute(select(User).where(User.username == username.lower())).scalar_one_or_none()
    if user is None:
        sys.exit(f"User '{username}' not found.")
    return user


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="CloudPay Shield local admin tool")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-users")
    p = sub.add_parser("assign-role"); p.add_argument("username"); p.add_argument("role", choices=ROLES)
    p = sub.add_parser("link-employee"); p.add_argument("username"); p.add_argument("employee_code")
    p = sub.add_parser("reset-mfa"); p.add_argument("username")
    p = sub.add_parser("unlock"); p.add_argument("username")
    sub.add_parser("verify-audit")
    args = parser.parse_args(argv)

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "list-users":
            for u in db.execute(select(User).order_by(User.id)).scalars():
                print(f"{u.id:>3}  {u.username:<16} {u.role:<9} mfa={'on ' if u.mfa_enabled else 'off'} employee_id={u.employee_id}")
            return
        if args.cmd == "verify-audit":
            print(verify_chain(db))
            return

        user = _user(db, args.username)
        if args.cmd == "assign-role":
            old = user.role
            user.role = args.role
            record_event(db, actor="local-admin", actor_role="admin", action="role_assigned", outcome="success",
                         target_type="user", target_id=user.id, details={"from": old, "to": args.role})
            print(f"{user.username}: {old} -> {args.role}")
        elif args.cmd == "link-employee":
            emp = db.execute(select(Employee).where(Employee.employee_code == args.employee_code.upper())).scalar_one_or_none()
            if emp is None:
                sys.exit("Employee code not found.")
            user.employee_id = emp.id
            record_event(db, actor="local-admin", actor_role="admin", action="employee_linked", outcome="success",
                         target_type="user", target_id=user.id, details={"employee_id": emp.id})
            print(f"{user.username} linked to {emp.employee_code}")
        elif args.cmd == "reset-mfa":
            user.mfa_enabled = False
            user.mfa_secret_enc = None
            user.mfa_pending_secret_enc = None
            user.recovery_code_hashes = []
            user.mfa_failed_attempts = 0
            user.mfa_locked_until = None
            user.mfa_last_used_step = None
            record_event(db, actor="local-admin", actor_role="admin", action="mfa_reset", outcome="success",
                         target_type="user", target_id=user.id)
            print(f"MFA reset for {user.username}. They must enrol again.")
        elif args.cmd == "unlock":
            user.failed_login_attempts = 0
            user.login_locked_until = None
            user.mfa_failed_attempts = 0
            user.mfa_locked_until = None
            record_event(db, actor="local-admin", actor_role="admin", action="account_unlocked", outcome="success",
                         target_type="user", target_id=user.id)
            print(f"{user.username} unlocked.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
