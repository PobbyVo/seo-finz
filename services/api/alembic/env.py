from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, pool

from app.config import ensure_data_dirs, settings
from app.db import Base, backup_database
import app.models  # noqa: F401

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
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

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
        # Fail closed if online backup cannot complete or fails integrity verification
        backup_database(reason="pre_migration")

    with connectable.begin() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
