"""Abstract database-adapter contract.

Purpose:
Different companies may use different database engines. Business services
should depend on this interface rather than on one hardcoded database.
"""

from abc import ABC, abstractmethod

from sqlalchemy.engine import Engine


class BaseDatabaseAdapter(ABC):
    """Required behavior for every database adapter."""

    @abstractmethod
    def create_engine(self) -> Engine:
        """Create or return the adapter's SQLAlchemy engine."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True when the configured database is reachable."""
