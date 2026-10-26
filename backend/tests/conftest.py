"""Test setup. Every test gets its own temporary SQLite file.

The real database (backend/cloudpay_shield.db) is never opened by the tests.
"""
import os
import sys
from pathlib import Path

# Must be set before any application module is imported.
os.environ["CLOUDPAY_TESTING"] = "1"
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-production-0123456789"
os.environ["MFA_ENCRYPTION_KEY"] = "test-only-mfa-key"
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"
os.environ["SEED_DEMO_DATA"] = "0"
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(__file__).parent / "_unused_default_test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
from routers import auth_routes  # noqa: E402
from seed import seed  # noqa: E402


@pytest.fixture()
def session_factory(tmp_path):
    engine = database.make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed(session_factory=factory, bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def client(session_factory, monkeypatch):
    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override_db
    monkeypatch.setattr(main, "startup", lambda *a, **k: None)
    auth_routes._ip_failures.clear()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def login(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


PASSWORDS = {
    "employee01": "EmployeeDemo!123",
    "hr01": "HrDemo!123",
    "manager01": "ManagerDemo!123",
    "auditor01": "AuditorDemo!123",
    "admin01": "AdminDemo!123",
}


@pytest.fixture()
def tokens(client):
    return {u: login(client, u, p)["access_token"] for u, p in PASSWORDS.items()}


def enroll_mfa(client, token):
    """Enrol MFA and return (new_token, secret, recovery_codes)."""
    setup = client.post("/auth/mfa/setup", headers=auth(token)).json()
    secret = setup["manual_entry_key"]
    r = client.post("/auth/mfa/enable", headers=auth(token), json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["access_token"], secret, body["recovery_codes"]
