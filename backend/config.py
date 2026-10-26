"""Central configuration. All secrets come from environment variables (.env file).

Nothing in this file is a production secret. If SECRET_KEY or MFA_ENCRYPTION_KEY
is missing, a random key is generated for the current process only and a warning
is printed. Tokens then stop working after a restart, which is acceptable for a
local demo but not for production.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _secret(name: str) -> str:
    """Read a secret from the environment.

    For local development only: if it is missing, generate a random value and
    save it to backend/.env (which is git-ignored) so it survives restarts.
    """
    value = os.getenv(name, "").strip()
    if value:
        return value
    value = secrets.token_urlsafe(48)
    if os.getenv("CLOUDPAY_TESTING") != "1":
        env_path = BASE_DIR / ".env"
        with env_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n{name}={value}\n")
        warnings.warn(f"{name} was not set; generated a local value in backend/.env", stacklevel=2)
    os.environ[name] = value
    return value


def _fernet_key(raw: str) -> bytes:
    """Accept a real Fernet key, or derive one from any string."""
    try:
        decoded = base64.urlsafe_b64decode(raw.encode())
        if len(decoded) == 32:
            return raw.encode()
    except Exception:  # noqa: BLE001 - fall through to derivation
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


@dataclass(frozen=True)
class RiskPolicy:
    """Documented, configurable weights for the explainable risk score (0-100).

    This is a transparent rule-based RISK SCORE, not a fraud probability.
    """

    increase_threshold_pct: float = _env_float("RISK_INCREASE_THRESHOLD_PCT", 25)
    very_large_increase_pct: float = _env_float("RISK_VERY_LARGE_INCREASE_PCT", 50)
    decrease_threshold_pct: float = _env_float("RISK_DECREASE_THRESHOLD_PCT", 10)
    severe_decrease_pct: float = _env_float("RISK_SEVERE_DECREASE_PCT", 30)
    min_reason_length: int = _env_int("RISK_MIN_REASON_LENGTH", 15)
    min_history_samples: int = _env_int("RISK_MIN_HISTORY_SAMPLES", 5)
    robust_z_threshold: float = _env_float("RISK_ROBUST_Z_THRESHOLD", 3.0)
    repeated_window_days: int = _env_int("RISK_REPEATED_WINDOW_DAYS", 30)
    repeated_unresolved_count: int = _env_int("RISK_REPEATED_UNRESOLVED_COUNT", 3)
    minimum_salary: int = _env_int("PAYROLL_MINIMUM_SALARY", 37000)
    maximum_salary: int = _env_int("PAYROLL_MAXIMUM_SALARY", 5_000_000)

    weights: dict = field(
        default_factory=lambda: {
            "LARGE_INCREASE": 25,
            "VERY_LARGE_INCREASE": 40,
            "UNUSUAL_DECREASE": 20,
            "SEVERE_DECREASE": 35,
            "NO_CHANGE": 10,
            "MISSING_REASON": 20,
            "VAGUE_REASON": 10,
            "DUPLICATE_PENDING": 20,
            "REPEATED_UNRESOLVED": 10,
            "REPEATED_LARGE_CHANGES": 10,
            "STALE_VERSION": 25,
            "HISTORICAL_DEVIATION": 15,
            "BELOW_MINIMUM_SALARY": 30,
            "ABOVE_MAXIMUM_SALARY": 15,
            "INVALID_BASELINE": 30,
            "UNAUTHORIZED_ROLE": 40,
            "INSUFFICIENT_HISTORY": 0,
        }
    )
    # Inclusive lower bounds for each level.
    levels: tuple = (("Critical", 75), ("High", 50), ("Medium", 25), ("Low", 0))
    vague_reasons: tuple = (
        "adjustment", "salary adjustment", "update", "salary update", "change",
        "increase", "raise", "n/a", "na", "none", "misc", "other", "test",
        "as discussed", "per request", "requested", "ok", "approved",
    )


@dataclass(frozen=True)
class Settings:
    secret_key: str = field(default_factory=lambda: _secret("SECRET_KEY"))
    mfa_key: bytes = field(default_factory=lambda: _fernet_key(_secret("MFA_ENCRYPTION_KEY")))
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'cloudpay_shield.db').as_posix()}")
    access_token_minutes: int = _env_int("ACCESS_TOKEN_MINUTES", 30)
    mfa_pending_minutes: int = 5
    jwt_algorithm: str = "HS256"
    cors_origins: tuple = tuple(
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    )
    require_mfa_for_decisions: bool = _env_bool("REQUIRE_MFA_FOR_DECISIONS", True)
    # Admin actions (role changes, MFA resets, account status) always need an MFA-verified admin session.
    require_mfa_for_admin: bool = _env_bool("REQUIRE_MFA_FOR_ADMIN", True)
    # On startup: create missing tables and, ONLY if the database has no users, add fictional demo data.
    seed_demo_data: bool = _env_bool("SEED_DEMO_DATA", True)
    password_iterations: int = _env_int("PASSWORD_HASH_ITERATIONS", 390_000)
    max_login_failures: int = 5
    login_lock_minutes: int = 5
    max_mfa_failures: int = 5
    mfa_lock_minutes: int = 5
    risk: RiskPolicy = field(default_factory=RiskPolicy)


settings = Settings()
