"""CollegeConnect Flask routes with interchangeable memory and AWS RDS SQL storage."""

import os
import csv
import io
import secrets
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    Response,
    abort
)

# SQL mode is designed for EC2 + private RDS MySQL. Memory mode retains the
# original application behavior and automated unit tests for local development.
if os.getenv("STORAGE_BACKEND", "memory").lower() == "sql":
    from services import sql_event_service as event_service
    from services import sql_registration_service as registration_service
else:
    from services import event_service
    from services import registration_service
from services.registration_service import (
    RegistrationError,
    DuplicateRegistrationError,
    EventFullError,
    EventClosedError,
    ValidationError
)

# Load environment variables
load_dotenv()

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY", "")
if os.getenv("STORAGE_BACKEND", "memory").lower() == "sql" and (not secret_key or secret_key.startswith("REPLACE_")):
    raise RuntimeError("Set a unique SECRET_KEY before running SQL/production mode.")
app.secret_key = secret_key if secret_key and not secret_key.startswith("REPLACE_") else "development-only-unsafe-secret" 
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
)

# Demo Administrator Credentials (Configurable via .env or environment)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin@collegeconnect2026")
if os.getenv("STORAGE_BACKEND", "memory").lower() == "sql" and (
    not ADMIN_PASSWORD or ADMIN_PASSWORD == "admin@collegeconnect2026" or ADMIN_PASSWORD.startswith("REPLACE_")
):
    raise RuntimeError("Set a strong, unique ADMIN_PASSWORD for SQL/production mode.")

# Seed initial sample events and demo records on startup
if os.getenv("STORAGE_BACKEND", "memory").lower() != "sql":
    event_service.seed_default_events()
    registration_service.seed_demo_registrations()


# ---------------------------------------------------------
# CSRF Protection & Context Helpers
# ---------------------------------------------------------
def generate_csrf_token():
    """Generates and stores a unique CSRF token in session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(24)
    return session["_csrf_token"]


def validate_csrf():
    """Validates the submitted CSRF token against the session."""
    token = request.form.get("csrf_token")
    if not token or token != session.get("_csrf_token"):
        abort(400, description="Invalid or missing CSRF security token.")


@app.context_processor
def inject_global_helpers():
    """Injects CSRF token and utility variables into all Jinja templates."""
    return {
        "csrf_token": generate_csrf_token,
        "current_year": datetime.now().year,
        "is_admin_logged_in": session.get("admin_logged_in", False),
        "admin_username": session.get("admin_user", ""),
        "allowed_departments": registration_service.ALLOWED_DEPARTMENTS,
        "allowed_academic_years": registration_service.ALLOWED_ACADEMIC_YEARS
    }


# ---------------------------------------------------------
# Admin Authentication Decorator
# ---------------------------------------------------------
def admin_required(f):
    """Protects admin routes; redirects to login if unauthenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Administrator login required to access that page.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
# Student Routes
# ---------------------------------------------------------
@app.route("/healthz")
def healthz():
    """Application + database reachability check for EC2 diagnostics."""
    if os.getenv("STORAGE_BACKEND", "memory").lower() == "sql":
        try:
            from services.sql_db import check_connection
            check_connection()
        except Exception:
            app.logger.exception("Database health check failed")
            return {"status": "unhealthy"}, 503
    return {"status": "ok", "storage": os.getenv("STORAGE_BACKEND", "memory")}, 200


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.route("/")
def index():
    """
    Student Homepage / Dashboard:
    Hero banner, category filter pills, event search, and live upcoming event cards.
    """
    category = request.args.get("category", "All")
    search = request.args.get("q", "").strip()

    reg_counts = registration_service.get_registration_counts_by_event()
    events = event_service.list_events(category=category, search=search, reg_counts=reg_counts)
    categories = event_service.get_categories()

    return render_template(
        "index.html",
        events=events,
        categories=categories,
        selected_category=category,
        search_query=search
    )


@app.route("/events")
def events_list():
    """Dedicated alias or full page view for events browsing."""
    return redirect(url_for("index") + "#upcoming-events")


@app.route("/register/<event_id>", methods=["GET", "POST"])
def register(event_id):
    """
    Event Registration Page:
    GET: Displays event details and registration form.
    POST: Validates inputs, checks duplicate emails and seat capacity,
          and processes student registration.
    """
    reg_counts = registration_service.get_registration_counts_by_event()
    event = event_service.get_event(event_id, reg_counts=reg_counts)

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("index"))

    form_data = {
        "student_name": "",
        "college_email": "",
        "department": "",
        "academic_year": ""
    }
    field_errors = {}

    if request.method == "POST":
        validate_csrf()

        # Capture and retain user inputs
        form_data["student_name"] = request.form.get("student_name", "").strip()
        form_data["college_email"] = request.form.get("college_email", "").strip()
        form_data["department"] = request.form.get("department", "").strip()
        form_data["academic_year"] = request.form.get("academic_year", "").strip()

        try:
            new_reg = registration_service.register_student(
                event=event,
                full_name=form_data["student_name"],
                email=form_data["college_email"],
                department=form_data["department"],
                academic_year=form_data["academic_year"]
            )
            # Redirect-after-POST pattern to prevent duplicate submissions on refresh
            return redirect(url_for("registration_success", ref_id=new_reg["reference_id"]))

        except DuplicateRegistrationError as e:
            flash(str(e), "error")
            field_errors["college_email"] = "You are already registered for this event."
            return render_template("register.html", event=event, form_data=form_data, field_errors=field_errors), 400

        except (EventFullError, EventClosedError) as e:
            flash(str(e), "error")
            return render_template("register.html", event=event, form_data=form_data, field_errors=field_errors), 400

        except ValidationError as e:
            field_errors = e.args[0] if isinstance(e.args[0], dict) else {}
            flash("Please resolve the highlighted errors in the form.", "error")
            return render_template("register.html", event=event, form_data=form_data, field_errors=field_errors), 400

        except RegistrationError as e:
            flash(str(e), "error")
            return render_template("register.html", event=event, form_data=form_data, field_errors=field_errors), 400

    return render_template("register.html", event=event, form_data=form_data, field_errors=field_errors)


@app.route("/registration-success/<ref_id>")
def registration_success(ref_id):
    """
    Registration Confirmation:
    Displays confirmed event registration reference, student details, and event summary.
    """
    reg = registration_service.get_registration_by_ref(ref_id)
    if not reg:
        flash("Registration reference not found.", "warning")
        return redirect(url_for("index"))

    return render_template("registration_success.html", registration=reg)


@app.route("/my-registrations", methods=["GET", "POST"])
def my_registrations():
    """
    Student Registrations Lookup:
    Provides an email lookup form for demonstration. Filters and displays only
    the student's registered events without exposing other students' data.
    """
    search_email = ""
    registrations = None
    has_searched = False

    if request.method == "POST":
        validate_csrf()
        search_email = request.form.get("email", "").strip()
        has_searched = True

        if not search_email:
            flash("Please enter your college email address.", "warning")
        elif not registration_service.validate_email_format(search_email):
            flash("Please enter a valid email address.", "error")
        else:
            registrations = registration_service.find_registrations_by_email(search_email)

    elif request.args.get("email"):
        search_email = request.args.get("email", "").strip()
        has_searched = True
        registrations = registration_service.find_registrations_by_email(search_email)

    return render_template(
        "my_registrations.html",
        search_email=search_email,
        registrations=registrations,
        has_searched=has_searched
    )


# ---------------------------------------------------------
# Administrator Routes
# ---------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    Administrator Login:
    Authenticates administrator against environment credentials with session creation.
    """
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        validate_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # Secure constant-time comparison against configured credentials
        if secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["admin_logged_in"] = True
            session["admin_user"] = username
            flash(f"Welcome back, Administrator!", "success")

            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid administrator credentials. Please check and try again.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Logs out the administrator and clears the active session."""
    session.pop("admin_logged_in", None)
    session.pop("admin_user", None)
    flash("You have been safely logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """
    Administrator Dashboard:
    Live KPI metrics cards, event management table, and registered students list.
    """
    search_student = request.args.get("q_student", "").strip()
    filter_event = request.args.get("filter_event", "").strip()

    reg_counts = registration_service.get_registration_counts_by_event()
    events = event_service.list_events(reg_counts=reg_counts)
    kpis = registration_service.get_kpis(events)
    registrations = registration_service.get_all_registrations(
        search=search_student,
        event_filter=filter_event
    )

    return render_template(
        "admin_dashboard.html",
        kpis=kpis,
        events=events,
        registrations=registrations,
        search_student=search_student,
        filter_event=filter_event
    )


@app.route("/admin/events/create", methods=["GET", "POST"])
@admin_required
def admin_create_event():
    """Admin: Create new event."""
    form_data = {
        "title": "",
        "category": "Technical",
        "date": "",
        "time": "10:00 AM - 04:00 PM",
        "venue": "",
        "description": "",
        "capacity": 50,
        "registration_deadline": "",
        "is_open": True
    }
    field_errors = {}

    if request.method == "POST":
        validate_csrf()
        form_data["title"] = request.form.get("title", "").strip()
        form_data["category"] = request.form.get("category", "Technical").strip()
        form_data["date"] = request.form.get("date", "").strip()
        form_data["time"] = request.form.get("time", "").strip()
        form_data["venue"] = request.form.get("venue", "").strip()
        form_data["description"] = request.form.get("description", "").strip()
        form_data["capacity"] = request.form.get("capacity", "").strip()
        form_data["registration_deadline"] = request.form.get("registration_deadline", "").strip()
        form_data["is_open"] = bool(request.form.get("is_open"))

        try:
            created = event_service.create_event(form_data)
            flash(f"Event '{created['title']}' created successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as e:
            flash(str(e), "error")
            field_errors["general"] = str(e)

    return render_template("admin_event_form.html", form_data=form_data, field_errors=field_errors, is_edit=False)


@app.route("/admin/events/edit/<event_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_event(event_id):
    """Admin: Edit an existing event."""
    reg_counts = registration_service.get_registration_counts_by_event()
    event = event_service.get_event(event_id, reg_counts=reg_counts)

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("admin_dashboard"))

    field_errors = {}
    form_data = dict(event)

    if request.method == "POST":
        validate_csrf()
        submitted = {
            "title": request.form.get("title", "").strip(),
            "category": request.form.get("category", "").strip(),
            "date": request.form.get("date", "").strip(),
            "time": request.form.get("time", "").strip(),
            "venue": request.form.get("venue", "").strip(),
            "description": request.form.get("description", "").strip(),
            "capacity": request.form.get("capacity", "").strip(),
            "registration_deadline": request.form.get("registration_deadline", "").strip(),
            "is_open": bool(request.form.get("is_open"))
        }

        try:
            event_service.update_event(
                event_id=event_id,
                data=submitted,
                current_registered_count=event["registered_count"]
            )
            flash(f"Event '{submitted['title']}' updated successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except (ValueError, KeyError) as e:
            flash(str(e), "error")
            form_data = {**event, **submitted}

    return render_template(
        "admin_event_form.html",
        event=event,
        form_data=form_data,
        field_errors=field_errors,
        is_edit=True
    )


@app.route("/admin/events/<event_id>/toggle-status", methods=["POST"])
@admin_required
def admin_toggle_event_status(event_id):
    """Admin: Toggle registration open/closed state."""
    validate_csrf()
    try:
        new_status = event_service.toggle_event_status(event_id)
        status_word = "opened" if new_status else "closed"
        flash(f"Event registration successfully {status_word}.", "info")
    except KeyError:
        flash("Event not found.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/events/<event_id>/attendees")
@admin_required
def admin_event_attendees(event_id):
    """Admin: Dedicated roster of registered attendees for a specific event."""
    reg_counts = registration_service.get_registration_counts_by_event()
    event = event_service.get_event(event_id, reg_counts=reg_counts)
    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("admin_dashboard"))

    search = request.args.get("q", "").strip()
    attendees = registration_service.list_event_attendees(event_id, search=search)

    return render_template(
        "admin_attendees.html",
        event=event,
        attendees=attendees,
        search_query=search
    )


@app.route("/admin/registrations/export")
@admin_required
def admin_export_csv():
    """Admin: Export attendee registrations to a clean downloadable CSV file."""
    event_filter = request.args.get("event_id")
    search = request.args.get("q")

    registrations = registration_service.get_all_registrations(
        search=search,
        event_filter=event_filter
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV Header
    writer.writerow([
        "Reference ID",
        "Student Name",
        "College Email",
        "Department",
        "Academic Year",
        "Event Title",
        "Event Date",
        "Event Venue",
        "Registered At",
        "Status"
    ])

    for reg in registrations:
        writer.writerow([
            reg.get("reference_id"),
            reg.get("student_name"),
            reg.get("email"),
            reg.get("department"),
            reg.get("academic_year"),
            reg.get("event_title"),
            reg.get("event_date"),
            reg.get("event_venue"),
            reg.get("registered_at"),
            reg.get("status")
        ])

    csv_data = output.getvalue()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"CollegeConnect_Registrations_{timestamp}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ---------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------
@app.errorhandler(400)
def bad_request(e):
    return render_template(
        "error.html",
        error_code=400,
        error_title="Bad Request",
        error_message=getattr(e, "description", "The request could not be processed due to invalid parameters.")
    ), 400


@app.errorhandler(404)
def page_not_found(e):
    return render_template(
        "error.html",
        error_code=404,
        error_title="Page Not Found",
        error_message="The page or event you are looking for does not exist or has been moved."
    ), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template(
        "error.html",
        error_code=500,
        error_title="Server Error",
        error_message="An unexpected error occurred while processing your request. Please try again shortly."
    ), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    app.run(host="127.0.0.1", port=port, debug=debug)

