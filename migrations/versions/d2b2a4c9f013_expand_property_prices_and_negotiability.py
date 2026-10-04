"""expand property prices and add negotiability

Revision ID: d2b2a4c9f013
Revises: c5eab7d92431
Create Date: 2026-10-04

"""
from alembic import op
import sqlalchemy as sa


revision = "d2b2a4c9f013"
down_revision = "c5eab7d92431"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("properties", schema=None) as batch_op:
        batch_op.alter_column(
            "price_per_night",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Numeric(15, 2),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "monthly_rent",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Numeric(15, 2),
            existing_nullable=True,
        )
        batch_op.add_column(
            sa.Column("price_negotiable", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade():
    with op.batch_alter_table("properties", schema=None) as batch_op:
        batch_op.drop_column("price_negotiable")
        batch_op.alter_column(
            "monthly_rent",
            existing_type=sa.Numeric(15, 2),
            type_=sa.Numeric(10, 2),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "price_per_night",
            existing_type=sa.Numeric(15, 2),
            type_=sa.Numeric(10, 2),
            existing_nullable=True,
        )