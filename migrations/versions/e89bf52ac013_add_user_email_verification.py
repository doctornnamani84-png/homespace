"""add user email verification

Revision ID: e89bf52ac013
Revises: d2b2a4c9f013
Create Date: 2026-10-04

"""
from alembic import op
import sqlalchemy as sa


revision = "e89bf52ac013"
down_revision = "d2b2a4c9f013"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("email_verified")