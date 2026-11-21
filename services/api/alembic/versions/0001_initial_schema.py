"""Initial FinZ SEO Workbench V1.6 schema (25 tables)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-21 19:00:00
"""
from __future__ import annotations

from alembic import op

from app.db import Base
import app.models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
