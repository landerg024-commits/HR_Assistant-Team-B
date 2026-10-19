"""Runtime schema test for the password-reset table."""

from sqlalchemy import create_engine, inspect

import models  # noqa: F401
from database.base import Base


def test_create_all_adds_password_reset_token_table() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(bind=engine)

    assert (
        "password_reset_tokens"
        in inspect(engine).get_table_names()
    )
