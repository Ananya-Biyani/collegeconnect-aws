"""
services/registration_service.py
In-memory Registration Data Service for CollegeConnect.

NOTE FOR TEAMMATE (SQL / AWS MIGRATION):
This module encapsulates all student event registration rules, duplicate checking,
capacity checks, and query filters.
Currently, registrations are stored in an in-memory dictionary.
When connecting to PostgreSQL/MySQL via Amazon RDS:
  1. Replace `_REGISTRATIONS` with your SQL table or SQLAlchemy model `Registration`.
  2. Map `(event_id, normalized_email)` to a UNIQUE database constraint or index.
  3. Keep the function signatures identical so the Flask routes do not need to change.
"""

import re
import uuid
import threading
from datetime import datetime

_lock = threading.Lock()

# In-memory store: {registration_id: reg_dict}
_REGISTRATIONS = {}
_NEXT_REG_ID = 1

# Allowed departments for college validation
ALLOWED_DEPARTMENTS = [
    "Computer Science & Engineering",
    "Information Technology",
    "Electronics & Communication",
    "Electrical & Electronics",
    "Mechanical Engineering",
    "Civil Engineering",
    "Data Science & AI",
    "Business Administration"
]

ALLOWED_ACADEMIC_YEARS = [
    "1st Year (Freshman)",
    "2nd Year (Sophomore)",
    "3rd Year (Junior)",
    "4th Year (Senior)",
    "Postgraduate / Masters"
]

# Standard RFC 5322 compatible simplified email regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class RegistrationError(Exception):
    """Base error for registration failures."""
    pass


class DuplicateRegistrationError(RegistrationError):
    """Raised when normalized email has already registered for the same event."""
    pass


class EventFullError(RegistrationError):
    """Raised when available seats have reached zero."""
    pass


class EventClosedError(RegistrationError):
    """Raised when an event is closed for registration."""
    pass


class ValidationError(RegistrationError):
    """Raised when form validation fails."""
    pass


def normalize_email(email):
    """
    Trims leading/trailing whitespace and converts to lowercase.
    """
    if not email:
        return ""
    return email.strip().lower()


def validate_email_format(email):
    """
    Validates email format using regex.
    """
    normalized = normalize_email(email)
    if not normalized or not EMAIL_REGEX.match(normalized):
        return False
    return True


def get_registration_counts_by_event():
    """
    Returns a dictionary of {event_id: count_of_active_registrations}.
    """
    with _lock:
        counts = {}
        for reg in _REGISTRATIONS.values():
            if reg.get("status") == "Confirmed":
                eid = reg["event_id"]
                counts[eid] = counts.get(eid, 0) + 1
        return counts


def get_active_count_for_event(event_id):
    """
    Returns current active registration count for a specific event.
    """
    event_id = str(event_id)
    with _lock:
        return sum(
            1 for reg in _REGISTRATIONS.values()
            if reg["event_id"] == event_id and reg.get("status") == "Confirmed"
        )


def register_student(event, full_name, email, department, academic_year=None):
    """
    Registers a student for an event after validating all constraints:
    - Non-empty fields
    - Email normalization and format check
    - Allowed department check
    - Event exists and is open
    - Capacity check (available seats > 0)
    - Duplicate check: Same normalized email cannot register twice for same event.

    Returns the new registration record dict.
    """
    global _NEXT_REG_ID

    # 1. Clean input fields
    name = (full_name or "").strip()
    norm_email = normalize_email(email)
    dept = (department or "").strip()
    year = (academic_year or "").strip()

    # 2. Field-level validation
    errors = {}
    if not name:
        errors["student_name"] = "Full name is required."
    elif len(name) < 2:
        errors["student_name"] = "Full name must be at least 2 characters."

    if not norm_email:
        errors["college_email"] = "College email is required."
    elif not validate_email_format(norm_email):
        errors["college_email"] = "Please enter a valid email address (e.g., student@college.edu)."

    if not dept:
        errors["department"] = "Please select your department."
    elif dept not in ALLOWED_DEPARTMENTS:
        errors["department"] = f"Invalid department selected. Please choose from the list."

    if errors:
        raise ValidationError(errors)

    if not event:
        raise RegistrationError("Selected event does not exist.")

    event_id = str(event["id"])

    # Synchronized critical section for capacity & duplicate checks
    with _lock:
        # 3. Check if event is open
        if not event.get("is_open", True):
            raise EventClosedError("Registration for this event is currently closed.")

        # 4. Check Duplicate Registration:
        # Normalize email and verify no existing record matches (event_id, norm_email)
        for existing in _REGISTRATIONS.values():
            if existing["event_id"] == event_id and existing["email"] == norm_email:
                raise DuplicateRegistrationError("You are already registered for this event.")

        # 5. Check Capacity
        current_count = sum(
            1 for r in _REGISTRATIONS.values()
            if r["event_id"] == event_id and r.get("status") == "Confirmed"
        )
        capacity = int(event.get("capacity", 0))
        if current_count >= capacity:
            raise EventFullError("This event is fully booked. No remaining seats are available.")

        # 6. Generate unique reference code: e.g. CC-2026-A1B2C3
        reg_id = str(_NEXT_REG_ID)
        _NEXT_REG_ID += 1
        ref_code = f"CC-2026-{uuid.uuid4().hex[:6].upper()}"

        new_reg = {
            "id": reg_id,
            "reference_id": ref_code,
            "event_id": event_id,
            "event_title": event.get("title", ""),
            "event_date": event.get("display_date", event.get("date", "")),
            "event_time": event.get("time", ""),
            "event_venue": event.get("venue", ""),
            "student_name": name,
            "email": norm_email,
            "department": dept,
            "academic_year": year if year else "Not Specified",
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "display_registered_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "status": "Confirmed"
        }

        _REGISTRATIONS[reg_id] = new_reg

    return new_reg


def get_registration_by_ref(reference_id):
    """
    Retrieves a registration record by its unique reference code (e.g. CC-2026-XXXX).
    """
    if not reference_id:
        return None
    ref_clean = reference_id.strip().upper()
    with _lock:
        for reg in _REGISTRATIONS.values():
            if reg["reference_id"] == ref_clean:
                return dict(reg)
    return None


def find_registrations_by_email(email):
    """
    Demo Lookup: Searches registrations matching normalized email address.
    Returns list of registrations sorted latest first.
    """
    norm = normalize_email(email)
    if not norm:
        return []

    with _lock:
        matches = [
            dict(reg) for reg in _REGISTRATIONS.values()
            if reg["email"] == norm
        ]

    matches.sort(key=lambda r: r.get("registered_at", ""), reverse=True)
    return matches


def get_all_registrations(search=None, event_filter=None):
    """
    Returns all registrations for admin view, with optional student search and event filter.
    """
    with _lock:
        regs = [dict(r) for r in _REGISTRATIONS.values()]

    results = []
    for r in regs:
        # Event filter
        if event_filter and str(r["event_id"]) != str(event_filter):
            continue

        # Search by student name or email
        if search:
            q = search.strip().lower()
            if (q not in r["student_name"].lower() and
                q not in r["email"].lower() and
                q not in r["reference_id"].lower()):
                continue

        results.append(r)

    # Sort newest first
    results.sort(key=lambda r: r.get("registered_at", ""), reverse=True)
    return results


def list_event_attendees(event_id, search=None):
    """
    Returns registered attendees for a specific event.
    """
    return get_all_registrations(search=search, event_filter=str(event_id))


def get_kpis(events):
    """
    Calculates live dashboard KPIs from current in-memory events and registrations.
    """
    reg_counts = get_registration_counts_by_event()
    total_events = len(events)
    total_registrations = sum(reg_counts.values())

    total_seats_capacity = sum(ev.get("capacity", 0) for ev in events)
    total_available_seats = max(0, total_seats_capacity - total_registrations)

    full_or_closed_events = 0
    for ev in events:
        registered = reg_counts.get(ev["id"], 0)
        is_full = (registered >= ev.get("capacity", 0))
        is_closed = not ev.get("is_open", True)
        if is_full or is_closed:
            full_or_closed_events += 1

    return {
        "total_events": total_events,
        "total_registrations": total_registrations,
        "total_available_seats": total_available_seats,
        "full_or_closed_events": full_or_closed_events
    }


def seed_demo_registrations():
    """
    Seeds a couple of realistic demo registrations so the admin dashboard
    and attendee lists show immediate illustrative data.
    """
    with _lock:
        if _REGISTRATIONS:
            return

    demo_data = [
        ("1", "Aarav Sharma", "aarav.sharma@college.edu", "Computer Science & Engineering", "3rd Year (Junior)"),
        ("1", "Priya Patel", "priya.patel@college.edu", "Information Technology", "2nd Year (Sophomore)"),
        ("2", "Rohan Mehta", "rohan.mehta@college.edu", "Mechanical Engineering", "4th Year (Senior)"),
        ("3", "Sneha Rao", "sneha.rao@college.edu", "Data Science & AI", "3rd Year (Junior)"),
    ]

    for eid, sname, semail, sdept, syear in demo_data:
        # Mock event dummy dict for seeding
        ev_dummy = {"id": eid, "title": "Sample Event", "capacity": 100, "is_open": True}
        try:
            register_student(ev_dummy, sname, semail, sdept, syear)
        except Exception:
            pass


def reset_registrations():
    """
    Clears all registrations. Useful for test isolation.
    """
    global _NEXT_REG_ID
    with _lock:
        _REGISTRATIONS.clear()
        _NEXT_REG_ID = 1

