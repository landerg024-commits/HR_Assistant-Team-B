"""Register all SQLAlchemy models."""

from models.company import Company
from models.department import Department
from models.employee import Employee
from models.employee_training import EmployeeTraining
from models.hr_policy import HRPolicy
from models.hr_policy_document import HRPolicyDocument
from models.hr_policy_section import HRPolicySection
from models.leave_balance import LeaveBalance
from models.leave_credit_transaction import LeaveCreditTransaction
from models.leave_request import LeaveRequest
from models.leave_type import LeaveType
from models.notification import Notification
from models.password_reset_token import PasswordResetToken
from models.role import Role
from models.user import User

__all__ = [
    "Company",
    "Department",
    "Employee",
    "EmployeeTraining",
    "HRPolicy",
    "HRPolicyDocument",
    "HRPolicySection",
    "LeaveBalance",
    "LeaveCreditTransaction",
    "LeaveRequest",
    "LeaveType",
    "Notification",
    "PasswordResetToken",
    "Role",
    "User",
]
