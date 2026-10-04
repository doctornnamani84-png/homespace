"""add Cloudinary public ID to property videos

Revision ID: c5eab7d92431
Revises: ad3e1f60c287
Create Date: 2026-10-04

"""
from alembic import op
import sqlalchemy as sa


revision = "c5eab7d92431"
down_revision = "ad3e1f60c287"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("property_videos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("property_videos", schema=None) as batch_op:
        batch_op.drop_column("cloudinary_public_id")