"""Persistent registrations with DB-enforced uniqueness and MySQL row locking."""
from datetime import datetime
import uuid
from sqlalchemy import select, insert, func
from sqlalchemy.exc import IntegrityError
from services.sql_db import get_engine, events, registrations
from services.registration_service import (
    ALLOWED_DEPARTMENTS, ALLOWED_ACADEMIC_YEARS, EMAIL_REGEX,
    normalize_email, validate_email_format, RegistrationError,
    DuplicateRegistrationError, EventFullError, EventClosedError, ValidationError
)


def _row(row):
    if row is None:
        return None
    d = dict(row._mapping)
    d["id"] = str(d["id"])
    d["event_id"] = str(d["event_id"])
    return d


def get_registration_counts_by_event():
    with get_engine().connect() as conn:
        rows = conn.execute(select(registrations.c.event_id, func.count()).where(
            registrations.c.status == "Confirmed"
        ).group_by(registrations.c.event_id)).all()
    return {str(eid): count for eid, count in rows}


def get_active_count_for_event(event_id):
    if not str(event_id).isdigit(): return 0
    with get_engine().connect() as conn:
        return conn.execute(select(func.count()).select_from(registrations).where(
            registrations.c.event_id == int(event_id), registrations.c.status == "Confirmed"
        )).scalar_one()


def register_student(event, full_name, email, department, academic_year=None):
    name = (full_name or "").strip()
    norm = normalize_email(email)
    dept = (department or "").strip()
    year = (academic_year or "").strip()
    errors = {}
    if not name: errors["student_name"] = "Full name is required."
    elif len(name) < 2: errors["student_name"] = "Full name must be at least 2 characters."
    if not norm: errors["college_email"] = "College email is required."
    elif not validate_email_format(norm): errors["college_email"] = "Please enter a valid email address (e.g., student@college.edu)."
    if not dept: errors["department"] = "Please select your department."
    elif dept not in ALLOWED_DEPARTMENTS: errors["department"] = "Invalid department selected. Please choose from the list."
    if errors: raise ValidationError(errors)
    if not event: raise RegistrationError("Selected event does not exist.")

    eid = int(event["id"])
    now = datetime.now()
    payload = {
        "reference_id": f"CC-{now.year}-{uuid.uuid4().hex[:12].upper()}",
        "event_id": eid,
        "student_name": name,
        "email": norm,
        "department": dept,
        "academic_year": year or "Not Specified",
        "registered_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "display_registered_at": now.strftime("%d %b %Y, %I:%M %p"),
        "status": "Confirmed",
    }
    try:
        with get_engine().begin() as conn:
            # On MySQL, FOR UPDATE locks the same event row for every registration
            # and admin capacity update, preventing concurrent overbooking.
            ev = conn.execute(select(events).where(events.c.id == eid).with_for_update()).first()
            if not ev: raise RegistrationError("Selected event does not exist.")
            ev = ev._mapping
            if not ev["is_open"]: raise EventClosedError("Registration for this event is currently closed.")
            duplicate = conn.execute(select(registrations.c.id).where(
                registrations.c.event_id == eid, registrations.c.email == norm
            )).first()
            if duplicate: raise DuplicateRegistrationError("You are already registered for this event.")
            count = conn.execute(select(func.count()).select_from(registrations).where(
                registrations.c.event_id == eid, registrations.c.status == "Confirmed"
            )).scalar_one()
            if count >= ev["capacity"]: raise EventFullError("This event is fully booked. No remaining seats are available.")
            payload.update({
                "event_title": ev["title"], "event_date": ev["display_date"],
                "event_time": ev["time"], "event_venue": ev["venue"]
            })
            result = conn.execute(insert(registrations).values(**payload))
            row = conn.execute(select(registrations).where(
                registrations.c.id == result.inserted_primary_key[0]
            )).first()
    except IntegrityError as exc:
        # Database unique key is the final safeguard against duplicate submissions.
        raise DuplicateRegistrationError("You are already registered for this event.") from exc
    return _row(row)


def get_registration_by_ref(reference_id):
    if not reference_id: return None
    with get_engine().connect() as conn:
        row = conn.execute(select(registrations).where(
            registrations.c.reference_id == reference_id.strip().upper()
        )).first()
    return _row(row)


def find_registrations_by_email(email):
    norm = normalize_email(email)
    if not norm: return []
    with get_engine().connect() as conn:
        rows = conn.execute(select(registrations).where(
            registrations.c.email == norm
        ).order_by(registrations.c.registered_at.desc(), registrations.c.id.desc())).all()
    return [_row(r) for r in rows]


def get_all_registrations(search=None, event_filter=None):
    with get_engine().connect() as conn:
        statement = select(registrations).order_by(registrations.c.registered_at.desc(), registrations.c.id.desc())
        if event_filter:
            if not str(event_filter).isdigit(): return []
            statement = statement.where(registrations.c.event_id == int(event_filter))
        rows = conn.execute(statement).all()
    result = [_row(r) for r in rows]
    if search:
        q = search.strip().lower()
        result = [r for r in result if any(q in r[k].lower() for k in ("student_name", "email", "reference_id"))]
    return result


def list_event_attendees(event_id, search=None):
    return get_all_registrations(search=search, event_filter=event_id)


def get_kpis(event_list):
    counts = get_registration_counts_by_event()
    total = sum(counts.values())
    seats = sum(max(0, ev["capacity"] - counts.get(ev["id"], 0)) for ev in event_list)
    full_or_closed = sum(not ev["is_open"] or counts.get(ev["id"], 0) >= ev["capacity"] for ev in event_list)
    return {
        "total_events": len(event_list), "total_registrations": total,
        "total_available_seats": seats, "full_or_closed_events": full_or_closed
    }
