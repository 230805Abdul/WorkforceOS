"""The migrations must build exactly the schema the models describe, be reversible, and KEEP existing data."""
from alembic import command
from sqlalchemy import inspect, text

from app.db import engine
from tests.conftest import alembic_config

TABLES = {"departments", "jobs", "candidates", "applications", "employees", "activity_log", "users", "audit_events"}


def _wipe():
    command.downgrade(alembic_config(), "base")


def test_upgrade_matches_models_and_downgrade_is_clean():
    _wipe()
    command.upgrade(alembic_config(), "head")
    assert TABLES <= set(inspect(engine).get_table_names())
    command.check(alembic_config())  # raises if models and migrations have drifted apart
    command.downgrade(alembic_config(), "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(alembic_config(), "head")  # leave the database usable for the tests that follow


def test_upgrading_a_phase2_database_keeps_every_record():
    """Simulates YOUR database: revision 0001, free-text departments, sample data plus records you created."""
    _wipe()
    command.upgrade(alembic_config(), "0001")
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO jobs (title, department, location, employment_type, status, openings, description, created_at, updated_at) VALUES
            ('Senior Backend Engineer', 'Engineering', 'Remote', 'full_time', 'open', 2, 'sample job', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('My Own Job', 'Engineering', 'Lahore', 'full_time', 'open', 1, 'created by the user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('Typed Differently', 'sales', 'Karachi', 'contract', 'draft', 1, 'lower-case department', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('Second Sales Job', 'Sales', 'Remote', 'contract', 'open', 1, 'same department, other case', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('No Department', '  ', 'Remote', 'contract', 'open', 1, 'blank department', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""))
        c.execute(text("""INSERT INTO candidates (full_name, email, source, created_at) VALUES
            ('Amara Okafor', 'amara.okafor@example.com', 'linkedin', CURRENT_TIMESTAMP),
            ('My Candidate', 'me@mycompany.pk', 'referral', CURRENT_TIMESTAMP)"""))
        c.execute(text("INSERT INTO applications (candidate_id, job_id, status, created_at, updated_at) "
                       "VALUES (2, 2, 'interview', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))

    command.upgrade(alembic_config(), "head")

    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM jobs")).scalar() == 5
        assert c.execute(text("SELECT count(*) FROM candidates")).scalar() == 2
        assert c.execute(text("SELECT status FROM applications")).scalar() == "interview"
        depts = dict(c.execute(text("SELECT name, code FROM departments")).all())
        assert depts == {"Engineering": "ENG", "Sales": "SAL", "Unassigned": "UNASSI"}  # 'sales'/'Sales' merged, blank -> Unassigned
        jobs = dict(c.execute(text("SELECT j.title, d.name FROM jobs j JOIN departments d ON d.id = j.department_id")).all())
        assert jobs["My Own Job"] == "Engineering" and jobs["Typed Differently"] == "Sales" and jobs["No Department"] == "Unassigned"
        flags = dict(c.execute(text("SELECT title, is_sample FROM jobs")).all())
        assert flags["Senior Backend Engineer"] and not flags["My Own Job"]  # only known sample data is flagged
        cflags = dict(c.execute(text("SELECT email, is_sample FROM candidates")).all())
        assert cflags["amara.okafor@example.com"] and not cflags["me@mycompany.pk"]
    command.check(alembic_config())

