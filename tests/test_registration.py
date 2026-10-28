"""
tests/test_registration.py
Comprehensive automated test suite for CollegeConnect student registration.

Tests:
1. Successful registration with valid data.
2. Missing required fields validation.
3. Invalid email format validation.
4. Duplicate registration for the same event is prevented.
5. Same email can successfully register for two different events.
6. Event capacity reached prevents further registrations.
7. Closed event prevents registration.
8. Nonexistent event handling.
9. Email lookup in My Registrations returns only matching student bookings.
10. Redirect-after-POST pattern verification.
"""

import pytest
from app import app
from services import event_service, registration_service


@pytest.fixture(autouse=True)
def reset_in_memory_state():
    """Reset events and registrations before each test run."""
    event_service.reset_events()
    registration_service.reset_registrations()
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "test-csrf-token"
        yield client


def test_successful_registration(client):
    """Test standard valid registration workflow."""
    post_data = {
        "csrf_token": "test-csrf-token",
        "student_name": "Jordan Lee",
        "college_email": "jordan.lee@college.edu",
        "department": "Computer Science & Engineering",
        "academic_year": "3rd Year (Junior)"
    }
    # Register for event ID 1
    response = client.post("/register/1", data=post_data, follow_redirects=False)

    # Must follow redirect-after-POST
    assert response.status_code == 302
    assert "/registration-success/" in response.headers["Location"]

    # Follow redirect to success page
    success_page = client.get(response.headers["Location"])
    assert success_page.status_code == 200
    assert b"Registration Successful!" in success_page.data
    assert b"Jordan Lee" in success_page.data
    assert b"jordan.lee@college.edu" in success_page.data


def test_missing_fields_validation(client):
    """Test that missing mandatory fields are rejected with field errors."""
    post_data = {
        "csrf_token": "test-csrf-token",
        "student_name": "",
        "college_email": "",
        "department": "",
        "academic_year": ""
    }
    response = client.post("/register/1", data=post_data)
    assert response.status_code == 400
    assert b"Full name is required." in response.data
    assert b"College email is required." in response.data
    assert b"Please select your department." in response.data


def test_invalid_email_format(client):
    """Test that malformed email address is rejected."""
    post_data = {
        "csrf_token": "test-csrf-token",
        "student_name": "Taylor Swift",
        "college_email": "not-an-email",
        "department": "Information Technology"
    }
    response = client.post("/register/1", data=post_data)
    assert response.status_code == 400
    assert b"valid email address" in response.data


def test_duplicate_registration_same_event_prevented(client):
    """
    CRITICAL REQUIREMENT:
    Normalized email cannot register for the same event more than once.
    Friendly error message: 'You are already registered for this event.'
    Does NOT increment count or decrement available seats.
    """
    # 1st Registration
    post_data = {
        "csrf_token": "test-csrf-token",
        "student_name": "Sam Student",
        "college_email": "Sam.Student@College.EDU ",  # mixed case + space
        "department": "Mechanical Engineering"
    }
    r1 = client.post("/register/1", data=post_data, follow_redirects=True)
    assert r1.status_code == 200
    assert b"Registration Successful!" in r1.data

    # Check seat count after first registration
    ev_after_1 = event_service.get_event("1", registration_service.get_registration_counts_by_event())
    assert ev_after_1["registered_count"] == 1

    # 2nd Registration attempt with duplicate normalized email for same event
    post_data_dup = {
        "csrf_token": "test-csrf-token",
        "student_name": "Sam Student",
        "college_email": "  sam.student@college.edu",  # trimmed lowercase
        "department": "Mechanical Engineering"
    }
    r2 = client.post("/register/1", data=post_data_dup)
    assert r2.status_code == 400
    assert b"You are already registered for this event." in r2.data

    # Count must NOT increase and available seats must NOT decrease
    ev_after_2 = event_service.get_event("1", registration_service.get_registration_counts_by_event())
    assert ev_after_2["registered_count"] == 1
    assert ev_after_2["available_seats"] == ev_after_1["available_seats"]


def test_same_email_registers_for_two_different_events(client):
    """
    A student may register for multiple different events using the same email.
    """
    email = "alex.rivera@college.edu"
    
    # Register for Event 1 (Tech Fest)
    res1 = client.post("/register/1", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Alex Rivera",
        "college_email": email,
        "department": "Computer Science & Engineering"
    }, follow_redirects=True)
    assert res1.status_code == 200
    assert b"Registration Successful!" in res1.data

    # Register for Event 2 (Cultural Fest) with same email
    res2 = client.post("/register/2", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Alex Rivera",
        "college_email": email,
        "department": "Computer Science & Engineering"
    }, follow_redirects=True)
    assert res2.status_code == 200
    assert b"Registration Successful!" in res2.data

    # Check lookup returns both
    lookup = registration_service.find_registrations_by_email(email)
    assert len(lookup) == 2
    event_ids = {r["event_id"] for r in lookup}
    assert event_ids == {"1", "2"}


def test_event_capacity_reached_prevents_registration(client):
    """
    Ensure available seats greater than zero rule is strictly enforced.
    Prevent registration beyond the event capacity.
    """
    # Create a micro event with capacity 1
    micro_event = event_service.create_event({
        "title": "VIP Workshop",
        "category": "Workshop",
        "date": "2026-12-01",
        "venue": "Room 101",
        "capacity": 1,
        "is_open": True
    })
    eid = micro_event["id"]

    # Student 1 books the only seat
    client.post(f"/register/{eid}", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Student One",
        "college_email": "student.one@college.edu",
        "department": "Civil Engineering"
    })

    # Student 2 attempts to book when capacity is reached
    r2 = client.post(f"/register/{eid}", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Student Two",
        "college_email": "student.two@college.edu",
        "department": "Civil Engineering"
    })
    assert r2.status_code == 400
    assert b"fully booked" in r2.data


def test_closed_event_prevents_registration(client):
    """Ensure closed events reject registration attempts."""
    # Close event 1
    event_service.update_event("1", {"is_open": False})

    res = client.post("/register/1", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Late Student",
        "college_email": "late.student@college.edu",
        "department": "Information Technology"
    })
    assert res.status_code == 400
    assert b"currently closed" in res.data


def test_nonexistent_event_redirects(client):
    """Nonexistent event returns redirect to homepage with error flash."""
    res = client.get("/register/99999", follow_redirects=True)
    assert res.status_code == 200
    assert b"Event not found" in res.data


def test_my_registrations_email_lookup_matches_only_student(client):
    """
    Ensure email lookup shows only matching normalized registrations
    and does not expose other students' data.
    """
    # Register Student A
    client.post("/register/1", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Alice Cooper",
        "college_email": "alice@college.edu",
        "department": "Computer Science & Engineering"
    })

    # Register Student B
    client.post("/register/2", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Bob Dylan",
        "college_email": "bob@college.edu",
        "department": "Mechanical Engineering"
    })

    # Student A looks up their registrations
    resp = client.post("/my-registrations", data={
        "csrf_token": "test-csrf-token",
        "email": "  ALICE@COLLEGE.EDU  "  # case + whitespace test
    })
    assert resp.status_code == 200
    assert b"Tech Fest 2026" in resp.data
    # Must NOT show Bob's event or name
    assert b"Bob Dylan" not in resp.data
    assert b"Cultural Fest" not in resp.data

