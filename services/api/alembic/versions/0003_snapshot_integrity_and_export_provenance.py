"""Add snapshot integrity manifest and export provenance columns

Revision ID: 0003_snapshot_integrity_and_export_provenance
Revises: 0002_revision_fingerprint_and_serp_provenance
Create Date: 2026-11-21 20:36:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_snapshot_integrity_and_export_provenance"
down_revision = "0002_revision_fingerprint_and_serp_provenance"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def _add_column_if_missing(inspector: sa.Inspector, table_name: str, column: sa.Column) -> None:
    if not _has_column(inspector, table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "research_batches" in tables:
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("import_seq", sa.Integer(), nullable=False, server_default="0"),
        )
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("target_keyword", sa.String(300), nullable=False, server_default=""),
        )
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("keyword_binding_source", sa.String(40), nullable=False, server_default="COLUMN"),
        )
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("source_observation_at", sa.DateTime(timezone=True), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("source_file_sha256", sa.String(64), nullable=False, server_default=""),
        )
        # Legacy batches intentionally remain NULL -> classified UNVERIFIED until explicitly revalidated
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("manifest_sha256", sa.String(64), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "research_batches",
            sa.Column("integrity_status", sa.String(32), nullable=False, server_default="UNVERIFIED"),
        )

    if "exports" in tables:
        _add_column_if_missing(
            inspector,
            "exports",
            sa.Column("evidence_state_hash", sa.String(64), nullable=False, server_default=""),
        )
        _add_column_if_missing(
            inspector,
            "exports",
            sa.Column("brief_fingerprints_json", sa.Text(), nullable=False, server_default="{}"),
        )
        _add_column_if_missing(
            inspector,
            "exports",
            sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _add_column_if_missing(
            inspector,
            "exports",
            sa.Column("superseded_reason", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    raise RuntimeError(
        "FINZ_UNSUPPORTED_DOWNGRADE: Forward-only SQLite migration 0003 cannot be downgraded in-place. "
        "Restore a verified pre-migration SQLite backup from data/backups/ instead."
    )
