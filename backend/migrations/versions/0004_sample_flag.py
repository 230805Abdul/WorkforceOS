"""is_sample: mark records that came from the seed script so they are always distinguishable from real data

Databases created before this migration may already contain the original sample jobs and candidates (loaded by the
old seed script). They are recognised by their well-known titles / e-mail addresses and flagged; anything else you
created yourself stays unflagged (is_sample = false). Departments created by migration 0002 from existing job data
stay unflagged too: jobs you created may point at them.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ("departments", "jobs", "candidates", "employees")

SAMPLE_JOB_TITLES = [
    "Senior Backend Engineer", "Frontend Engineer", "Product Designer", "Product Manager, Workforce Planning",
    "Account Executive", "People Operations Coordinator", "Content Marketing Intern", "Financial Analyst",
]
SAMPLE_CANDIDATE_EMAILS = [
    "amara.okafor@example.com", "daniel.weber@example.com", "priya.raman@example.com", "lucas.moreau@example.com",
    "sofia.martins@example.com", "ethan.brooks@example.com", "mei.chen@example.com", "omar.haddad@example.com",
    "hannah.fischer@example.com", "tomas.rivera@example.com", "grace.kimani@example.com", "noah.patel@example.com",
    "isabella.rossi@example.com", "kenji.watanabe@example.com",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("is_sample", sa.Boolean(), server_default=sa.false(), nullable=False))

    op.execute(
        sa.text("UPDATE jobs SET is_sample = :yes WHERE title IN :titles").bindparams(
            sa.bindparam("yes", True), sa.bindparam("titles", SAMPLE_JOB_TITLES, expanding=True)
        )
    )
    op.execute(
        sa.text("UPDATE candidates SET is_sample = :yes WHERE lower(email) IN :emails").bindparams(
            sa.bindparam("yes", True), sa.bindparam("emails", SAMPLE_CANDIDATE_EMAILS, expanding=True)
        )
    )


def downgrade() -> None:
    # Plain DROP COLUMN (SQLite >= 3.35 supports it). A "batch" rebuild would silently lose the lower(email)/lower(name)
    # unique indexes on SQLite, because they are expression indexes that SQLite's batch mode cannot copy.
    for table in reversed(TABLES):
        op.drop_column(table, "is_sample")
