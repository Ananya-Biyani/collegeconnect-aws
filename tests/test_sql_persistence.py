"""SQL adapter tests run locally against SQLite, no AWS account necessary.
Actual RDS TLS and MySQL row-lock behavior must be verified during deployment.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from services import sql_db, sql_event_service as events, sql_registration_service as regs


@pytest.fixture
def sql_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///" + str(tmp_path / "collegeconnect.db"))
    monkeypatch.delenv("DB_SSL_CA", raising=False)
    sql_db.get_engine.cache_clear()
    sql_db.initialize_schema()
    yield
    sql_db.get_engine().dispose()
    sql_db.get_engine.cache_clear()


def test_sql_seed_and_persistence_after_reconnect(sql_storage):
    assert len(events.list_events()) == 5
    ev = events.get_event("1")
    reg = regs.register_student(ev, "Cloud Student", " CLOUD@college.edu ", "Information Technology")
    assert reg["email"] == "cloud@college.edu"
    assert events.get_event("1", regs.get_registration_counts_by_event())["registered_count"] == 1
    sql_db.get_engine().dispose()
    sql_db.get_engine.cache_clear()
    assert regs.get_registration_by_ref(reg["reference_id"])["student_name"] == "Cloud Student"
    assert len(events.list_events()) == 5


def test_sql_duplicate_closed_and_capacity(sql_storage):
    ev = events.create_event({"title": "Tiny event", "venue": "Lab", "date": "2026-12-01", "capacity": 1})
    regs.register_student(ev, "A Student", "a@college.edu", "Information Technology")
    with pytest.raises(regs.DuplicateRegistrationError):
        regs.register_student(ev, "A Student", "a@college.edu", "Information Technology")
    with pytest.raises(regs.EventFullError):
        regs.register_student(ev, "B Student", "b@college.edu", "Information Technology")
    assert events.toggle_event_status(ev["id"]) is False
    with pytest.raises(regs.EventClosedError):
        regs.register_student(ev, "C Student", "c@college.edu", "Information Technology")
    with pytest.raises(ValueError):
        events.update_event(ev["id"], {"capacity": 0})


def test_sql_admin_event_edit_and_kpis(sql_storage):
    ev = events.create_event({"title": "Old", "venue": "Room A", "date": "2026-12-01", "capacity": 3})
    updated = events.update_event(ev["id"], {"title": "New", "capacity": 4})
    assert updated["title"] == "New"
    assert events.get_event(ev["id"])["capacity"] == 4
    assert regs.get_kpis(events.list_events())["total_events"] == 6
