"""Tests for policy content editing and readable upload previews."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from modules.documents.policy_file_storage import PolicyFileStorage
from schemas.policy_schema import (
    PolicyMetadataUpdate,
    PolicyUploadRequest,
)
from scripts.create_initial_data import seed_initial_data
from services.policy_service import PolicyService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="CONTENTEDIT",
        initial_company_name="Content Edit Company",
        initial_admin_username="admin",
        initial_admin_email="content.edit@example.com",
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


def test_content_edit_updates_view_sections_and_qa(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        original_bytes = (
            b"ORIGINAL POLICY:\n"
            b"Employees receive five leave days."
        )
        policy = service.create_policy_from_upload(
            values=PolicyUploadRequest(
                company_id=seed["company"].id,
                created_by_user_id=seed["admin_user"].id,
                title="Leave Policy",
                category="Leave",
                version="1.0",
            ),
            filename="leave_policy.txt",
            file_bytes=original_bytes,
            mime_type="text/plain",
            maximum_size_bytes=1024 * 1024,
        )

        document = service.document_repository.get_by_policy(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )
        original_path = document.storage_path

        edited_content = (
            "ANNUAL LEAVE ENTITLEMENT:\n"
            "Employees receive fifteen paid annual leave days.\n\n"
            "REQUEST PROCEDURE:\n"
            "Submit requests at least five working days in advance."
        )

        service.update_policy_metadata(
            PolicyMetadataUpdate(
                company_id=seed["company"].id,
                policy_id=policy.id,
                title=policy.title,
                category=policy.category,
                version=policy.version,
                content=edited_content,
            )
        )

        view = service.get_admin_policy_view(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )
        answer = service.answer_question(
            company_id=seed["company"].id,
            question=(
                "How many paid annual leave days "
                "do employees receive?"
            ),
        )

        assert "fifteen paid annual leave days" in (
            view.extracted_text.lower()
        )
        assert len(view.sections) == 2
        assert view.sections[0].heading == (
            "ANNUAL LEAVE ENTITLEMENT"
        )
        assert view.sections[1].heading == (
            "REQUEST PROCEDURE"
        )
        assert answer.matched is True
        assert "fifteen paid annual leave days" in (
            answer.answer.lower()
        )

        # Original file remains unchanged.
        assert (
            tmp_path / original_path
        ).read_bytes() == original_bytes


def test_metadata_only_edit_remains_compatible(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = service.create_policy_from_upload(
            values=PolicyUploadRequest(
                company_id=seed["company"].id,
                created_by_user_id=seed["admin_user"].id,
                title="Office Policy",
                category="Administration",
                version="1.0",
            ),
            filename="office.txt",
            file_bytes=b"OFFICE POLICY:\nUse the main entrance.",
            mime_type="text/plain",
            maximum_size_bytes=1024 * 1024,
        )

        updated = service.update_policy_metadata(
            PolicyMetadataUpdate(
                company_id=seed["company"].id,
                policy_id=policy.id,
                title="Main Office Policy",
                category="Administration",
                version="1.1",
            )
        )

        assert updated.title == "Main Office Policy"
        assert updated.version == "1.1"


def test_edit_details_has_content_editor() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert '"Editable Policy Content *"' in source
    assert "value=view.extracted_text" in source
    assert "content=content" in source
    assert "Saving content rebuilds searchable sections" in source


def test_headings_are_vertical_wrapped_and_unlimited() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert "def _render_detected_headings(" in source
    assert "<ol style=" in source
    assert "<li style=" in source
    assert "overflow-wrap:anywhere" in source
    assert '" · ".join(headings)' not in source
    assert "more detected section" not in source
    assert "limit: int" not in source


def test_preview_contains_all_sections_without_limits() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert "def _format_section_preview(" in source
    assert "def _render_full_section_preview(" in source
    assert "'─' * 56" in source
    assert "MAX_PREVIEW_CHARACTERS" not in source
    assert "maximum_characters" not in source
    assert "maximum_sections" not in source
    assert "Preview limited" not in source
    assert source.count(
        "_render_full_section_preview("
    ) >= 3


def test_editable_content_uses_dynamic_full_height() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert "def _full_content_editor_height(" in source
    assert (
        "height=_full_content_editor_height("
        in source
    )
    assert "No maximum cap is used" in source



def test_parser_can_reindex_edited_content() -> None:
    source = (
        PROJECT_ROOT
        / "modules/documents/policy_file_parser.py"
    ).read_text(encoding="utf-8")

    assert "def parse_edited_content(" in source
    assert "Policy content must contain at least 20" in source
