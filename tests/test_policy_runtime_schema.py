"""Test that an existing database receives the new policy table."""

from sqlalchemy import create_engine, inspect

import models  # noqa: F401
from database.base import Base


def test_create_all_adds_hr_policies_table() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # Create only selected older tables first.
    models.Company.__table__.create(
        bind=engine,
        checkfirst=True,
    )
    models.Role.__table__.create(
        bind=engine,
        checkfirst=True,
    )
    models.User.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    assert (
        "hr_policies"
        not in inspect(engine).get_table_names()
    )

    Base.metadata.create_all(bind=engine)

    assert (
        "hr_policies"
        in inspect(engine).get_table_names()
    )



def test_create_all_adds_policy_document_and_section_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    models.Company.__table__.create(
        bind=engine,
        checkfirst=True,
    )
    models.Role.__table__.create(
        bind=engine,
        checkfirst=True,
    )
    models.User.__table__.create(
        bind=engine,
        checkfirst=True,
    )
    models.HRPolicy.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()

    assert "hr_policy_documents" in tables
    assert "hr_policy_sections" in tables
