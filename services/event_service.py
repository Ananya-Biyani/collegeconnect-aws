"""
services/event_service.py
In-memory Event Data Service for CollegeConnect.

NOTE FOR TEAMMATE (SQL / AWS MIGRATION):
This module encapsulates all event retrieval, creation, and modification logic.
Currently, data is held in-memory within this Python process. When ready to connect
to SQL/RDS, replace the in-memory dictionary operations in these functions with
SQL repository or ORM calls (e.g. SQLAlchemy, raw SQL, or PyMySQL) without altering
the route signatures or templates.
"""

import threading
from datetime import datetime, timedelta

_lock = threading.Lock()

# In-memory storage for events: {event_id: event_dict}
_EVENTS = {}
_NEXT_EVENT_ID = 1


def seed_default_events():
    """
    Seeds default realistic events with dates relative to the current date.
    Called on application startup.
    """
    global _NEXT_EVENT_ID
    with _lock:
        if _EVENTS:
            return  # Already seeded

        # Base date for seeding relative to current date (e.g., Nov 2026)
        base = datetime.now()
        
        default_events = [
            {
                "id": "1",
                "title": "Tech Fest 2026",
                "category": "Technical",
                "date": (base + timedelta(days=14)).strftime("%Y-%m-%d"),
                "display_date": (base + timedelta(days=14)).strftime("%d %b %Y"),
                "time": "09:30 AM - 05:00 PM",
                "venue": "Main Auditorium",
                "description": "A premier showcase of innovation and creativity featuring coding competitions, robotics challenges, project exhibitions, and keynote lectures by industry leaders.",
                "capacity": 50,
                "registration_deadline": (base + timedelta(days=13)).strftime("%Y-%m-%d"),
                "is_open": True,
                "image_url": "/static/images/tech-fest.svg",
                "created_at": base.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "2",
                "title": "Cultural Fest",
                "category": "Cultural",
                "date": (base + timedelta(days=18)).strftime("%Y-%m-%d"),
                "display_date": (base + timedelta(days=18)).strftime("%d %b %Y"),
                "time": "05:00 PM - 10:00 PM",
                "venue": "College Ground & Amphitheater",
                "description": "Experience the vibrant cultural diversity of our campus with live musical bands, traditional and contemporary dance battles, fashion runway, and food stalls.",
                "capacity": 200,
                "registration_deadline": (base + timedelta(days=17)).strftime("%Y-%m-%d"),
                "is_open": True,
                "image_url": "/static/images/cultural-fest.svg",
                "created_at": base.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "3",
                "title": "CodeSprint Hackathon 2026",
                "category": "Technical",
                "date": (base + timedelta(days=22)).strftime("%Y-%m-%d"),
                "display_date": (base + timedelta(days=22)).strftime("%d %b %Y"),
                "time": "24 Hours Non-Stop (Starts 10:00 AM)",
                "venue": "Computer Lab 1 & Innovation Hub",
                "description": "Solve real-world industry problems, build innovative full-stack prototypes, collaborate with mentors, and compete for thrilling cash prizes and internship tracks.",
                "capacity": 75,
                "registration_deadline": (base + timedelta(days=21)).strftime("%Y-%m-%d"),
                "is_open": True,
                "image_url": "/static/images/hackathon.svg",
                "created_at": base.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "4",
                "title": "Web Development Workshop",
                "category": "Workshop",
                "date": (base + timedelta(days=26)).strftime("%Y-%m-%d"),
                "display_date": (base + timedelta(days=26)).strftime("%d %b %Y"),
                "time": "01:00 PM - 05:30 PM",
                "venue": "Software Lab 2",
                "description": "Master modern full-stack web development essentials, responsive UI design systems, RESTful API construction, and deploy your live dynamic web application from scratch.",
                "capacity": 60,
                "registration_deadline": (base + timedelta(days=25)).strftime("%Y-%m-%d"),
                "is_open": True,
                "image_url": "/static/images/web-dev.svg",
                "created_at": base.strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": "5",
                "title": "AI & Cloud Computing Workshop",
                "category": "Workshop",
                "date": (base + timedelta(days=30)).strftime("%Y-%m-%d"),
                "display_date": (base + timedelta(days=30)).strftime("%d %b %Y"),
                "time": "10:00 AM - 03:30 PM",
                "venue": "Seminar Hall A",
                "description": "Dive deep into Generative AI concepts, cloud architecture fundamentals, scalable microservices, and hands-on prompt engineering for computer science students.",
                "capacity": 40,
                "registration_deadline": (base + timedelta(days=29)).strftime("%Y-%m-%d"),
                "is_open": True,
                "image_url": "/static/images/ai-cloud.svg",
                "created_at": base.strftime("%Y-%m-%d %H:%M:%S")
            }
        ]

        for ev in default_events:
            _EVENTS[ev["id"]] = ev
        
        _NEXT_EVENT_ID = 6


def list_events(category=None, search=None, reg_counts=None):
    """
    Returns a list of all events, optionally filtered by category and search term.
    Enriches each event with calculated registration counts and available seats.
    """
    reg_counts = reg_counts or {}
    results = []

    with _lock:
        events_copy = [dict(ev) for ev in _EVENTS.values()]

    for ev in events_copy:
        registered_count = reg_counts.get(ev["id"], 0)
        available_seats = max(0, ev["capacity"] - registered_count)
        is_full = (available_seats == 0)

        # Status determination
        if not ev["is_open"]:
            status_badge = "Closed"
            status_text = "Registration Closed"
            can_register = False
        elif is_full:
            status_badge = "Full"
            status_text = "Seats Full"
            can_register = False
        else:
            status_badge = "Open"
            status_text = "Open for Registration"
            can_register = True

        ev_enriched = {
            **ev,
            "registered_count": registered_count,
            "available_seats": available_seats,
            "is_full": is_full,
            "status_badge": status_badge,
            "status_text": status_text,
            "can_register": can_register
        }

        # Filter by category
        if category and category.lower() != "all" and ev["category"].lower() != category.lower():
            continue

        # Filter by search keyword
        if search:
            q = search.strip().lower()
            if (q not in ev["title"].lower() and 
                q not in ev["description"].lower() and 
                q not in ev["venue"].lower() and 
                q not in ev["category"].lower()):
                continue

        results.append(ev_enriched)

    # Sort upcoming: by date ascending
    results.sort(key=lambda x: x.get("date", ""))
    return results


def get_event(event_id, reg_counts=None):
    """
    Returns a single event by ID enriched with seat capacity statistics.
    """
    reg_counts = reg_counts or {}
    with _lock:
        ev = _EVENTS.get(str(event_id))
        if not ev:
            return None
        ev = dict(ev)

    registered_count = reg_counts.get(ev["id"], 0)
    available_seats = max(0, ev["capacity"] - registered_count)
    is_full = (available_seats == 0)

    if not ev["is_open"]:
        status_badge = "Closed"
        status_text = "Registration Closed"
        can_register = False
    elif is_full:
        status_badge = "Full"
        status_text = "Seats Full"
        can_register = False
    else:
        status_badge = "Open"
        status_text = "Open for Registration"
        can_register = True

    ev.update({
        "registered_count": registered_count,
        "available_seats": available_seats,
        "is_full": is_full,
        "status_badge": status_badge,
        "status_text": status_text,
        "can_register": can_register
    })
    return ev


def create_event(data):
    """
    Creates a new event and stores it in-memory.
    Returns the created event dictionary or raises ValueError.
    """
    global _NEXT_EVENT_ID

    title = (data.get("title") or "").strip()
    category = (data.get("category") or "Technical").strip()
    date = (data.get("date") or "").strip()
    time = (data.get("time") or "10:00 AM - 04:00 PM").strip()
    venue = (data.get("venue") or "").strip()
    description = (data.get("description") or "").strip()
    deadline = (data.get("registration_deadline") or date).strip()
    is_open = bool(data.get("is_open", True))

    if not title:
        raise ValueError("Event title is required.")
    if not date:
        raise ValueError("Event date is required.")
    if not venue:
        raise ValueError("Event venue is required.")

    try:
        capacity = int(data.get("capacity", 50))
        if capacity <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Capacity must be a positive integer greater than zero.")

    # Format human-readable display date
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        display_date = parsed_date.strftime("%d %b %Y")
    except Exception:
        display_date = date

    # Choose default image based on category
    cat_lower = category.lower()
    if "cultur" in cat_lower:
        image_url = "/static/images/cultural-fest.svg"
    elif "hack" in cat_lower or "code" in cat_lower:
        image_url = "/static/images/hackathon.svg"
    elif "web" in cat_lower:
        image_url = "/static/images/web-dev.svg"
    elif "ai" in cat_lower or "cloud" in cat_lower:
        image_url = "/static/images/ai-cloud.svg"
    else:
        image_url = "/static/images/tech-fest.svg"

    with _lock:
        event_id = str(_NEXT_EVENT_ID)
        _NEXT_EVENT_ID += 1

        new_event = {
            "id": event_id,
            "title": title,
            "category": category,
            "date": date,
            "display_date": display_date,
            "time": time,
            "venue": venue,
            "description": description,
            "capacity": capacity,
            "registration_deadline": deadline,
            "is_open": is_open,
            "image_url": image_url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        _EVENTS[event_id] = new_event

    return new_event


def update_event(event_id, data, current_registered_count=0):
    """
    Updates an existing event.
    Enforces that capacity cannot be reduced below current registered count.
    """
    event_id = str(event_id)
    with _lock:
        if event_id not in _EVENTS:
            raise KeyError(f"Event ID {event_id} not found.")

        ev = _EVENTS[event_id]

        title = (data.get("title") or ev["title"]).strip()
        category = (data.get("category") or ev["category"]).strip()
        date = (data.get("date") or ev["date"]).strip()
        time = (data.get("time") or ev["time"]).strip()
        venue = (data.get("venue") or ev["venue"]).strip()
        description = (data.get("description") or ev["description"]).strip()
        deadline = (data.get("registration_deadline") or ev["registration_deadline"]).strip()
        is_open = bool(data.get("is_open", ev["is_open"]))

        if not title:
            raise ValueError("Event title cannot be empty.")
        if not date:
            raise ValueError("Event date cannot be empty.")
        if not venue:
            raise ValueError("Event venue cannot be empty.")

        try:
            capacity = int(data.get("capacity", ev["capacity"]))
            if capacity <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Capacity must be a positive integer greater than zero.")

        if capacity < current_registered_count:
            raise ValueError(
                f"Capacity cannot be reduced to {capacity} because {current_registered_count} students are already registered."
            )

        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d")
            display_date = parsed_date.strftime("%d %b %Y")
        except Exception:
            display_date = date

        ev.update({
            "title": title,
            "category": category,
            "date": date,
            "display_date": display_date,
            "time": time,
            "venue": venue,
            "description": description,
            "capacity": capacity,
            "registration_deadline": deadline,
            "is_open": is_open
        })
        return dict(ev)


def toggle_event_status(event_id):
    """
    Toggles the is_open flag of an event between True and False.
    """
    event_id = str(event_id)
    with _lock:
        if event_id not in _EVENTS:
            raise KeyError(f"Event ID {event_id} not found.")
        _EVENTS[event_id]["is_open"] = not _EVENTS[event_id]["is_open"]
        return _EVENTS[event_id]["is_open"]


def get_categories():
    """
    Returns unique list of categories across existing events.
    """
    with _lock:
        cats = sorted(list({ev["category"] for ev in _EVENTS.values()}))
    return ["All"] + cats


def reset_events():
    """
    Clears all events and re-seeds. Useful for unit testing.
    """
    global _NEXT_EVENT_ID
    with _lock:
        _EVENTS.clear()
        _NEXT_EVENT_ID = 1
    seed_default_events()

