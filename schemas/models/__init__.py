"""Register all SQLAlchemy models."""

from models.company import Company
from models.department import Department
from models.employee import Employee
from models.role import Role
from models.user import User

__all__ = [
    "Company",
    "Department",
    "Employee",
    "Role",
    "User",
]
