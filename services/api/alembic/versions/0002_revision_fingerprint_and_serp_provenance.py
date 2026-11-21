"""Add revision fingerprints, SERP provenance columns, and mapping_revisions audit table

Revision ID: 0002_revision_fingerprint_and_serp_provenance
Revises: 0001_initial_schema
Create Date: 2026-11-21 19:57:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_revision_fingerprint_and_serp_provenance"
down_revision = "0001_initial_schema"
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

    if "evidence_rows" in tables:
        _add_column_if_missing(
            inspector,
            "evidence_rows",
            sa.Column("serp_result_type", sa.String(40), nullable=False, server_default="ORGANIC"),
        )
        _add_column_if_missing(
            inspector,
            "evidence_rows",
            sa.Column("organic_domain", sa.String(255), nullable=False, server_default=""),
        )
        _add_column_if_missing(
            inspector,
            "evidence_rows",
            sa.Column("organic_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    if "approvals" in tables:
        _add_column_if_missing(
            inspector,
            "approvals",
            sa.Column("target_revision", sa.Integer(), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "approvals",
            sa.Column("target_fingerprint", sa.String(64), nullable=True),
        )

    if "keyword_mappings" in tables:
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("logical_key", sa.String(200), nullable=False, server_default=""),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("content_fingerprint", sa.String(64), nullable=False, server_default=""),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("metrics_evidence_id", sa.String(40), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("serp_evidence_summary_json", sa.Text(), nullable=False, server_default="{}"),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("approved_revision", sa.Integer(), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("approved_fingerprint", sa.String(64), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "keyword_mappings",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if "content_briefs" in tables:
        _add_column_if_missing(
            inspector,
            "content_briefs",
            sa.Column("mapping_revision", sa.Integer(), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "content_briefs",
            sa.Column("mapping_fingerprint", sa.String(64), nullable=True),
        )
        _add_column_if_missing(
            inspector,
            "content_briefs",
            sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _add_column_if_missing(
            inspector,
            "content_briefs",
            sa.Column("eligibility_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        )

    if "mapping_revisions" not in tables:
        op.create_table(
            "mapping_revisions",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("project_id", sa.String(40), sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True),
            sa.Column("keyword_mapping_id", sa.String(40), sa.ForeignKey("keyword_mappings.id", ondelete="CASCADE"), index=True),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("content_fingerprint", sa.String(64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # Forward-only safety policy: do not drop user data columns in SQLite
    pass
