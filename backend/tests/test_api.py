"""API, workflow, RBAC, MFA, audit and ETL tests (isolated temporary database)."""
import pyotp
from sqlalchemy import select

from models import AuditEvent, Employee, SalaryHistory, User
from tests.conftest import PASSWORDS, auth, enroll_mfa, login

GOOD_REASON = "Annual performance review 2026: exceeds expectations, merit increase per policy HR-12."


def employee(client, token, code):
    for e in client.get("/employees", headers=auth(token)).json():
        if e["employee_code"] == code:
            return e
    raise AssertionError(code)


def create(client, token, emp, proposed, reason=GOOD_REASON, version=None):
    return client.post("/salary-change-requests", headers=auth(token), json={
        "employee_id": emp["id"], "proposed_salary": proposed, "reason": reason,
        "expected_salary_version": version or emp["salary_version"],
    })


def manager_with_mfa(client, tokens):
    token, secret, codes = enroll_mfa(client, tokens["manager01"])
    return token


# ------------------------------------------------------------------ basics / auth
def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_login_success_and_failure(client):
    body = login(client, "hr01", PASSWORDS["hr01"])
    assert body["user"]["role"] == "hr" and body["access_token"]
    bad = client.post("/auth/login", json={"username": "hr01", "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid username or password."
    unknown = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert unknown.status_code == 401 and unknown.json()["detail"] == bad.json()["detail"]


def test_account_lockout(client):
    for _ in range(5):
        client.post("/auth/login", json={"username": "auditor01", "password": "wrong"})
    r = client.post("/auth/login", json={"username": "auditor01", "password": PASSWORDS["auditor01"]})
    assert r.status_code == 429


def test_unauthenticated_is_401(client):
    assert client.get("/me").status_code == 401
    assert client.get("/employees").status_code == 401
    assert client.get("/me", headers=auth("garbage")).status_code == 401


def test_logout_revokes_token(client, tokens):
    t = tokens["hr01"]
    assert client.post("/auth/logout", headers=auth(t)).status_code == 200
    assert client.get("/me", headers=auth(t)).status_code == 401


# ------------------------------------------------------------------ RBAC
def test_employee_sees_only_own_salary(client, tokens):
    r = client.get("/salary/me", headers=auth(tokens["employee01"]))
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ayesha Khan"
    assert len(r.json()["history"]) == 2


def test_employee_denied_restricted_resources(client, tokens, session_factory):
    t = tokens["employee01"]
    assert client.get("/employees", headers=auth(t)).status_code == 403
    assert client.get("/audit-events", headers=auth(t)).status_code == 403
    assert client.get("/analytics/summary", headers=auth(t)).status_code == 403
    r = client.post("/salary-change-requests", headers=auth(t),
                    json={"employee_id": 1, "proposed_salary": 999999, "reason": GOOD_REASON, "expected_salary_version": 1})
    assert r.status_code == 403
    with session_factory() as db:
        denied = db.execute(select(AuditEvent).where(AuditEvent.action == "access_denied")).scalars().all()
        assert any(e.actor == "employee01" for e in denied)


def test_auditor_cannot_modify(client, tokens):
    t = tokens["auditor01"]
    assert client.get("/audit-events", headers=auth(t)).status_code == 200
    assert client.post("/salary-change-requests/1/decision", headers=auth(t),
                       json={"decision": "approve", "reason": "looks fine to me"}).status_code == 403
    assert client.post("/salary-change-requests", headers=auth(t), json={
        "employee_id": 1, "proposed_salary": 1, "reason": "x", "expected_salary_version": 1}).status_code == 403


# ------------------------------------------------------------------ registration
def test_register_employee_only(client):
    ok = client.post("/auth/register", json={"username": "newstaff", "full_name": "New Staff", "password": "StrongPass!2026"})
    assert ok.status_code == 201 and ok.json()["user"]["role"] == "employee"
    priv = client.post("/auth/register", json={"username": "sneaky", "full_name": "Sneaky", "password": "StrongPass!2026", "role": "manager"})
    assert priv.status_code == 403
    dup = client.post("/auth/register", json={"username": "newstaff", "full_name": "Again", "password": "StrongPass!2026"})
    assert dup.status_code == 409
    weak = client.post("/auth/register", json={"username": "weakling", "full_name": "Weak", "password": "short"})
    assert weak.status_code == 422
    assert "short" not in weak.text  # submitted password not echoed back
    t = login(client, "newstaff", "StrongPass!2026")["access_token"]
    assert client.get("/salary/me", headers=auth(t)).status_code == 404  # not linked to payroll


# ------------------------------------------------------------------ workflow
def test_hr_creates_request_with_risk_and_salary_unchanged(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-001")
    r = create(client, hr, emp, 400_000, reason="adjustment")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["pct_change"] == 60.0
    assert body["risk_level"] in ("High", "Critical")
    found = {i["code"] for i in body["risk_assessment"]["indicators"]}
    assert {"VERY_LARGE_INCREASE", "MISSING_REASON"} <= found
    assert employee(client, hr, "EMP-001")["current_salary"] == 250_000  # not applied before approval


def test_create_with_outdated_version_conflicts(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-004")
    assert create(client, hr, emp, 330_000, version=99).status_code == 409


def test_duplicate_request_detected(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-005")
    create(client, hr, emp, 200_000)
    second = create(client, hr, emp, 200_000).json()
    assert "DUPLICATE_PENDING" in {i["code"] for i in second["risk_assessment"]["indicators"]}


def test_risk_preview_saves_nothing(client, tokens):
    hr = tokens["hr01"]
    emp = employee(client, hr, "EMP-006")
    before = len(client.get("/salary-change-requests", headers=auth(hr)).json())
    r = client.post("/risk/assess", headers=auth(hr), json={"employee_id": emp["id"], "proposed_salary": 300_000, "reason": ""})
    assert r.status_code == 200 and r.json()["score"] > 0
    assert len(client.get("/salary-change-requests", headers=auth(hr)).json()) == before


def test_decision_requires_mfa(client, tokens):
    hr = tokens["hr01"]
    req = create(client, hr, employee(client, hr, "EMP-002"), 190_000).json()
    r = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(tokens["manager01"]),
                    json={"decision": "approve", "reason": "Within policy and documented."})
    assert r.status_code == 403 and "MFA" in r.json()["detail"]


def test_manager_approval_updates_salary_atomically(client, tokens, session_factory):
    hr = tokens["hr01"]
    mgr = manager_with_mfa(client, tokens)
    emp = employee(client, hr, "EMP-002")
    req = create(client, hr, emp, 190_000).json()
    r = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(mgr),
                    json={"decision": "approve", "reason": "Within policy and documented."})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["decided_by"] == "manager01"
    after = employee(client, hr, "EMP-002")
    assert after["current_salary"] == 190_000 and after["salary_version"] == emp["salary_version"] + 1
    with session_factory() as db:
        assert db.execute(select(SalaryHistory).where(SalaryHistory.request_id == req["id"])).scalar_one()
        actions = [e.action for e in db.execute(select(AuditEvent)).scalars()]
        assert "salary_updated" in actions and "salary_request_approve" in actions
    # Double decision is refused.
    again = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(mgr),
                        json={"decision": "reject", "reason": "Changed my mind later."})
    assert again.status_code == 409


def test_manager_rejection_keeps_salary(client, tokens):
    hr = tokens["hr01"]
    mgr = manager_with_mfa(client, tokens)
    emp = employee(client, hr, "EMP-007")
    req = create(client, hr, emp, 230_000).json()
    r = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(mgr),
                    json={"decision": "reject", "reason": "Budget freeze for this quarter."})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert employee(client, hr, "EMP-007")["current_salary"] == 210_000


def test_stale_version_conflict(client, tokens):
    hr = tokens["hr01"]
    mgr = manager_with_mfa(client, tokens)
    emp = employee(client, hr, "EMP-009")
    first = create(client, hr, emp, 175_000).json()
    second = create(client, hr, emp, 178_000).json()
    assert client.post(f"/salary-change-requests/{first['id']}/decision", headers=auth(mgr),
                       json={"decision": "approve", "reason": "Approved within policy."}).status_code == 200
    r = client.post(f"/salary-change-requests/{second['id']}/decision", headers=auth(mgr),
                    json={"decision": "approve", "reason": "Approved within policy."})
    assert r.status_code == 409 and "Version conflict" in r.json()["detail"]
    assert employee(client, hr, "EMP-009")["current_salary"] == 175_000
    detail = client.get(f"/salary-change-requests/{second['id']}", headers=auth(mgr)).json()
    assert detail["is_stale"] is True
    assert "STALE_VERSION" in {i["code"] for i in detail["live_assessment"]["indicators"]}


def test_self_approval_prevented(client, tokens, session_factory):
    hr = tokens["hr01"]
    req = create(client, hr, employee(client, hr, "EMP-008"), 125_000).json()
    with session_factory() as db:  # simulate hr01 later being promoted to manager
        db.execute(select(User)).scalars()
        u = db.execute(select(User).where(User.username == "hr01")).scalar_one()
        u.role = "manager"
        db.commit()
    t = login(client, "hr01", PASSWORDS["hr01"])["access_token"]
    t, _, _ = enroll_mfa(client, t)
    r = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(t),
                    json={"decision": "approve", "reason": "Approving my own request."})
    assert r.status_code == 403 and "Separation of duties" in r.json()["detail"]


def test_high_risk_needs_detailed_reason(client, tokens):
    hr = tokens["hr01"]
    mgr = manager_with_mfa(client, tokens)
    req = create(client, hr, employee(client, hr, "EMP-010"), 500_000, reason="increase").json()
    assert req["risk_level"] in ("High", "Critical")
    r = client.post(f"/salary-change-requests/{req['id']}/decision", headers=auth(mgr),
                    json={"decision": "reject", "reason": "no"})
    assert r.status_code == 422


def test_filters(client, tokens):
    m = tokens["auditor01"]
    allreqs = client.get("/salary-change-requests", headers=auth(m)).json()
    assert len(allreqs) == 3  # seeded demo requests
    pending = client.get("/salary-change-requests?status=pending", headers=auth(m)).json()
    assert all(r["status"] == "pending" for r in pending)
    found = client.get("/salary-change-requests?search=sara", headers=auth(m)).json()
    assert len(found) == 1 and found[0]["employee_name"] == "Sara Ahmed"
    assert client.get("/salary-change-requests?status=bogus", headers=auth(m)).status_code == 422


# ------------------------------------------------------------------ MFA
def test_mfa_login_flow_and_lockout(client, tokens, session_factory):
    _, secret, recovery = enroll_mfa(client, tokens["auditor01"])
    first = client.post("/auth/login", json={"username": "auditor01", "password": PASSWORDS["auditor01"]}).json()
    assert first["mfa_required"] is True and "access_token" not in first
    bad = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": "000000"})
    assert bad.status_code == 401
    # Recovery code works exactly once.
    ok = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": recovery[0]})
    assert ok.status_code == 200 and ok.json()["user"]["mfa_verified_session"] is True
    again = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": recovery[0]})
    assert again.status_code == 401
    # The pending MFA token cannot be used as an access token.
    assert client.get("/me", headers=auth(first["mfa_token"])).status_code == 401
    # TOTP code works (reset replay marker because enrolment used the current step).
    with session_factory() as db:
        u = db.execute(select(User).where(User.username == "auditor01")).scalar_one()
        u.mfa_last_used_step = None
        db.commit()
    totp_ok = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": pyotp.TOTP(secret).now()})
    assert totp_ok.status_code == 200
    # Replay of the same code is refused.
    replay = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": pyotp.TOTP(secret).now()})
    assert replay.status_code == 401
    for _ in range(5):
        client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": "123456"})
    locked = client.post("/auth/mfa/login", json={"mfa_token": first["mfa_token"], "code": "123456"})
    assert locked.status_code == 429


def test_mfa_secret_encrypted_at_rest(client, tokens, session_factory):
    _, secret, _ = enroll_mfa(client, tokens["hr01"])
    with session_factory() as db:
        u = db.execute(select(User).where(User.username == "hr01")).scalar_one()
        assert u.mfa_enabled and secret not in (u.mfa_secret_enc or "")
        assert all(secret not in str(e.details) for e in db.execute(select(AuditEvent)).scalars())


def test_manager_cannot_disable_mfa(client, tokens):
    mgr = manager_with_mfa(client, tokens)
    assert client.post("/auth/mfa/disable", headers=auth(mgr), json={"code": "123456"}).status_code == 403


# ------------------------------------------------------------------ audit
def test_audit_chain_verifies_and_detects_tampering(client, tokens, session_factory):
    hr = tokens["hr01"]
    create(client, hr, employee(client, hr, "EMP-003"), 160_000)
    a = tokens["auditor01"]
    ok = client.get("/audit/verify", headers=auth(a)).json()
    assert ok["valid"] is True and ok["total"] > 0
    with session_factory() as db:
        ev = db.execute(select(AuditEvent).where(AuditEvent.action == "salary_request_create")).scalars().first()
        ev.outcome = "tampered"
        db.commit()
        bad_id = ev.id
    bad = client.get("/audit/verify", headers=auth(a)).json()
    assert bad["valid"] is False and bad["broken_at_id"] == bad_id


def test_audit_never_contains_passwords(client, tokens, session_factory):
    client.post("/auth/login", json={"username": "hr01", "password": "MySecretAttempt!9"})
    with session_factory() as db:
        for e in db.execute(select(AuditEvent)).scalars():
            assert "MySecretAttempt" not in str(e.details)


# ------------------------------------------------------------------ analytics + ETL
def test_analytics_summary(client, tokens):
    s = client.get("/analytics/summary", headers=auth(tokens["manager01"])).json()
    assert s["total_employees"] == 10
    assert s["status_counts"]["pending"] == 3
    assert sum(s["risk_counts"].values()) == 3
    assert s["history_sources"] == {"seed_demo": 20}


def test_etl_preview_and_submit_never_changes_salaries(client, tokens):
    hr = tokens["hr01"]
    sample = client.get("/etl/sample", headers=auth(hr)).json()
    prev = client.post("/etl/preview", headers=auth(hr), json={"filename": sample["filename"], "csv_text": sample["csv_text"]})
    assert prev.status_code == 200, prev.text
    s = prev.json()["summary"]
    assert s["total_rows"] == 8
    assert s["invalid_rows"] == 5  # abc salary, bad date, duplicate, unknown code, missing salary
    assert s["duplicate_rows"] == 1
    assert s["submittable_rows"] == 3
    assert s["suspicious_rows"] >= 1
    rows = {r["row_number"]: r for r in prev.json()["rows"]}
    assert any("not a number" in e for e in rows[4]["errors"])
    assert any("differs from system" in w for w in rows[8]["warnings"])
    before = {e["employee_code"]: e["current_salary"] for e in client.get("/employees", headers=auth(hr)).json()}
    sub = client.post(f"/etl/batches/{prev.json()['batch_id']}/submit", headers=auth(hr)).json()
    assert len(sub["created_request_ids"]) == 3
    after = {e["employee_code"]: e["current_salary"] for e in client.get("/employees", headers=auth(hr)).json()}
    assert before == after
    assert client.post(f"/etl/batches/{prev.json()['batch_id']}/submit", headers=auth(hr)).status_code == 409


def test_etl_missing_columns(client, tokens):
    r = client.post("/etl/preview", headers=auth(tokens["hr01"]), json={"csv_text": "name,salary\nA,1\n"})
    assert r.json()["summary"]["fatal_error"].startswith("Missing required column")
