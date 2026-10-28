"""
tests/test_admin.py
Automated test suite for CollegeConnect administrator features and authorization.

Tests:
1. Admin login with correct credentials.
2. Admin login failure with incorrect credentials.
3. Admin logout clears session.
4. Unauthorized access to protected admin routes redirects to login.
5. Admin creating an event.
6. Newly created event immediately appears on the student homepage.
7. Admin editing an existing event.
8. Capacity validation: cannot reduce below registered count.
9. Capacity validation: must be a positive integer > 0.
10. Toggle event registration status (Open <-> Closed).
11. CSV export of registrations.
"""

import pytest
from app import app, ADMIN_USERNAME, ADMIN_PASSWORD
from services import event_service, registration_service


@pytest.fixture(autouse=True)
def reset_in_memory_state():
    event_service.reset_events()
    registration_service.reset_registrations()
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "test-csrf-token"
        yield client


@pytest.fixture
def auth_admin_client(client):
    """Client with an active authenticated admin session."""
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "test-csrf-token"
        sess["admin_logged_in"] = True
        sess["admin_user"] = ADMIN_USERNAME
    return client


def test_admin_login_success(client):
    """Test successful administrator authentication."""
    res = client.post("/admin/login", data={
        "csrf_token": "test-csrf-token",
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD
    }, follow_redirects=False)

    assert res.status_code == 302
    assert "/admin/dashboard" in res.headers["Location"]

    # Verify session
    with client.session_transaction() as sess:
        assert sess.get("admin_logged_in") is True
        assert sess.get("admin_user") == ADMIN_USERNAME


def test_admin_login_invalid_credentials(client):
    """Test authentication failure on invalid credentials."""
    res = client.post("/admin/login", data={
        "csrf_token": "test-csrf-token",
        "username": "wrong_user",
        "password": "wrong_password"
    })
    assert res.status_code == 200
    assert b"Invalid administrator credentials" in res.data

    with client.session_transaction() as sess:
        assert sess.get("admin_logged_in") is not True


def test_admin_logout(auth_admin_client):
    """Test admin logout cleans session."""
    res = auth_admin_client.get("/admin/logout", follow_redirects=True)
    assert res.status_code == 200
    assert b"safely logged out" in res.data

    with auth_admin_client.session_transaction() as sess:
        assert sess.get("admin_logged_in") is None


def test_unauthorized_access_to_admin_routes(client):
    """Ensure unauthorized visitors are redirected to admin login."""
    protected_urls = [
        "/admin/dashboard",
        "/admin/events/create",
        "/admin/events/edit/1",
        "/admin/events/1/attendees",
        "/admin/registrations/export"
    ]
    for url in protected_urls:
        res = client.get(url, follow_redirects=False)
        assert res.status_code == 302
        assert "/admin/login" in res.headers["Location"]


def test_admin_create_event_and_homepage_visibility(auth_admin_client, client):
    """
    Ensure admin can create an event and that it immediately appears on the
    student homepage without restarting the server.
    """
    new_event_payload = {
        "csrf_token": "test-csrf-token",
        "title": "Quantum Computing Symposium 2026",
        "category": "Technical",
        "date": "2026-11-20",
        "time": "11:00 AM - 03:00 PM",
        "venue": "Science Block Hall 4",
        "description": "Cutting-edge quantum information theory, qubits, and quantum algorithm simulations.",
        "capacity": 80,
        "registration_deadline": "2026-11-19",
        "is_open": "1"
    }

    create_res = auth_admin_client.post("/admin/events/create", data=new_event_payload, follow_redirects=True)
    assert create_res.status_code == 200
    assert b"Quantum Computing Symposium 2026" in create_res.data

    # Now verify on the public Student Homepage (unauthenticated client)
    home_res = client.get("/")
    assert home_res.status_code == 200
    assert b"Quantum Computing Symposium 2026" in home_res.data
    assert b"Science Block Hall 4" in home_res.data
    assert b"80 seats available" in home_res.data


def test_admin_edit_event(auth_admin_client):
    """Test updating existing event attributes."""
    edit_payload = {
        "csrf_token": "test-csrf-token",
        "title": "Tech Fest 2026 — Expanded Edition",
        "category": "Technical",
        "date": "2026-11-25",
        "time": "09:00 AM - 06:00 PM",
        "venue": "Grand Convention Center",
        "description": "Expanded technical competition arena.",
        "capacity": 120,
        "registration_deadline": "2026-11-24",
        "is_open": "1"
    }
    res = auth_admin_client.post("/admin/events/edit/1", data=edit_payload, follow_redirects=True)
    assert res.status_code == 200
    assert b"updated successfully" in res.data

    # Verify updated values in service
    updated = event_service.get_event("1")
    assert updated["title"] == "Tech Fest 2026 — Expanded Edition"
    assert updated["capacity"] == 120
    assert updated["venue"] == "Grand Convention Center"


def test_admin_capacity_cannot_be_less_than_registered(auth_admin_client, client):
    """
    CRITICAL RULE:
    Do not allow capacity to be reduced below the number of active registrations.
    """
    # Register 2 students for Event 1
    for name, email in [("Student A", "a@college.edu"), ("Student B", "b@college.edu")]:
        client.post("/register/1", data={
            "csrf_token": "test-csrf-token",
            "student_name": name,
            "college_email": email,
            "department": "Computer Science & Engineering"
        })

    ev = event_service.get_event("1", registration_service.get_registration_counts_by_event())
    assert ev["registered_count"] == 2

    # Attempt to reduce capacity to 1 (which is less than 2 registered)
    res = auth_admin_client.post("/admin/events/edit/1", data={
        "csrf_token": "test-csrf-token",
        "title": ev["title"],
        "category": ev["category"],
        "date": ev["date"],
        "time": ev["time"],
        "venue": ev["venue"],
        "description": ev["description"],
        "capacity": 1,  # ILLEGAL: 1 < 2
        "is_open": "1"
    })
    assert b"Capacity cannot be reduced to 1 because 2 students are already registered" in res.data

    # Verify capacity was NOT reduced
    ev_check = event_service.get_event("1")
    assert ev_check["capacity"] == 50


def test_admin_capacity_must_be_positive_integer(auth_admin_client):
    """Test capacity validation rejects 0 or negative numbers."""
    res = auth_admin_client.post("/admin/events/create", data={
        "csrf_token": "test-csrf-token",
        "title": "Bad Capacity Event",
        "category": "Workshop",
        "date": "2026-12-10",
        "venue": "Hall B",
        "capacity": -10,
        "is_open": "1"
    })
    assert b"Capacity must be a positive integer" in res.data


def test_admin_toggle_event_status(auth_admin_client):
    """Test toggling event registration status open and closed."""
    # Initially Event 1 is open
    ev1 = event_service.get_event("1")
    assert ev1["is_open"] is True

    # Toggle to closed
    res = auth_admin_client.post("/admin/events/1/toggle-status", data={
        "csrf_token": "test-csrf-token"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Event registration successfully closed" in res.data

    ev1_closed = event_service.get_event("1")
    assert ev1_closed["is_open"] is False

    # Toggle back to open
    res2 = auth_admin_client.post("/admin/events/1/toggle-status", data={
        "csrf_token": "test-csrf-token"
    }, follow_redirects=True)
    assert res2.status_code == 200
    assert b"Event registration successfully opened" in res2.data

    ev1_open = event_service.get_event("1")
    assert ev1_open["is_open"] is True


def test_admin_csv_export(auth_admin_client, client):
    """Test CSV export generates valid CSV content with registration records."""
    # Create a registration first
    client.post("/register/1", data={
        "csrf_token": "test-csrf-token",
        "student_name": "Export Student",
        "college_email": "export.student@college.edu",
        "department": "Information Technology"
    })

    res = auth_admin_client.get("/admin/registrations/export")
    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert "attachment; filename=CollegeConnect_Registrations_" in res.headers["Content-Disposition"]
    csv_text = res.data.decode("utf-8")
    assert "Reference ID,Student Name,College Email,Department" in csv_text
    assert "Export Student" in csv_text
    assert "export.student@college.edu" in csv_text

