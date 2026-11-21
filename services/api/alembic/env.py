from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, pool

from app.config import ensure_data_dirs, settings
from app.db import BackupError, Base, backup_database, resolve_sqlite_db_path
import app.models  # noqa: F401

logger = logging.getLogger("finz.alembic")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    ensure_data_dirs()
    return settings.database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _has_pending_migrations(connection) -> bool:
    script = ScriptDirectory.from_config(config)
    heads = set(script.get_heads())
    mig_ctx = MigrationContext.configure(connection)
    current = set(mig_ctx.get_current_heads())
    return current != heads


def run_migrations_online() -> None:
    url = get_url()
    effective_db_path = resolve_sqlite_db_path(url)
    # Check existence & non-emptiness BEFORE SQLAlchemy opens the SQLite file!
    db_existed_before = effective_db_path.exists() and effective_db_path.stat().st_size > 0
    if effective_db_path.parent:
        effective_db_path.parent.mkdir(parents=True, exist_ok=True)

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Check pending migration on a separate read-only connection so we don't open an
    # uncommitted outer SQLAlchemy 2.0 transaction on the migration connection.
    with connectable.connect() as check_conn:
        pending = _has_pending_migrations(check_conn)

    if pending:
        if db_existed_before:
            # Fail closed if online backup of the ACTUAL target SQLite DB cannot complete
            backup_path = backup_database(
                reason="pre_migration",
                source_path=effective_db_path,
                verify=True,
            )
            if backup_path is None or not backup_path.exists():
                raise BackupError(
                    f"Sao lưu trước migration không tạo được bản sao hợp lệ cho {effective_db_path}."
                )
        else:
            logger.info(
                "Fresh SQLite bootstrap at %s — skipping pre-migration backup (no legacy DB to protect).",
                effective_db_path,
            )

    with connectable.begin() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
