import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Allow imports from hacklog package and legacy flat modules.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_HACKLOG_DIR = os.path.join(_REPO_ROOT, "hacklog")
for _path in (_REPO_ROOT, _HACKLOG_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from entities import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def _database_url() -> str:
    return os.environ.get("HACKLOG_DB_URL") or config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
