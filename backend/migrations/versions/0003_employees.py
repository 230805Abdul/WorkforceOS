"""employees: people who work here, belonging to a department (RESTRICT) and optionally linked to the candidate they were hired from"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_code", sa.String(length=20), nullable=False),
        sa.Column("first_name", sa.String(length=60), nullable=False),
        sa.Column("last_name", sa.String(length=60), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("employment_status", sa.String(length=20), nullable=False),
        sa.Column("joining_date", sa.Date(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("employment_status IN ('active', 'on_leave', 'terminated')", name=op.f("ck_employees_employment_status_valid")),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], name=op.f("fk_employees_candidate_id_candidates"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name=op.f("fk_employees_department_id_departments"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("candidate_id", name=op.f("uq_employees_candidate_id")),
        sa.UniqueConstraint("employee_code", name=op.f("uq_employees_employee_code")),
    )
    op.create_index(op.f("ix_employees_department_id"), "employees", ["department_id"], unique=False)
    op.create_index(op.f("ix_employees_employment_status"), "employees", ["employment_status"], unique=False)
    op.create_index("uq_employees_email_lower", "employees", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_employees_email_lower", table_name="employees")
    op.drop_index(op.f("ix_employees_employment_status"), table_name="employees")
    op.drop_index(op.f("ix_employees_department_id"), table_name="employees")
    op.drop_table("employees")
