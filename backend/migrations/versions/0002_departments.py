"""departments: turn jobs.department (free text) into a real table + foreign key

DATA MIGRATION. Existing jobs are kept: every distinct department name found in `jobs.department` becomes a row in
the new `departments` table and each job is pointed at it. Nothing is deleted.

Migrations are frozen snapshots: never import app code here, and never edit this file after it has been applied.
"""
import re
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Short codes for the departments the project has always shipped with; anything else gets a derived code.
KNOWN_CODES = {"Engineering": "ENG", "Product": "PRD", "Design": "DSN", "Sales": "SAL",
               "Marketing": "MKT", "Operations": "OPS", "People": "PPL", "Finance": "FIN"}


def _code_for(name: str, taken: set[str]) -> str:
    base = KNOWN_CODES.get(name) or re.sub(r"[^A-Z0-9]", "", name.upper())[:6] or "DEPT"
    code, n = base, 2
    while code in taken:
        code = f"{base}{n}"
        n += 1
    taken.add(code)
    return code


def _name(text: str | None) -> str:
    return (text or "").strip() or "Unassigned"


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("code = upper(code)", name=op.f("ck_departments_code_uppercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("code", name=op.f("uq_departments_code")),
    )
    op.create_index("uq_departments_name_lower", "departments", [sa.text("lower(name)")], unique=True)
    op.add_column("jobs", sa.Column("department_id", sa.Integer(), nullable=True))

    # ---- move the data ----
    bind = op.get_bind()
    jobs = sa.table("jobs", sa.column("id", sa.Integer), sa.column("department", sa.String), sa.column("department_id", sa.Integer))
    departments = sa.table("departments", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("code", sa.String),
                           sa.column("description", sa.String), sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime))
    rows = bind.execute(sa.select(jobs.c.id, jobs.c.department)).all()
    now = datetime.now(timezone.utc)
    ids_by_lower: dict[str, int] = {}
    taken: set[str] = set()
    for name in sorted({_name(r.department) for r in rows}, key=lambda n: (n.lower(), n)):
        if name.lower() in ids_by_lower:  # "sales" and "Sales" are the same department
            continue
        bind.execute(departments.insert().values(name=name, code=_code_for(name, taken), description=None, created_at=now, updated_at=now))
        ids_by_lower[name.lower()] = bind.execute(sa.select(departments.c.id).where(departments.c.name == name)).scalar_one()
    for r in rows:
        bind.execute(jobs.update().where(jobs.c.id == r.id).values(department_id=ids_by_lower[_name(r.department).lower()]))

    # ---- tighten the schema ----
    with op.batch_alter_table("jobs") as batch:  # "batch" lets SQLite do ALTERs too; on PostgreSQL it is plain ALTER TABLE
        batch.drop_index("ix_jobs_department")
        batch.alter_column("department_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(op.f("fk_jobs_department_id_departments"), "departments", ["department_id"], ["id"], ondelete="RESTRICT")
        batch.create_index(op.f("ix_jobs_department_id"), ["department_id"], unique=False)
        batch.drop_column("department")


def downgrade() -> None:
    """Back to free-text departments. Department descriptions/codes are lost, names longer than 40 characters are cut."""
    op.add_column("jobs", sa.Column("department", sa.String(length=40), nullable=True))
    op.execute("UPDATE jobs SET department = (SELECT SUBSTR(d.name, 1, 40) FROM departments d WHERE d.id = jobs.department_id)")
    with op.batch_alter_table("jobs") as batch:
        batch.alter_column("department", existing_type=sa.String(length=40), nullable=False)
        batch.create_index("ix_jobs_department", ["department"], unique=False)
        batch.drop_index(op.f("ix_jobs_department_id"))
        batch.drop_constraint(op.f("fk_jobs_department_id_departments"), type_="foreignkey")
        batch.drop_column("department_id")
    op.drop_index("uq_departments_name_lower", table_name="departments")
    op.drop_table("departments")
