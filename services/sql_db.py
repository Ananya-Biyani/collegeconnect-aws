"""SQLAlchemy Core schema/connection layer for persistent MySQL (Amazon RDS).

Use STORAGE_BACKEND=sql and set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME.
DATABASE_URL is supported for local automated SQLite integration testing.
No network request or schema mutation occurs on import; run scripts/init_db.py.
"""
import os
from functools import lru_cache

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, Boolean, ForeignKey,
    UniqueConstraint, Index, create_engine, text
)
from sqlalchemy.engine import URL, make_url

metadata = MetaData()

events = Table(
    "events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("category", String(50), nullable=False),
    Column("date", String(10), nullable=False),
    Column("display_date", String(30), nullable=False),
    Column("time", String(80), nullable=False),
    Column("venue", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("registration_deadline", String(10), nullable=False),
    Column("is_open", Boolean, nullable=False, default=True),
    Column("image_url", String(255), nullable=False),
    Column("created_at", String(30), nullable=False),
)

registrations = Table(
    "registrations", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reference_id", String(48), nullable=False, unique=True),
    Column("event_id", Integer, ForeignKey("events.id", ondelete="RESTRICT"), nullable=False),
    Column("event_title", String(200), nullable=False),
    Column("event_date", String(30), nullable=False),
    Column("event_time", String(80), nullable=False),
    Column("event_venue", String(200), nullable=False),
    Column("student_name", String(200), nullable=False),
    Column("email", String(255), nullable=False),
    Column("department", String(100), nullable=False),
    Column("academic_year", String(60), nullable=False),
    Column("registered_at", String(30), nullable=False),
    Column("display_registered_at", String(50), nullable=False),
    Column("status", String(20), nullable=False, default="Confirmed"),
    UniqueConstraint("event_id", "email", name="uq_registration_event_email"),
)
Index("ix_regs_event_status", registrations.c.event_id, registrations.c.status)
Index("ix_regs_email", registrations.c.email)


def _config():
    if os.getenv("DATABASE_URL"):
        url = make_url(os.environ["DATABASE_URL"])
    else:
        missing = [name for name in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(name)]
        if missing:
            raise RuntimeError("Missing database environment variables: " + ", ".join(missing))
        url = URL.create(
            "mysql+pymysql", username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
            host=os.environ["DB_HOST"], port=int(os.getenv("DB_PORT", "3306")),
            database=os.environ["DB_NAME"],
        )

    kwargs = {"pool_pre_ping": True, "pool_recycle": 1800}
    if url.get_backend_name() == "mysql":
        ca = os.getenv("DB_SSL_CA", "")
        if not ca and os.getenv("DB_REQUIRE_TLS", "1") == "1":
            raise RuntimeError("For MySQL/RDS configure DB_SSL_CA with the AWS RDS CA bundle path")
        if ca:
            if not os.path.isfile(ca):
                raise RuntimeError("DB_SSL_CA certificate file not found: " + ca)
            kwargs["connect_args"] = {
                "ssl_ca": ca, "ssl_verify_cert": True, "ssl_verify_identity": True
            }
    return url, kwargs


@lru_cache(maxsize=1)
def get_engine():
    url, kwargs = _config()
    return create_engine(url, **kwargs)


def initialize_schema(seed=True):
    engine = get_engine()
    metadata.create_all(engine)
    if seed:
        # The original five seed events are retained, including their images and dates.
        from sqlalchemy import select, func, insert
        from services import event_service
        with engine.begin() as conn:
            count = conn.execute(select(func.count()).select_from(events)).scalar_one()
            if count == 0:
                event_service.seed_default_events()
                for event in event_service.list_events():
                    payload = {col.name: event[col.name] for col in events.columns if col.name in event}
                    payload["id"] = int(payload["id"])
                    conn.execute(insert(events).values(**payload))


def check_connection():
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1")).scalar_one()
