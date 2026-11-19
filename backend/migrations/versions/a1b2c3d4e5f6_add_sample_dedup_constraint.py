"""add sample dedup constraint

Revision ID: a1b2c3d4e5f6
Revises: c0818da1d58c
Create Date: 2026-11-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'c0818da1d58c'
branch_labels = None
depends_on = None

def upgrade():
    # Use batch mode so the migration also works on SQLite, which cannot ALTER
    # TABLE to add constraints directly. On PostgreSQL batch mode is a no-op.
    with op.batch_alter_table("samples", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_sample_dataset_sha256", ["dataset_id", "sha256"])

def downgrade():
    with op.batch_alter_table("samples", schema=None) as batch_op:
        batch_op.drop_constraint("uq_sample_dataset_sha256", type_="unique")
