"""Create missing tables and apply safe upgrades at application startup."""

from threading import Lock

from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from database.session import engine


_SCHEMA_LOCK = Lock()
_SCHEMA_READY = False


def initialize_runtime_schema() -> None:
    """Create new tables and upgrade older databases once per process."""

    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        import models  # noqa: F401

        # New databases receive the complete schema immediately.
        # Existing databases keep all records and receive only missing fields.
        Base.metadata.create_all(bind=engine)
        upgrade_existing_schema(engine)

        _SCHEMA_READY = True
