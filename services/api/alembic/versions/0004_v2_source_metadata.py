"""Metadata Bộ key FinZ V2, tương thích dữ liệu cũ."""

from alembic import op
import sqlalchemy as sa

revision = "0004_v2_source_metadata"
down_revision = "0003_snapshot_integrity_and_export_provenance"
branch_labels = None
depends_on = None
COLUMNS = {
    "topic_pillars": ["notes", "legacy_code"],
    "source_keywords": [
        "funnel_stage",
        "title_match_check",
        "content_title",
        "subtopic",
        "planner_volume",
    ],
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table, columns in COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name in columns:
            if name not in existing:
                op.add_column(
                    table, sa.Column(name, sa.Text(), nullable=False, server_default="")
                )


def downgrade():
    raise RuntimeError(
        "FINZ_UNSUPPORTED_DOWNGRADE: Không hỗ trợ hạ schema để bảo vệ dữ liệu nguồn."
    )
