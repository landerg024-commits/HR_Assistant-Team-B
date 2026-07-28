"""Business logic for company profile, departments, and roles.

Layer flow:
Admin Page -> Pydantic Schema -> OrganizationService -> Repository -> DB

Important rules:
- Every department and role operation is limited by company_id.
- Company code is immutable; only the display name may be changed.
- System roles cannot be deactivated.
- A custom role with assigned users cannot be deactivated.
"""

from sqlalchemy.orm import Session

from models.company import Company
from models.department import Department
from models.role import Role
from repositories.company_repository import CompanyRepository
from repositories.department_repository import DepartmentRepository
from repositories.role_repository import RoleRepository
from schemas.organization_schema import (
    CompanyNameUpdate,
    CompanyThemeColorUpdate,
    DepartmentCreate,
    RoleCreateRequest,
)


class OrganizationService:
    """Manage company-scoped organization settings."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.company_repository = CompanyRepository(session)
        self.department_repository = DepartmentRepository(session)
        self.role_repository = RoleRepository(session)

    def get_company(self, company_id: int) -> Company:
        """Return the current company or raise a readable error."""

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            raise ValueError("The company record was not found.")

        return company

    def update_company_name(
        self,
        values: CompanyNameUpdate,
    ) -> Company:
        """Update only the company display name."""

        normalized_name = values.name.strip()

        company = self.company_repository.update_name(
            company_id=values.company_id,
            name=normalized_name,
        )

        if company is None:
            raise ValueError("The company record was not found.")

        return company

    def update_company_theme_color(
        self,
        values: CompanyThemeColorUpdate,
    ) -> Company:
        """Update the company-wide primary accent color."""

        normalized_color = values.primary_color.strip().upper()

        company = self.company_repository.update_theme_color(
            company_id=values.company_id,
            primary_color=normalized_color,
        )

        if company is None:
            raise ValueError("The company record was not found.")

        return company

    def list_departments(
        self,
        company_id: int,
    ) -> list[Department]:
        """Return all departments owned by the company."""

        return self.department_repository.list_all_for_company(
            company_id
        )

    def create_department(
        self,
        values: DepartmentCreate,
    ) -> Department:
        """Create a unique department inside one company."""

        normalized_name = values.name.strip()
        normalized_code = (
            values.code.strip().upper()
            if values.code
            else None
        )

        existing_name = self.department_repository.get_by_name(
            values.company_id,
            normalized_name,
        )

        if existing_name is not None:
            raise ValueError(
                f"Department '{normalized_name}' already exists "
                "inside this company."
            )

        if normalized_code:
            existing_code = self.department_repository.get_by_code(
                values.company_id,
                normalized_code,
            )

            if existing_code is not None:
                raise ValueError(
                    f"Department code '{normalized_code}' "
                    "already exists inside this company."
                )

        return self.department_repository.create(
            {
                "company_id": values.company_id,
                "name": normalized_name,
                "code": normalized_code,
                "is_active": True,
            }
        )

    def set_department_active_status(
        self,
        *,
        company_id: int,
        department_id: int,
        is_active: bool,
    ) -> Department:
        """Activate or deactivate a company-owned department."""

        department = (
            self.department_repository.update_active_status(
                company_id=company_id,
                department_id=department_id,
                is_active=is_active,
            )
        )

        if department is None:
            raise ValueError(
                "The selected department does not belong "
                "to this company."
            )

        return department

    def list_roles(self, company_id: int) -> list[Role]:
        """Return system and custom company roles."""

        return self.role_repository.list_all_for_company(
            company_id
        )

    def create_custom_role(
        self,
        values: RoleCreateRequest,
    ) -> Role:
        """Create an active custom role inside one company."""

        normalized_name = values.name.strip().lower()
        normalized_description = (
            values.description.strip()
            if values.description
            else None
        )

        existing = self.role_repository.get_by_name(
            values.company_id,
            normalized_name,
        )

        if existing is not None:
            raise ValueError(
                f"Role '{normalized_name}' already exists "
                "inside this company."
            )

        return self.role_repository.create(
            {
                "company_id": values.company_id,
                "name": normalized_name,
                "description": normalized_description,
                "is_system_role": False,
                "is_active": True,
            }
        )

    def set_role_active_status(
        self,
        *,
        company_id: int,
        role_id: int,
        is_active: bool,
    ) -> Role:
        """Safely activate or deactivate a custom role."""

        role = self.role_repository.get_by_id(
            record_id=role_id,
            company_id=company_id,
        )

        if role is None:
            raise ValueError(
                "The selected role does not belong to this company."
            )

        if role.is_system_role and not is_active:
            raise ValueError(
                "System roles cannot be deactivated."
            )

        if not is_active:
            assigned_users = (
                self.role_repository.count_assigned_users(
                    company_id=company_id,
                    role_id=role_id,
                )
            )

            if assigned_users > 0:
                raise ValueError(
                    "This role cannot be deactivated because "
                    f"{assigned_users} user account(s) are assigned to it."
                )

        updated_role = self.role_repository.update_active_status(
            company_id=company_id,
            role_id=role_id,
            is_active=is_active,
        )

        if updated_role is None:
            raise ValueError("The role could not be updated.")

        return updated_role
