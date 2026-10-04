"""add verified stay reviews

Revision ID: ad3e1f60c287
Revises: 7a2d1c9f4e61
Create Date: 2026-10-04

"""
from alembic import op
import sqlalchemy as sa


revision = "ad3e1f60c287"
down_revision = "7a2d1c9f4e61"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "property_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=1200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_property_review_rating"
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index(
        op.f("ix_property_reviews_property_id"),
        "property_reviews",
        ["property_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_property_reviews_property_id"), table_name="property_reviews")
    op.drop_table("property_reviews")