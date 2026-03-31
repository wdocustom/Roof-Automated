"""Alembic migration environment."""

import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models import Base  # noqa: F401 — import all models so metadata is populated

config = context.config

# Neon's connection pooler (-pooler endpoint) uses PgBouncer in transaction mode,
# which doesn't support advisory locks required by Alembic. Always use direct connection.
raw_url = settings.database_sync_url
sync_url = raw_url.replace("-pooler.", ".")
config.set_main_option("sqlalchemy.url", sync_url)

# Log connection info for debugging (mask password)
_masked = sync_url.split("@")[-1] if "@" in sync_url else "unknown"
print(f"[alembic env] Connecting to: ...@{_masked}", file=sys.stderr)
if "-pooler" in raw_url:
    print("[alembic env] Stripped -pooler from URL (using direct connection)", file=sys.stderr)
print(f"[alembic env] Models registered: {len(Base.metadata.tables)} tables", file=sys.stderr)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
