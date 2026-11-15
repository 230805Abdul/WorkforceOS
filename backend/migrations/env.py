"""Alembic environment: connects with the app's engine and compares against app.models."""
from logging.config import fileConfig

from alembic import context

import app.audit  # noqa: F401
import app.auth.models  # noqa: F401
import app.models  # noqa: F401  (importing registers every table on Base.metadata)
from app.config import MIGRATION_DATABASE_URL
from app.db import Base, make_engine

# Migrations run as the database OWNER (MIGRATION_DATABASE_URL, falls back to DATABASE_URL) and without the app's
# statement timeout: data migrations may legitimately take longer than a normal request.
engine = make_engine(MIGRATION_DATABASE_URL)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` prints the SQL instead of running it."""
    context.configure(url=str(engine.url), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        if is_sqlite:
            # SQLite changes tables by copying them and DROPPING the original. With foreign keys enforced, that DROP
            # would fire ON DELETE CASCADE and silently delete child rows (e.g. applications). PostgreSQL alters tables
            # in place, so this only applies to SQLite. The PRAGMA must run outside a transaction, hence the commit.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",  # SQLite can't ALTER most things directly
        )
        with context.begin_transaction():
            context.run_migrations()
        if is_sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            if broken:
                raise RuntimeError(f"Migration left {len(broken)} rows with broken foreign keys: {broken[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
