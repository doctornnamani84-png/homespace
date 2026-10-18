"""add property discovery and safety features

Revision ID: 9b31c4e2a765
Revises: f1a2b3c4d5e6
Create Date: 2026-10-17

"""
from alembic import op
import sqlalchemy as sa


revision = "9b31c4e2a765"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("bedrooms", sa.Integer(), nullable=True))
    op.add_column(
        "properties",
        sa.Column("amenities", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("properties", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("properties", sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "property_favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "property_id", name="uq_property_favorite"),
    )
    op.create_table(
        "property_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=1200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_property_reports_status_created_at",
        "property_reports",
        ["status", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_property_reports_status_created_at", table_name="property_reports")
    op.drop_table("property_reports")
    op.drop_table("property_favorites")
    op.drop_column("properties", "longitude")
    op.drop_column("properties", "latitude")
    op.drop_column("properties", "amenities")
    op.drop_column("properties", "bedrooms")
