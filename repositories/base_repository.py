"""Generic repository for common database operations.

Purpose:
Repositories isolate SQLAlchemy code from services and UI modules.
Business logic should call repositories instead of writing SQL directly.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.base import Base


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Reusable CRUD operations for one model type."""

    def __init__(
        self,
        session: Session,
        model: type[ModelType],
    ) -> None:
        self.session = session
        self.model = model

    def get_by_id(
        self,
        record_id: int,
        company_id: int | None = None,
    ) -> ModelType | None:
        """Return one row by ID.

        When company_id is supplied and the model contains company_id,
        the query also enforces tenant ownership.
        """

        statement = select(self.model).where(
            self.model.id == record_id
        )

        if company_id is not None and hasattr(
            self.model,
            "company_id",
        ):
            statement = statement.where(
                self.model.company_id == company_id
            )

        return self.session.scalar(statement)

    def list_all(
        self,
        company_id: int | None = None,
    ) -> list[ModelType]:
        """Return all rows, optionally filtered to one company."""

        statement = select(self.model)

        if company_id is not None and hasattr(
            self.model,
            "company_id",
        ):
            statement = statement.where(
                self.model.company_id == company_id
            )

        return list(self.session.scalars(statement).all())

    def create(self, values: dict[str, Any]) -> ModelType:
        """Create, commit, refresh, and return a new row."""

        instance = self.model(**values)
        self.session.add(instance)
        self.session.commit()

        # Refresh reads generated values such as primary key and timestamps.
        self.session.refresh(instance)

        return instance

    def update(
        self,
        instance: ModelType,
        values: dict[str, Any],
    ) -> ModelType:
        """Update existing fields, commit, and return the refreshed row."""

        for field_name, value in values.items():
            if hasattr(instance, field_name):
                setattr(instance, field_name, value)

        self.session.commit()
        self.session.refresh(instance)

        return instance

    def delete(self, instance: ModelType) -> None:
        """Delete and commit one row."""

        self.session.delete(instance)
        self.session.commit()
