"""security: append-only audit log (+ database triggers), audit:read permission, sessions.reauthenticated_at

The triggers make the database itself refuse UPDATE, DELETE and TRUNCATE on audit_events, whoever asks (including the
table owner, until they deliberately disable the trigger: see docs/SECURITY.md, "Audit retention").

Migrations are frozen snapshots: never import app code here.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=254), nullable=True),
        sa.Column("target_type", sa.String(length=30), nullable=True),
        sa.Column("target_id", sa.String(length=40), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("key_id", sa.String(length=16), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("category IN ('auth', 'user', 'role', 'employee', 'department', 'job', 'candidate', 'application', 'system', 'security')",
                           name=op.f("ck_audit_events_category_valid")),
        sa.CheckConstraint("outcome IN ('success', 'failure', 'denied')", name=op.f("ck_audit_events_outcome_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        sa.UniqueConstraint("hash", name=op.f("uq_audit_events_hash")),
    )
    for column in ("occurred_at", "category", "action", "outcome", "actor_user_id"):
        op.create_index(op.f(f"ix_audit_events_{column}"), "audit_events", [column], unique=False)
    op.create_index("ix_audit_events_target", "audit_events", ["target_type", "target_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
                    USING ERRCODE = 'insufficient_privilege';
            END $$""")
        op.execute("CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events "
                   "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()")
        op.execute("CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
                   "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()")
    else:  # SQLite (tests / quick experiments) has no TRUNCATE
        op.execute("CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
                   "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE is not allowed'); END")
        op.execute("CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
                   "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only: DELETE is not allowed'); END")

    op.add_column("sessions", sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sessions SET reauthenticated_at = created_at")

    permissions = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
                           sa.column("group", sa.String), sa.column("description", sa.String))
    op.bulk_insert(permissions, [{"code": "audit:read", "group": "Administration",
                                  "description": "View the audit log and security events, and verify its integrity"}])
    op.execute("INSERT INTO role_permissions (role_id, permission_id) "
               "SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'super_admin' AND p.code = 'audit:read'")


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'audit:read')")
    op.execute("DELETE FROM permissions WHERE code = 'audit:read'")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("reauthenticated_at")
    op.drop_table("audit_events")  # also drops its triggers
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
