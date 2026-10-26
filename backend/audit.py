"""SHA-256 hash-chained audit log.

Each event stores prev_hash (the previous event's hash) and its own hash:

    hash = SHA256( canonical_json({timestamp, actor, actor_role, action,
                                   target_type, target_id, outcome, details,
                                   prev_hash}) )

The first event uses prev_hash = 64 zeros. To verify, walk the events in id order,
recompute each hash and check that every prev_hash equals the previous hash.

Limitation: the chain lives in the same database as the data. Anyone with direct
write access to the database file could rewrite the whole chain. It detects
accidental or partial tampering; it is not tamper-proof storage. Production would
anchor the latest hash externally (e.g. WORM storage or a separate log service).

Never put passwords, tokens, TOTP secrets or recovery codes in `details`.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditEvent

GENESIS_HASH = "0" * 64
_FORBIDDEN_KEYS = {"password", "token", "access_token", "secret", "totp_secret", "code", "recovery_code", "mfa_token"}

# Serialises appends inside one backend process so two requests cannot fork the chain.
audit_lock = threading.RLock()


def _clean(details: dict | None) -> dict:
    details = dict(details or {})
    for key in list(details):
        if key.lower() in _FORBIDDEN_KEYS:
            details[key] = "[omitted]"
    return details


def compute_hash(fields: dict) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_fields(event: AuditEvent) -> dict:
    return {
        "timestamp": event.timestamp,
        "actor": event.actor,
        "actor_role": event.actor_role,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "outcome": event.outcome,
        "details": event.details,
        "prev_hash": event.prev_hash,
    }


def record_event(
    db: Session,
    *,
    actor: str,
    actor_role: str,
    action: str,
    outcome: str,
    target_type: str = "",
    target_id: str | int = "",
    details: dict | None = None,
) -> AuditEvent:
    """Add an event to the current transaction. The caller commits."""
    with audit_lock:
        last = db.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            actor=(actor or "anonymous")[:60],
            actor_role=(actor_role or "none")[:20],
            action=action[:60],
            target_type=str(target_type)[:40],
            target_id=str(target_id)[:40],
            outcome=outcome[:20],
            details=_clean(details),
            prev_hash=last.hash if last else GENESIS_HASH,
        )
        event.hash = compute_hash(_hash_fields(event))
        db.add(event)
        db.flush()
        return event


def verify_chain(db: Session) -> dict:
    events = db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars().all()
    expected_prev = GENESIS_HASH
    for index, event in enumerate(events):
        if event.prev_hash != expected_prev:
            return {
                "valid": False, "checked": index, "total": len(events), "broken_at_id": event.id,
                "problem": "prev_hash does not match the previous event's hash (event removed or reordered)",
            }
        if compute_hash(_hash_fields(event)) != event.hash:
            return {
                "valid": False, "checked": index, "total": len(events), "broken_at_id": event.id,
                "problem": "stored hash does not match the event contents (event modified)",
            }
        expected_prev = event.hash
    return {
        "valid": True, "checked": len(events), "total": len(events), "broken_at_id": None,
        "problem": None, "latest_hash": expected_prev,
    }
