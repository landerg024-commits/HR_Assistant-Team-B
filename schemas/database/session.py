"""Database engine and SQLAlchemy session factory.

Purpose:
- Build the SQLAlchemy engine from DATABASE_URL.
- Apply database-specific connection options.
- Provide reusable sessions to repositories and services.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings


def _build_connect_args(database_url: str) -> dict[str, object]:
    """Return connection arguments required by the selected database."""

    # SQLite normally restricts a connection to one thread.
    # Streamlit can use multiple execution contexts, so this is disabled.
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}

    # PostgreSQL and other engines do not need the SQLite option.
    return {}


def create_database_engine(database_url: str | None = None) -> Engine:
    """Create an SQLAlchemy engine.

    A custom URL is useful in tests. When omitted, the value from `.env`
    is used.
    """

    settings = get_settings()
    selected_url = database_url or settings.database_url

    return create_engine(
        selected_url,
        connect_args=_build_connect_args(selected_url),
        pool_pre_ping=True,  # Check stale pooled connections before use.
        future=True,
    )


# Shared application engine.
engine = create_database_engine()

# SessionFactory creates independent Session objects for each operation.
SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_session() -> Generator[Session, None, None]:
    """Yield a session and always close it afterward.

    This helper can later be used by APIs, services, or dependency systems.
    """

    session = SessionFactory()

    try:
        yield session
    finally:
        session.close()
