"""Database engine, session handling and the declarative Base."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import DATABASE_URL, DB_STATEMENT_TIMEOUT_MS

# Predictable constraint/index names make future migrations (drop/alter) straightforward.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class UTCDateTime(TypeDecorator):
    """Always hand back timezone-aware UTC datetimes (SQLite would otherwise return naive ones)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def make_engine(url: str, *, statement_timeout_ms: int | None = None) -> Engine:
    kwargs: dict = {
        "pool_pre_ping": True,     # quietly replaces connections that went stale
        "hide_parameters": True,   # never put query VALUES (names, e-mails...) into error messages or logs
    }
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql") and statement_timeout_ms:
        # Server-side safety limits for every connection of the running app.
        kwargs["connect_args"] = {"options": f"-c statement_timeout={int(statement_timeout_ms)} "
                                             f"-c idle_in_transaction_session_timeout={int(statement_timeout_ms) * 4}"}
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless asked; PostgreSQL always enforces them.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


engine = make_engine(DATABASE_URL, statement_timeout_ms=DB_STATEMENT_TIMEOUT_MS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one session per request, always closed afterwards."""
    with SessionLocal() as db:
        yield db


def describe_url() -> str:
    """The database URL with the password hidden, safe to print or log."""
    return engine.url.render_as_string(hide_password=True)
