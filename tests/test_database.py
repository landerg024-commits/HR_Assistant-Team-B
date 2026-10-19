"""Database architecture tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import models  # noqa: F401
from database.base import Base
from models.company import Company
from repositories.company_repository import CompanyRepository


def test_database_tables_and_company_repository() -> None:
    """The in-memory database should support repository CRUD."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = CompanyRepository(session)

        company = repository.create(
            {
                "code": "DEMO",
                "name": "Demo Company",
            }
        )

        found = repository.get_by_code("DEMO")

        assert found is not None
        assert found.id == company.id
        assert found.name == "Demo Company"
