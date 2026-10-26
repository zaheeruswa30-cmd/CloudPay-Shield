"""Create in-app notifications. Called inside the same transaction as the action that caused them."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Notification, User


def notify_users(db: Session, user_ids: Iterable[int], *, kind: str, title: str, body: str = "",
                 link: str = "", severity: str = "info", exclude: int | None = None) -> int:
    count = 0
    for uid in set(user_ids):
        if uid is None or uid == exclude:
            continue
        db.add(Notification(user_id=uid, kind=kind, title=title[:160], body=body, link=link[:200], severity=severity))
        count += 1
    return count


def notify_roles(db: Session, roles: Iterable[str], **kwargs) -> int:
    ids = db.execute(select(User.id).where(User.role.in_(list(roles)), User.is_active.is_(True))).scalars().all()
    return notify_users(db, ids, **kwargs)
