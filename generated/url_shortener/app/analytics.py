"""Click tracking & analytics aggregation."""
from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import ClickEvent


def record_click(db: Session, short_code: str, referrer: str | None = None) -> ClickEvent:
    event = ClickEvent(short_code=short_code, referrer=referrer)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_analytics(db: Session, short_code: str) -> dict:
    total = db.query(func.count(ClickEvent.id)).filter(ClickEvent.short_code == short_code).scalar()
    recent = (
        db.query(ClickEvent)
        .filter(ClickEvent.short_code == short_code)
        .order_by(ClickEvent.timestamp.desc())
        .limit(20)
        .all()
    )
    return {
        "short_code": short_code,
        "total_clicks": total or 0,
        "recent_clicks": [
            {"timestamp": e.timestamp.isoformat(), "referrer": e.referrer} for e in recent
        ],
    }
