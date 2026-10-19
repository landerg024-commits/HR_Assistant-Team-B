"""Tests for policy metadata editing, new versions, and permanent deletion."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.hr_policy import HRPolicy
from models.hr_policy_document import HRPolicyDocument
from models.hr_policy_section import HRPolicySection
from modules.documents.policy_file_storage import PolicyFileStorage
from schemas.policy_schema import (
    PolicyMetadataUpdate,
    PolicyPermanentDeleteRequest,
    PolicyUploadRequest,
)
from scripts.create_initial_data import seed_initial_data
from services.policy_service import PolicyService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="POLICYEDIT",
        initial_company_name="Policy Edit Company",
        initial_admin_username="admin",
        initial_admin_email="policy.edit@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _upload(
    service: PolicyService,
    seed,
    *,
    title: str,
    version: str,
    filename: str,
    body: bytes,
):
    return service.create_policy_from_upload(
        values=PolicyUploadRequest(
            company_id=seed["company"].id,
            created_by_user_id=seed["admin_user"].id,
            title=title,
            category="General",
            version=version,
        ),
        filename=filename,
        file_bytes=body,
        mime_type="text/plain",
        maximum_size_bytes=1024 * 1024,
    )


def test_edit_updates_family_title_category_and_selected_version(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        first = _upload(
            service,
            seed,
            title="Office Policy",
            version="1.0",
            filename="office_v1.txt",
            body=b"OFFICE RULES:\nFirst version.",
        )
        second = _upload(
            service,
            seed,
            title="Office Policy",
            version="2.0",
            filename="office_v2.txt",
            body=b"OFFICE RULES:\nSecond version.",
        )

        updated = service.update_policy_metadata(
            PolicyMetadataUpdate(
                company_id=seed["company"].id,
                policy_id=second.id,
                title="Main Office Policy",
                category="Administration",
                version="2.1",
            )
        )

        family = service.repository.list_by_title(
            company_id=seed["company"].id,
            title="Main Office Policy",
        )

        assert updated.version == "2.1"
        assert {item.id for item in family} == {
            first.id,
            second.id,
        }
        assert {
            item.category
            for item in family
        } == {"Administration"}
        assert {
            item.version
            for item in family
        } == {"1.0", "2.1"}


def test_edit_does_not_overwrite_original_file(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(
            service,
            seed,
            title="Leave Policy",
            version="1.0",
            filename="leave.txt",
            body=b"LEAVE:\nOriginal content.",
        )
        document = service.document_repository.get_by_policy(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )
        original_hash = document.sha256
        original_path = document.storage_path

        service.update_policy_metadata(
            PolicyMetadataUpdate(
                company_id=seed["company"].id,
                policy_id=policy.id,
                title="Employee Leave Policy",
                category="Leave",
                version="1.1",
            )
        )

        refreshed = service.document_repository.get_by_policy(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )

        assert refreshed.sha256 == original_hash
        assert refreshed.storage_path == original_path
        assert (tmp_path / original_path).is_file()


def test_permanent_delete_removes_exact_bin_version_and_file(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        first = _upload(
            service,
            seed,
            title="Conduct Policy",
            version="1.0",
            filename="conduct_v1.txt",
            body=b"CONDUCT:\nFirst version.",
        )
        second = _upload(
            service,
            seed,
            title="Conduct Policy",
            version="2.0",
            filename="conduct_v2.txt",
            body=b"CONDUCT:\nSecond version.",
        )
        document = service.document_repository.get_by_policy(
            company_id=seed["company"].id,
            policy_id=first.id,
        )
        stored_path = document.storage_path

        service.move_to_bin(
            company_id=seed["company"].id,
            policy_id=first.id,
            user_id=seed["admin_user"].id,
            confirmation_public_id=first.public_id,
        )

        result = service.permanently_delete_from_bin(
            PolicyPermanentDeleteRequest(
                company_id=seed["company"].id,
                policy_id=first.id,
                confirmation_public_id=first.public_id,
                permanent_delete_acknowledged=True,
            )
        )

        assert result.public_id == first.public_id
        assert session.get(HRPolicy, first.id) is None
        assert session.get(HRPolicy, second.id) is not None
        assert not (tmp_path / stored_path).exists()

        document_count = session.scalar(
            select(func.count(HRPolicyDocument.id)).where(
                HRPolicyDocument.policy_id == first.id
            )
        )
        section_count = session.scalar(
            select(func.count(HRPolicySection.id)).where(
                HRPolicySection.policy_id == first.id
            )
        )

        assert document_count == 0
        assert section_count == 0


def test_permanent_delete_requires_bin_and_exact_id(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(
            service,
            seed,
            title="Security Policy",
            version="1.0",
            filename="security.txt",
            body=b"SECURITY:\nRules.",
        )

        request = PolicyPermanentDeleteRequest(
            company_id=seed["company"].id,
            policy_id=policy.id,
            confirmation_public_id="PID_WRONG",
            permanent_delete_acknowledged=True,
        )

        try:
            service.permanently_delete_from_bin(request)
        except ValueError as error:
            assert "Only policy versions" in str(error)
        else:
            raise AssertionError(
                "An active policy was permanently deleted."
            )

        service.move_to_bin(
            company_id=seed["company"].id,
            policy_id=policy.id,
            user_id=seed["admin_user"].id,
            confirmation_public_id=policy.public_id,
        )

        try:
            service.permanently_delete_from_bin(request)
        except ValueError as error:
            assert "does not match" in str(error)
        else:
            raise AssertionError(
                "A wrong Policy ID confirmation was accepted."
            )


def test_manage_ui_has_edit_new_version_and_delete() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert '"Edit Details"' in source
    assert '"Upload New Version"' in source
    assert "Save Policy Changes" in source
    assert "Editable Policy Content *" in source
    assert "Upload New Policy Version" in source
    assert '"Delete Permanently"' in source
    assert "Delete Policy Version Permanently" in source
    assert "PolicyPermanentDeleteRequest" in source
