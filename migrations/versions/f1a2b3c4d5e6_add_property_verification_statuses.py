"""add property and owner verification statuses

Revision ID: f1a2b3c4d5e6
Revises: e89bf52ac013
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e89bf52ac013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("phone_number", sa.String(length=30), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "identity_verification_status",
            sa.String(length=20),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "users",
        sa.Column("identity_verification_reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("identity_verification_reviewed_by_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone_verification_status",
            sa.String(length=20),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "users",
        sa.Column("phone_verification_reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("phone_verification_reviewed_by_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "properties",
        sa.Column(
            "ownership_verification_status",
            sa.String(length=20),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column(
        "properties",
        sa.Column("ownership_verification_reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("ownership_verification_reviewed_by_id", sa.Integer(), nullable=True),
    )
    op.add_column("properties", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE properties SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column(
        "properties",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )

    op.create_foreign_key(
        "fk_users_identity_verification_reviewer",
        "users",
        "users",
        ["identity_verification_reviewed_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_phone_verification_reviewer",
        "users",
        "users",
        ["phone_verification_reviewed_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_properties_ownership_verification_reviewer",
        "properties",
        "users",
        ["ownership_verification_reviewed_by_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_properties_ownership_verification_reviewer", "properties", type_="foreignkey"
    )
    op.drop_constraint("fk_users_phone_verification_reviewer", "users", type_="foreignkey")
    op.drop_constraint("fk_users_identity_verification_reviewer", "users", type_="foreignkey")
    op.drop_column("properties", "updated_at")
    op.drop_column("properties", "ownership_verification_reviewed_by_id")
    op.drop_column("properties", "ownership_verification_reviewed_at")
    op.drop_column("properties", "ownership_verification_status")
    op.drop_column("users", "phone_verification_reviewed_by_id")
    op.drop_column("users", "phone_verification_reviewed_at")
    op.drop_column("users", "phone_verification_status")
    op.drop_column("users", "identity_verification_reviewed_by_id")
    op.drop_column("users", "identity_verification_reviewed_at")
    op.drop_column("users", "identity_verification_status")
    op.drop_column("users", "phone_number")