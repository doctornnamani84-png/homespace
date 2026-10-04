"""add booking fee and Paystack reference

Revision ID: 7a2d1c9f4e61
Revises: bbb494203b3f
Create Date: 2026-10-04

"""
from alembic import op
import sqlalchemy as sa


revision = "7a2d1c9f4e61"
down_revision = "bbb494203b3f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("platform_fee", sa.Numeric(10, 2), nullable=False, server_default="0.00")
        )
        batch_op.add_column(sa.Column("paystack_reference", sa.String(length=100), nullable=True))
        batch_op.create_unique_constraint(
            "uq_bookings_paystack_reference", ["paystack_reference"]
        )


def downgrade():
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_constraint("uq_bookings_paystack_reference", type_="unique")
        batch_op.drop_column("paystack_reference")
        batch_op.drop_column("platform_fee")