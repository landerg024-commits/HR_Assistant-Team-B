"""Tests for the administrator policy-content viewer service."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from modules.documents.policy_file_storage import PolicyFileStorage
from schemas.policy_schema import (
    PolicyCreateRequest,
    PolicyUploadRequest,
)
from scripts.create_initial_data import seed_initial_data
from services.policy_service import PolicyService


def _settings(code: str, email: str) -> Settings:
    """Create isolated company settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code=code,
        initial_company_name=f"{code} Company",
        initial_admin_username=f"{code.lower()}admin",
        initial_admin_email=email,
        initial_admin_password=SecretStr("ChangeMe123!"),
        initial_admin_employee_number=f"{code}-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    """Create an isolated database factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def test_admin_view_returns_uploaded_document_and_sections(
    tmp_path: Path,
) -> None:
    """Uploaded content must be visible with exact indexed sections."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "VIEWFILE",
                "view.file@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )

        policy = service.create_policy_from_upload(
            values=PolicyUploadRequest(
                company_id=seed["company"].id,
                created_by_user_id=seed["admin_user"].id,
                title="Annual Leave Policy",
                category="Leave",
                version="1.0",
                publish_immediately=False,
            ),
            filename="Annual_Leave.txt",
            file_bytes=(
                b"ENTITLEMENT:\n"
                b"Employees receive fifteen leave days.\n\n"
                b"REQUEST PROCEDURE:\n"
                b"Submit five working days in advance."
            ),
            mime_type="text/plain",
            maximum_size_bytes=1024 * 1024,
        )

        view = service.get_admin_policy_view(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )

        assert view.source_type == "uploaded_file"
        assert view.document is not None
        assert view.document.original_filename == "Annual_Leave.txt"
        assert len(view.sections) == 2
        assert view.sections[0].heading == "ENTITLEMENT"
        assert "fifteen leave days" in view.extracted_text


def test_admin_view_supports_legacy_manual_policy(
    tmp_path: Path,
) -> None:
    """Older manual policies must remain viewable after the upgrade."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "VIEWMAN",
                "view.manual@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )

        policy = service.create_policy(
            PolicyCreateRequest(
                company_id=seed["company"].id,
                created_by_user_id=seed["admin_user"].id,
                title="Manual Conduct Policy",
                category="Conduct",
                content=(
                    "RESPECT:\n"
                    "Employees must treat colleagues respectfully."
                ),
                version="1.0",
                publish_immediately=False,
            )
        )

        view = service.get_admin_policy_view(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )

        assert view.source_type == "manual_entry"
        assert view.document is None
        assert len(view.sections) == 1
        assert view.sections[0].heading == "RESPECT"


def test_other_company_cannot_view_policy_content(
    tmp_path: Path,
) -> None:
    """Company isolation must protect extracted content and metadata."""

    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "VIEWONE",
                "view.one@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "VIEWTWO",
                "view.two@example.com",
            ),
        )

        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )

        policy = service.create_policy_from_upload(
            values=PolicyUploadRequest(
                company_id=first["company"].id,
                created_by_user_id=first["admin_user"].id,
                title="Private Policy",
                category="Internal",
                version="1.0",
            ),
            filename="private.txt",
            file_bytes=b"PRIVATE:\nFirst company content only.",
            mime_type="text/plain",
            maximum_size_bytes=1024 * 1024,
        )

        try:
            service.get_admin_policy_view(
                company_id=second["company"].id,
                policy_id=policy.id,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Another company viewed private policy content."
            )
