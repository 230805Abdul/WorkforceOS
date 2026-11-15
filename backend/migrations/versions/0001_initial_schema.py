"""initial schema: jobs, candidates, applications, activity_log

Migrations are frozen snapshots: never import app code here, and never edit this file after
it has been applied anywhere. To change the schema, create a NEW migration.

Revision ID: 0001
Revises: 
Create Date: 2026-11-09 17:33:48.907896
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('activity_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('message', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_activity_log'))
    )
    op.create_index(op.f('ix_activity_log_created_at'), 'activity_log', ['created_at'], unique=False)
    op.create_table('candidates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source IN ('careers_page', 'referral', 'linkedin', 'agency', 'other')", name=op.f('ck_candidates_source_valid')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_candidates'))
    )
    op.create_index(op.f('ix_candidates_source'), 'candidates', ['source'], unique=False)
    op.create_index('uq_candidates_email_lower', 'candidates', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('department', sa.String(length=40), nullable=False),
    sa.Column('location', sa.String(length=100), nullable=False),
    sa.Column('employment_type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('openings', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("employment_type IN ('full_time', 'part_time', 'contract', 'internship')", name=op.f('ck_jobs_employment_type_valid')),
    sa.CheckConstraint("status IN ('draft', 'open', 'closed', 'archived')", name=op.f('ck_jobs_status_valid')),
    sa.CheckConstraint('openings BETWEEN 1 AND 50', name=op.f('ck_jobs_openings_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs'))
    )
    op.create_index(op.f('ix_jobs_department'), 'jobs', ['department'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_table('applications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('applied', 'screening', 'interview', 'offer', 'hired', 'rejected')", name=op.f('ck_applications_status_valid')),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], name=op.f('fk_applications_candidate_id_candidates'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_applications_job_id_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_applications')),
    sa.UniqueConstraint('candidate_id', 'job_id', name='uq_applications_candidate_job')
    )
    op.create_index(op.f('ix_applications_candidate_id'), 'applications', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_applications_job_id'), 'applications', ['job_id'], unique=False)
    op.create_index(op.f('ix_applications_status'), 'applications', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_applications_status'), table_name='applications')
    op.drop_index(op.f('ix_applications_job_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_candidate_id'), table_name='applications')
    op.drop_table('applications')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_department'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index('uq_candidates_email_lower', table_name='candidates')
    op.drop_index(op.f('ix_candidates_source'), table_name='candidates')
    op.drop_table('candidates')
    op.drop_index(op.f('ix_activity_log_created_at'), table_name='activity_log')
    op.drop_table('activity_log')
