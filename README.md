# CollegeConnect — AWS-integrated edition

**Start here:** [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) contains the complete VPC + EC2 + RDS + IAM CloudFormation and deployment instructions. The code does **not** create AWS resources automatically merely by being downloaded.

This edition preserves the original frontend/routes and adds SQL persistence with `STORAGE_BACKEND=sql` (Amazon RDS MySQL), a TLS-verified database connection, SQL integration tests, and EC2 Nginx/Gunicorn deployment configuration. `STORAGE_BACKEND=memory` retains the original local development behavior and unit tests.

**Safety:** `.env` and secrets have deliberately been excluded from this archive. The original in-memory README below documents the pre-cloud version. Do not deploy real student data until email ownership verification and HTTPS are implemented.

---

# CollegeConnect — College Event Registration System

> **Tagline:** *Events. Learn. Grow.*  
> **Architecture:** Modular Python Flask backend with Jinja2 templates, modern responsive UI design, and an in-memory service repository layer ready for future SQL database and cloud deployment.

---

## 📖 1. Project Overview & Abstract

### Abstract
**CollegeConnect** is a college event management and registration portal designed for universities and academic institutions. The platform bridges the gap between campus event coordinators and students by offering a clean, responsive web interface where students can discover upcoming symposiums, hackathons, technical workshops, and cultural nights, reserve their seats, and track their bookings with unique reference codes. Concurrently, campus administrators are equipped with a password-protected dashboard to manage seat allocations, publish new events, monitor live registration numbers, and export attendee rosters.

### Problem Statement
In many colleges and universities, event registration is still handled through disjointed physical forms, spreadsheets, or third-party links that fail to enforce strict seat capacities or prevent accidental duplicate student submissions. Furthermore, students often lack a single portal to look up their registered activities. **CollegeConnect** solves this by providing a unified web solution with centralized in-memory validation rules (duplicate registration prevention, capacity enforcement, and registration status toggling) coupled with a modern, university-branded user experience.

### Key Objectives
1. **Student Accessibility:** Allow students to browse campus events, filter by category (Technical, Cultural, Workshop, etc.), search by keyword, and complete quick registration in under a minute.
2. **Strict In-Memory Business Logic:** Enforce duplicate registration prevention based on normalized email addresses, real-time seat availability calculation, and capacity locking.
3. **Administrator Governance:** Provide an authenticated control panel with live KPI metrics, dynamic event creation/editing, and attendee roster management with CSV export capabilities.
4. **Clean Handoff Architecture:** Keep routes and UI completely isolated from data storage details, enabling teammates to seamlessly plug in SQL databases and AWS deployment later.

---

## ✨ 2. Key Features

### Student Portal
- **Modern Hero & Brand Identity:** University theme with deep navy, royal purple gradients, and soft lavender accents matching campus aesthetics.
- **Dynamic Event Discovery:** Real-time event cards with category tags, date/venue metadata, live remaining seats, and registration status badges.
- **Interactive Search & Category Filters:** Instantly filter events by *All*, *Technical*, *Cultural*, *Workshop*, *Hackathon*, or search by keyword.
- **Robust Registration Flow:**
  - Validates full name, email format, and college academic departments.
  - Prevents double submissions with button-disabling loading states.
  - Retains form inputs upon validation failure so students do not need to retype their details.
- **Duplicate Registration Prevention:**
  - Normalizes email addresses (strips whitespace and converts to lowercase).
  - Strictly prevents the same student from registering for the same event twice.
  - Permits the same student to register for multiple distinct events.
  - Duplicate attempts never decrement seat counts or inflate attendee records.
- **Registration Success Confirmation:**
  - Redirect-after-POST pattern to prevent accidental duplicate bookings on page refresh.
  - Displays student details, event information, and generates a unique reference code (e.g., `CC-2026-AB12CD`) with one-click copy functionality.
- **My Registrations Lookup:**
  - Look up registered campus events using college email.
  - Displays only matching registrations and hides other students' private data.

### Administrator Portal
- **Secure Authentication:**
  - Session-backed login protected by an `@admin_required` decorator.
  - Configurable credentials via environment variables with safe development defaults.
  - Automatic CSRF protection across state-changing forms.
- **Live KPI Dashboard:**
  - Real-time counters for Total Events, Total Registrations, Available Seats, and Full/Closed Events.
- **Event Lifecycle Management:**
  - Create new events with titles, categories, dates, venues, descriptions, and seat capacities.
  - Edit existing events with strict validation (capacity cannot be reduced below current active registrations).
  - Instant One-Click Toggle to Open or Close event registration.
  - Newly published events immediately appear on the student homepage without server restarts.
- **Attendee Management & CSV Export:**
  - Searchable registration table with event filters.
  - Event-specific attendee roster pages.
  - Instant CSV file export of attendee rosters.

---

## 🛠️ 3. Technologies Used

- **Backend:** Python 3.10+ / 3.13, Flask 3.1
- **Templating:** Jinja2
- **Frontend:** HTML5, Modern CSS3 (CSS Variables, Flexbox, Grid), JavaScript (Vanilla ES6)
- **Security:** CSRF Tokens, Secure Sessions, Input Sanitization & Regex Normalization
- **Testing:** Pytest (19 automated unit and integration tests)

---

## 📐 4. Architecture & Request Flow

```
[ Student / Administrator Browser ]
               │
        HTTP GET / POST
               │
               ▼
       [ Flask Router: app.py ]
         ├─ CSRF Token Validation
         ├─ Session Authentication Check (@admin_required)
         └─ Input Normalization & Form Validation
               │
               ▼
     [ Service Layer (services/) ]
         ├─ event_service.py       <── In-memory event collection & seat calculations
         └─ registration_service.py <── In-memory registration records, capacity checks,
                                        and duplicate registration prevention
               │
               ▼
    [ Jinja2 HTML Templates (templates/) ]
         └─ Rendered HTML + SVG Assets + CSS (static/)
```

---

## 📁 5. Project Directory Structure

```
CollegeConnect/
├── app.py                         # Main Flask application and HTTP route handlers
├── services/
│   ├── __init__.py                # Services module marker
│   ├── event_service.py           # Event retrieval, creation, editing, and capacity logic
│   └── registration_service.py    # Registration rules, duplicate checks, and KPIs
├── templates/
│   ├── base.html                  # Global layout with responsive navbar, flash alerts, and footer
│   ├── index.html                 # Student homepage: hero banner, search, filters, event cards
│   ├── register.html              # Event registration form with real-time field validation
│   ├── registration_success.html  # Success confirmation card with copyable reference code
│   ├── my_registrations.html      # Email-based student booking lookup
│   ├── admin_login.html           # Administrator login portal
│   ├── admin_dashboard.html       # Admin control panel with KPI cards and registration tables
│   ├── admin_event_form.html      # Reusable form for creating and editing campus events
│   ├── admin_attendees.html       # Event-specific student attendee roster
│   └── error.html                 # Custom 400, 404, and 500 error pages
├── static/
│   ├── css/
│   │   └── style.css              # Custom styling, color system, and responsive breakpoints
│   ├── js/
│   │   └── app.js                 # Double-submit prevention, clipboard copy, mobile nav toggle
│   └── images/
│       ├── logo.svg               # CollegeConnect graduation cap brand logo
│       ├── hero-illustration.svg  # Campus silhouette and student banner illustration
│       ├── tech-fest.svg          # Tech Fest card graphic
│       ├── cultural-fest.svg      # Cultural Night card graphic
│       ├── hackathon.svg          # CodeSprint Hackathon card graphic
│       ├── web-dev.svg            # Web Development Workshop card graphic
│       ├── ai-cloud.svg           # AI & Cloud Computing card graphic
│       └── success-envelope.svg   # Confirmation envelope and checkmark graphic
├── tests/
│   ├── test_registration.py       # Automated tests for registration, duplicates, capacity
│   └── test_admin.py              # Automated tests for admin auth, event CRUD, and CSV export
├── requirements.txt               # Python package dependencies
├── .env.example                   # Template for environment variables
├── .env                           # Local environment configuration (development)
├── .gitignore                     # Git ignore rules for virtual environments and caches
└── README.md                      # Comprehensive project documentation
```

---

## 🚀 6. Installation & Local Setup

### Prerequisites
- Python 3.10 or higher installed on your machine.
- `pip` package manager.

### Step 1: Clone or Navigate to the Project Directory
```bash
cd D:\CollegeConnect
```

### Step 2: Create and Activate a Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### On Windows (Command Prompt):
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

#### On Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to create your local `.env` file:

```bash
# On Windows:
copy .env.example .env

# On Linux / macOS:
cp .env.example .env
```

---

## 🌐 7. Running the Application

To launch the local development server:

```bash
python app.py
```

### Accessing the Website:
Open your browser and navigate to:
```
http://127.0.0.1:5000/
```

### Administrator Demo Credentials:
- **Admin Login URL:** `http://127.0.0.1:5000/admin/login`
- **Default Username:** `admin`
- **Default Password:** `admin@collegeconnect2026`

*(You can customize these credentials in your `.env` file via `ADMIN_USERNAME` and `ADMIN_PASSWORD`)*.

---

## 🧪 8. Running Automated Tests

CollegeConnect comes with a comprehensive automated test suite covering all critical workflows:

```bash
python -m pytest tests/ -v
```

### Summary of Tested Behaviors:
1. `test_successful_registration`: Valid registration creation and reference code generation.
2. `test_missing_fields_validation`: Required field checks and error highlighting.
3. `test_invalid_email_format`: Rejection of malformed email strings.
4. `test_duplicate_registration_same_event_prevented`: Verifies that a student cannot register twice for the same event and that seats/counts remain unchanged.
5. `test_same_email_registers_for_two_different_events`: Ensures students can participate in multiple campus events.
6. `test_event_capacity_reached_prevents_registration`: Enforces strict maximum attendee limit.
7. `test_closed_event_prevents_registration`: Blocks registration attempts on closed events.
8. `test_nonexistent_event_redirects`: Safe redirect and error handling for bad event IDs.
9. `test_my_registrations_email_lookup_matches_only_student`: Verifies privacy of email lookup.
10. `test_admin_login_success`: Authenticated session creation.
11. `test_admin_login_invalid_credentials`: Denial of unauthorized login attempts.
12. `test_admin_logout`: Clean session invalidation.
13. `test_unauthorized_access_to_admin_routes`: Protected route guarding.
14. `test_admin_create_event_and_homepage_visibility`: Immediate homepage synchronization of newly created events.
15. `test_admin_edit_event`: Event property updates.
16. `test_admin_capacity_cannot_be_less_than_registered`: Enforces rule that capacity cannot be reduced below existing confirmed registrations.
17. `test_admin_capacity_must_be_positive_integer`: Rejects negative/zero capacity values.
18. `test_admin_toggle_event_status`: Quick open/close toggle functionality.
19. `test_admin_csv_export`: Clean CSV file generation with proper headers and data.

---

## ⚠️ 9. Known Limitations

- **In-Memory Storage Scope:** Data is held in Python in-memory structures (`_EVENTS` in `services/event_service.py` and `_REGISTRATIONS` in `services/registration_service.py`).
- **Server Restart:** All newly registered students and created events will reset to the seeded defaults when the Python process is restarted.
- **Process Concurrency:** In-memory storage is thread-safe within a single Python process using `threading.Lock`. If running multiple worker processes (e.g. `gunicorn -w 4`), storage must be replaced with a shared database as described below.

---

## 🤝 10. Teammate Handoff Guide: SQL & AWS Integration

> **Note for Teammate:**  
> The routes in `app.py` and the Jinja2 templates in `templates/` are **completely decoupled** from storage mechanics. You do not need to rewrite the UI, form handlers, or route signatures. Follow the instructions below to integrate persistence and cloud deployment.

### Where to Connect SQL Persistence:
1. **Module to Modify:**
   - [`services/event_service.py`](file:///d:/CollegeConnect/services/event_service.py): Replace `_EVENTS` dictionary reads/writes with SQL queries or SQLAlchemy ORM operations for your `events` table.
   - [`services/registration_service.py`](file:///d:/CollegeConnect/services/registration_service.py): Replace `_REGISTRATIONS` dictionary reads/writes with SQL queries or SQLAlchemy ORM operations for your `registrations` table.
2. **Key Constraints to Enforce in SQL:**
   - Create a `UNIQUE (event_id, email)` constraint on the registration table to enforce duplicate registration prevention at the database engine level.
   - Run seat reservations inside a database transaction (`SELECT ... FOR UPDATE` or serializable isolation) to guarantee zero overbooking during concurrent traffic spikes.
3. **Database Environment Configuration:**
   - Add your connection string (e.g. `DATABASE_URL=mysql+pymysql://user:pass@host/collegeconnect` or PostgreSQL) to `.env` and load it inside the services module.

### Where to Connect AWS Deployment:
1. **Static Files & Assets:**
   - The contents of `static/` (CSS, JavaScript, and SVG images) can either be served directly via Nginx on EC2 or uploaded to an Amazon S3 bucket with CloudFront CDN distribution.
2. **Application Server:**
   - Deploy `app.py` using a production WSGI server such as Gunicorn (`gunicorn -w 4 -b 0.0.0.0:5000 app:app`) on an EC2 instance behind an Application Load Balancer (ALB).
3. **Secrets Management:**
   - Replace the demo values in `.env` with AWS Secrets Manager or Systems Manager (SSM) Parameter Store for `SECRET_KEY`, `ADMIN_PASSWORD`, and database credentials.

