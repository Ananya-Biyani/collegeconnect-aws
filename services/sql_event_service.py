"""Persistent event-service adapter; same public interface as event_service.py."""
from datetime import datetime
from sqlalchemy import select, insert, update, func
from services.sql_db import events, registrations, get_engine


def _row(row):
    if row is None:
        return None
    result = dict(row._mapping)
    result["id"] = str(result["id"])
    result["is_open"] = bool(result["is_open"])
    return result


def _enrich(ev, reg_counts=None):
    if not ev:
        return None
    count = (reg_counts or {}).get(ev["id"], 0)
    available = max(0, int(ev["capacity"]) - count)
    status = "Closed" if not ev["is_open"] else "Full" if available == 0 else "Open"
    ev.update({
        "registered_count": count,
        "available_seats": available,
        "is_full": available == 0,
        "status_badge": status,
        "status_text": {"Closed": "Registration Closed", "Full": "Seats Full", "Open": "Open for Registration"}[status],
        "can_register": status == "Open",
    })
    return ev


def _count_for_event(conn, eid):
    return conn.execute(select(func.count()).select_from(registrations).where(
        registrations.c.event_id == eid, registrations.c.status == "Confirmed"
    )).scalar_one()


def list_events(category=None, search=None, reg_counts=None):
    with get_engine().connect() as conn:
        rows = conn.execute(select(events).order_by(events.c.date, events.c.id)).fetchall()
    result = []
    for r in rows:
        ev = _row(r)
        if category and category.lower() != "all" and ev["category"].lower() != category.lower():
            continue
        if search:
            q = search.strip().lower()
            if not any(q in str(ev.get(k, "")).lower() for k in ("title", "description", "venue", "category")):
                continue
        result.append(_enrich(ev, reg_counts))
    return result


def get_event(event_id, reg_counts=None):
    if not str(event_id).isdigit():
        return None
    with get_engine().connect() as conn:
        row = conn.execute(select(events).where(events.c.id == int(event_id))).first()
    return _enrich(_row(row), reg_counts)


def _validated(data, existing=None):
    existing = existing or {}
    payload = {}
    for key, default in (("title", ""), ("category", "Technical"), ("date", ""),
                         ("time", "10:00 AM - 04:00 PM"), ("venue", ""),
                         ("description", ""), ("registration_deadline", "")):
        payload[key] = (data.get(key) or existing.get(key) or default).strip()
    if not payload["title"]: raise ValueError("Event title is required.")
    if not payload["date"]: raise ValueError("Event date is required.")
    if not payload["venue"]: raise ValueError("Event venue is required.")
    try:
        payload["capacity"] = int(data.get("capacity", existing.get("capacity", 50)))
        if payload["capacity"] <= 0: raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Capacity must be a positive integer greater than zero.")
    try:
        payload["display_date"] = datetime.strptime(payload["date"], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        raise ValueError("Event date must use YYYY-MM-DD format.")
    if not payload["registration_deadline"]:
        payload["registration_deadline"] = payload["date"]
    if "is_open" in data:
        payload["is_open"] = bool(data["is_open"])
    else:
        payload["is_open"] = bool(existing.get("is_open", True))
    return payload


def create_event(data):
    payload = _validated(data)
    cat = payload["category"].lower()
    if "cultur" in cat: image = "cultural-fest.svg"
    elif "hack" in cat or "code" in cat: image = "hackathon.svg"
    elif "web" in cat: image = "web-dev.svg"
    elif "ai" in cat or "cloud" in cat: image = "ai-cloud.svg"
    else: image = "tech-fest.svg"
    payload["image_url"] = "/static/images/" + image
    payload["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_engine().begin() as conn:
        eid = conn.execute(insert(events).values(**payload)).inserted_primary_key[0]
        result = conn.execute(select(events).where(events.c.id == eid)).first()
    return _enrich(_row(result))


def update_event(event_id, data, current_registered_count=0):
    eid = int(event_id) if str(event_id).isdigit() else -1
    with get_engine().begin() as conn:
        result = conn.execute(select(events).where(events.c.id == eid).with_for_update()).first()
        if not result:
            raise KeyError(f"Event ID {event_id} not found.")
        old = _row(result)
        payload = _validated(data, old)
        # Count inside the same locking transaction (do not rely on a stale UI count).
        count = _count_for_event(conn, eid)
        if payload["capacity"] < count:
            raise ValueError(f"Capacity cannot be reduced to {payload['capacity']} because {count} students are already registered.")
        conn.execute(update(events).where(events.c.id == eid).values(**payload))
        latest = conn.execute(select(events).where(events.c.id == eid)).first()
    return _enrich(_row(latest), {str(eid): count})


def toggle_event_status(event_id):
    eid = int(event_id) if str(event_id).isdigit() else -1
    with get_engine().begin() as conn:
        row = conn.execute(select(events).where(events.c.id == eid).with_for_update()).first()
        if row is None:
            raise KeyError(f"Event ID {event_id} not found.")
        status = not bool(row._mapping["is_open"])
        conn.execute(update(events).where(events.c.id == eid).values(is_open=status))
    return status


def get_categories():
    with get_engine().connect() as conn:
        vals = conn.execute(select(events.c.category).distinct().order_by(events.c.category)).scalars().all()
    return ["All"] + vals
