"""In-app notifications for the signed-in user (bell icon in the top bar)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from database import get_db
from models import Notification
from security import CurrentUser, get_current_user

router = APIRouter(tags=["notifications"])


def _iso(dt):
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _dict(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "severity": n.severity, "title": n.title, "body": n.body, "link": n.link,
            "created_at": _iso(n.created_at), "read": n.read_at is not None}


@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=30, ge=1, le=200),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Notification).where(Notification.user_id == current.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.execute(q.order_by(Notification.id.desc()).limit(limit)).scalars().all()
    unread = db.execute(select(func.count(Notification.id)).where(
        Notification.user_id == current.id, Notification.read_at.is_(None))).scalar_one()
    return {"items": [_dict(n) for n in rows], "unread": unread}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != current.id:  # never reveal other users' notifications
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found.")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return _dict(n)


@router.post("/notifications/read-all")
def mark_all_read(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(update(Notification)
                        .where(Notification.user_id == current.id, Notification.read_at.is_(None))
                        .values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"marked_read": result.rowcount}
