"""Tests for the web-platform features: admin role process, access requests, notifications,
employee directory restrictions, searchable audit with integrity status, password change."""
from sqlalchemy import select, update

from models import AuditEvent, Notification, User
from tests.conftest import PASSWORDS, auth, enroll_mfa, login
from tests.test_api import GOOD_REASON, create, employee, manager_with_mfa


def user_id(client, admin_token, username):
    users = client.get("/admin/users", headers=auth(admin_token)).json()["users"]
    return next(u["id"] for u in users if u["username"] == username)


def register(client, username="newstaff", password="Str0ng!Passw0rd"):
    r = client.post("/auth/register", json={"username": username, "full_name": "New Staff", "password": password})
    assert r.status_code == 201, r.text
    return login(client, username, password)["access_token"]


# ------------------------------------------------------------------ admin + roles
def test_admin_routes_need_admin_role(client, tokens):
    for u in ("employee01", "hr01", "manager01", "auditor01"):
        assert client.get("/admin/users", headers=auth(tokens[u])).status_code == 403
    assert client.get("/admin/users").status_code == 401


def test_role_change_requires_admin_mfa(client, tokens):
    admin = tokens["admin01"]
    uid = user_id(client, admin, "employee01")
    r = client.post(f"/admin/users/{uid}/role", headers=auth(admin), json={"role": "hr", "reason": "Joined payroll team"})
    assert r.status_code == 403 and "MFA" in r.json()["detail"]
    mfa_admin, _, _ = enroll_mfa(client, admin)
    r = client.post(f"/admin/users/{uid}/role", headers=auth(mfa_admin), json={"role": "hr", "reason": "Joined payroll team"})
    assert r.status_code == 200 and r.json()["role"] == "hr"
    # Role is read from the database on every request, so it applies immediately.
    assert client.get("/me", headers=auth(tokens["employee01"])).json()["role"] == "hr"


def test_admin_cannot_change_own_role(client, tokens):
    mfa_admin, _, _ = enroll_mfa(client, tokens["admin01"])
    uid = user_id(client, mfa_admin, "admin01")
    r = client.post(f"/admin/users/{uid}/role", headers=auth(mfa_admin), json={"role": "manager", "reason": "testing self change"})
    assert r.status_code == 403


def test_access_request_workflow(client, tokens):
    t = register(client)
    assert client.get("/me", headers=auth(t)).json()["role"] == "employee"
    r = client.post("/access-requests", headers=auth(t), json={"requested_role": "admin", "justification": "x" * 30})
    assert r.status_code == 422  # admin cannot be requested
    r = client.post("/access-requests", headers=auth(t),
                    json={"requested_role": "hr", "justification": "I joined the HR payroll team on 1 Oct 2026."})
    assert r.status_code == 201
    req_id = r.json()["id"]
    dup = client.post("/access-requests", headers=auth(t),
                      json={"requested_role": "auditor", "justification": "Second request should be refused."})
    assert dup.status_code == 409

    admin_notes = client.get("/notifications", headers=auth(tokens["admin01"])).json()
    assert admin_notes["unread"] >= 1 and any("requests" in n["title"] for n in admin_notes["items"])

    mfa_admin, _, _ = enroll_mfa(client, tokens["admin01"])
    d = client.post(f"/admin/access-requests/{req_id}/decision", headers=auth(mfa_admin),
                    json={"decision": "approve", "reason": "Confirmed with HR director"})
    assert d.status_code == 200 and d.json()["status"] == "approved"
    assert client.get("/me", headers=auth(t)).json()["role"] == "hr"
    again = client.post(f"/admin/access-requests/{req_id}/decision", headers=auth(mfa_admin),
                        json={"decision": "reject", "reason": "Second decision attempt"})
    assert again.status_code == 409


def test_last_admin_cannot_be_removed(client, tokens, session_factory):
    mfa_admin, _, _ = enroll_mfa(client, tokens["admin01"])
    # Make a second admin, then try to demote the original from the second one.
    t = register(client, "secadmin")
    uid = user_id(client, mfa_admin, "secadmin")
    assert client.post(f"/admin/users/{uid}/role", headers=auth(mfa_admin),
                       json={"role": "admin", "reason": "Backup administrator"}).status_code == 200
    second, _, _ = enroll_mfa(client, t)
    first_id = user_id(client, second, "admin01")
    assert client.post(f"/admin/users/{first_id}/role", headers=auth(second),
                       json={"role": "auditor", "reason": "Rotate duties now"}).status_code == 200
    # Now 'secadmin' is the only admin; nobody else can demote them (and they cannot demote themselves).
    assert client.post(f"/admin/users/{uid}/role", headers=auth(second),
                       json={"role": "hr", "reason": "Self demotion attempt"}).status_code == 403


# ------------------------------------------------------------------ notifications
def test_notifications_on_submit_and_decision(client, tokens):
    hr, mgr = tokens["hr01"], manager_with_mfa(client, tokens)
    emp = employee(client, hr, "EMP-004")
    r = create(client, hr, emp, 520_000, reason="adjustment")
    assert r.status_code == 201
    req_id = r.json()["id"]
    mgr_notes = client.get("/notifications", headers=auth(mgr)).json()["items"]
    assert any(f"#/requests/{req_id}" == n["link"] for n in mgr_notes)
    aud_notes = client.get("/notifications", headers=auth(tokens["auditor01"])).json()["items"]
    assert any("not a fraud finding" in n["body"] for n in aud_notes)

    client.post(f"/salary-change-requests/{req_id}/decision", headers=auth(mgr),
                json={"decision": "reject", "reason": "No supporting documents were provided."})
    hr_notes = client.get("/notifications", headers=auth(hr)).json()
    assert any("rejected" in n["title"] for n in hr_notes["items"])
    assert client.post("/notifications/read-all", headers=auth(hr)).status_code == 200
    assert client.get("/notifications", headers=auth(hr)).json()["unread"] == 0


def test_notifications_are_private(client, tokens, session_factory):
    db = session_factory()
    other = db.execute(select(User).where(User.username == "manager01")).scalar_one()
    db.add(Notification(user_id=other.id, kind="security", title="private"))
    db.commit()
    nid = db.execute(select(Notification.id).where(Notification.title == "private")).scalar_one()
    db.close()
    assert client.post(f"/notifications/{nid}/read", headers=auth(tokens["hr01"])).status_code == 404


# ------------------------------------------------------------------ employees
def test_employee_directory_salary_restricted_by_role(client, tokens):
    hr_list = client.get("/employees", headers=auth(tokens["hr01"])).json()
    assert all(e["current_salary"] is not None for e in hr_list)
    aud_list = client.get("/employees", headers=auth(tokens["auditor01"])).json()
    assert all(e["current_salary"] is None and e["salary_visible"] is False for e in aud_list)
    assert client.get("/employees", headers=auth(tokens["employee01"])).status_code == 403

    emp_id = hr_list[0]["id"]
    detail = client.get(f"/employees/{emp_id}", headers=auth(tokens["auditor01"])).json()
    assert all(h["old_salary"] is None for h in detail["history"])
    assert all("proposed_salary" not in r for r in detail["requests"])
    full = client.get(f"/employees/{emp_id}", headers=auth(tokens["hr01"])).json()
    assert full["history"] and full["history"][0]["new_salary"] is not None


def test_employee_filters(client, tokens):
    eng = client.get("/employees", params={"department": "Engineering"}, headers=auth(tokens["hr01"])).json()
    assert eng and all(e["department"] == "Engineering" for e in eng)
    found = client.get("/employees", params={"search": "ayesha"}, headers=auth(tokens["hr01"])).json()
    assert [e["full_name"] for e in found] == ["Ayesha Khan"]


def test_risk_preview_lists_open_requests_for_duplicate_warning(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-002")  # has a seeded pending request
    r = client.post("/risk/assess", headers=auth(hr),
                    json={"employee_id": emp["id"], "proposed_salary": 200_000, "reason": GOOD_REASON})
    assert r.status_code == 200 and len(r.json()["open_requests"]) == 1


def test_reason_is_mandatory(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-005")
    assert create(client, hr, emp, 200_000, reason="").status_code == 422


def test_request_filters_mine_and_employee(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-002")
    mine = client.get("/salary-change-requests", params={"mine": True}, headers=auth(hr)).json()
    assert len(mine) == 3
    by_emp = client.get("/salary-change-requests", params={"employee_id": emp["id"]}, headers=auth(hr)).json()
    assert len(by_emp) == 1 and by_emp[0]["employee_code"] == "EMP-002"


# ------------------------------------------------------------------ audit
def test_audit_search_integrity_and_roles(client, tokens, session_factory):
    aud = tokens["auditor01"]
    body = client.get("/audit-events", params={"search": "login"}, headers=auth(aud)).json()
    assert body["events"] and all("login" in e["action"] for e in body["events"])
    assert all(e["integrity"] == "verified" for e in body["events"]) and body["chain"]["valid"]
    # Auditor sees IP details; manager does not.
    assert any("ip" in e["details"] for e in body["events"])
    mgr_body = client.get("/audit-events", params={"search": "login"}, headers=auth(tokens["manager01"])).json()
    assert all("ip" not in e["details"] for e in mgr_body["events"])
    assert client.get("/audit-events", headers=auth(tokens["admin01"])).status_code == 200
    assert client.get("/audit-events", headers=auth(tokens["hr01"])).status_code == 403

    # Tamper with one event in this temporary test database only.
    db = session_factory()
    db.execute(update(AuditEvent).where(AuditEvent.id == 3).values(outcome="tampered"))
    db.commit()
    db.close()
    events = client.get("/audit-events", params={"limit": 2000}, headers=auth(aud)).json()["events"]
    by_id = {e["id"]: e["integrity"] for e in events}
    assert by_id[2] == "verified" and by_id[3] == "broken" and by_id[4] == "unverifiable"


def test_audit_related_request(client, tokens):
    body = client.get("/audit-events", params={"request_id": 1}, headers=auth(tokens["auditor01"])).json()
    assert body["events"] and all(e["related_request_id"] == 1 for e in body["events"])


# ------------------------------------------------------------------ account
def test_change_password(client):
    t = register(client, "pwuser", "Str0ng!Passw0rd")
    bad = client.post("/auth/change-password", headers=auth(t),
                      json={"current_password": "wrong", "new_password": "An0ther!Passw0rd"})
    assert bad.status_code == 401
    ok = client.post("/auth/change-password", headers=auth(t),
                     json={"current_password": "Str0ng!Passw0rd", "new_password": "An0ther!Passw0rd"})
    assert ok.status_code == 200
    assert client.get("/me", headers=auth(t)).status_code == 401  # session revoked
    login(client, "pwuser", "An0ther!Passw0rd")


def test_admin_must_keep_mfa(client, tokens):
    t, secret, _ = enroll_mfa(client, tokens["admin01"])
    import pyotp
    r = client.post("/auth/mfa/disable", headers=auth(t), json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 403
