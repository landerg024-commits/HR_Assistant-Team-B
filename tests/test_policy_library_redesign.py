"""Tests for v8.4.0 policy library redesign."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from modules.documents.policy_file_storage import PolicyFileStorage
from schemas.policy_schema import PolicyUploadRequest
from scripts.create_initial_data import seed_initial_data
from services.policy_service import PolicyService


def _settings():
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="POLLIB",
        initial_company_name="Policy Library Company",
        initial_admin_username="admin",
        initial_admin_email="policy.library@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _upload(service, seed, tmp_path, *, filename, version, title=None):
    preview = service.preview_policy_upload(
        company_id=seed["company"].id,
        filename=filename,
        file_bytes=b"ANNUAL LEAVE:\nEmployees receive leave days.",
        maximum_size_bytes=1024 * 1024,
        mime_type="text/plain",
        selected_existing_title=title,
    )
    return service.create_policy_from_upload(
        values=PolicyUploadRequest(
            company_id=seed["company"].id,
            created_by_user_id=seed["admin_user"].id,
            title=preview.display_title,
            category=preview.suggested_category,
            version=version,
        ),
        filename=filename,
        file_bytes=(b"ANNUAL LEAVE:\nEmployees receive leave days." + version.encode()),
        mime_type="text/plain",
        maximum_size_bytes=1024 * 1024,
    )


def test_filename_title_category_and_public_id(tmp_path: Path) -> None:
    _, factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(session, storage=PolicyFileStorage(tmp_path))
        preview = service.preview_policy_upload(
            company_id=seed["company"].id,
            filename="Annual_Leave_Policy_v1.0.txt",
            file_bytes=b"ANNUAL LEAVE ENTITLEMENT:\nFifteen days.",
            maximum_size_bytes=1024 * 1024,
            mime_type="text/plain",
        )
        assert preview.display_title == "Annual Leave Policy"
        assert preview.suggested_category == "Annual Leave Entitlement"
        policy = service.create_policy_from_upload(
            values=PolicyUploadRequest(
                company_id=seed["company"].id,
                created_by_user_id=seed["admin_user"].id,
                title=preview.display_title,
                category=preview.suggested_category,
                version="1.0",
            ),
            filename="Annual_Leave_Policy_v1.0.txt",
            file_bytes=b"ANNUAL LEAVE ENTITLEMENT:\nFifteen days.",
            mime_type="text/plain",
            maximum_size_bytes=1024 * 1024,
        )
        assert policy.public_id == f"PID_{policy.id:03d}"
        assert policy.status == "published"
        assert policy.effective_date is None


def test_auto_and_explicit_version_linking(tmp_path: Path) -> None:
    _, factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(session, storage=PolicyFileStorage(tmp_path))
        first = _upload(service, seed, tmp_path, filename="Code_of_Conduct.txt", version="1.0")
        auto = service.preview_policy_upload(
            company_id=seed["company"].id,
            filename="Code_of_Conduct_v2.txt",
            file_bytes=b"CONDUCT:\nUpdated rules.",
            maximum_size_bytes=1024 * 1024,
            mime_type="text/plain",
        )
        assert auto.display_title == first.title
        assert auto.latest_version == "1.0"
        explicit = service.preview_policy_upload(
            company_id=seed["company"].id,
            filename="renamed_document.txt",
            file_bytes=b"CONDUCT:\nAnother update.",
            maximum_size_bytes=1024 * 1024,
            mime_type="text/plain",
            selected_existing_title=first.title,
        )
        assert explicit.display_title == first.title
        assert explicit.previous_versions[0].version == "1.0"


def test_move_to_bin_excludes_employee_search_and_restore(tmp_path: Path) -> None:
    _, factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = PolicyService(session, storage=PolicyFileStorage(tmp_path))
        policy = _upload(service, seed, tmp_path, filename="Attendance_Policy.txt", version="1.0")
        moved = service.move_to_bin(
            company_id=seed["company"].id,
            policy_id=policy.id,
            user_id=seed["admin_user"].id,
            confirmation_public_id=policy.public_id,
        )
        assert moved.status == "trashed"
        assert service.list_published(seed["company"].id) == []
        assert service.list_bin(seed["company"].id)[0].id == policy.id
        restored = service.restore_from_bin(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )
        assert restored.status == "published"
        assert service.list_published(seed["company"].id)[0].id == policy.id


def test_runtime_upgrade_adds_policy_library_columns() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # Simulate older policy table through raw SQL-compatible metadata copy.
    models.Company.__table__.create(engine)
    models.Role.__table__.create(engine)
    models.User.__table__.create(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE TABLE hr_policies (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL,
            created_by_user_id INTEGER NOT NULL,
            title VARCHAR(200) NOT NULL,
            category VARCHAR(100) NOT NULL,
            summary TEXT,
            content TEXT NOT NULL,
            version VARCHAR(30) NOT NULL,
            status VARCHAR(20) NOT NULL,
            effective_date DATE,
            published_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
            )"""
        )
        connection.exec_driver_sql(
            "INSERT INTO hr_policies VALUES "
            "(1,1,1,'Policy','General',NULL,'Content','1.0','published',NULL,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    upgrade_existing_schema(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("hr_policies")}
    assert {"public_id", "trashed_at", "trashed_by_user_id"} <= columns
    with engine.connect() as connection:
        public_id = connection.exec_driver_sql(
            "SELECT public_id FROM hr_policies WHERE id = 1"
        ).scalar_one()
    assert public_id == "PID_001"


def test_policy_page_removes_obsolete_fields_and_has_bin() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")
    assert '"Status"' not in source.split("def _policy_rows", 1)[1].split("def _render_policy_table", 1)[0]
    assert '"Source File"' not in source
    assert '"Effective Date"' not in source
    assert "Publish immediately" not in source
    assert "Preview Before Upload" not in source
    assert "Document Preview" in source
    assert "Move Policy Version to Bin" in source
    assert "Restore Policy Version" in source
    assert "Delete Permanently" in source



def test_employee_page_uses_upload_date_and_excludes_bin_wording() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ui/pages/user/policies_page.py"
    ).read_text(encoding="utf-8")

    assert "Uploaded:" in source
    assert "Versions moved to the Bin are excluded" in source
    assert "Effective:" not in source


def test_bin_keeps_original_file_access_and_has_permanent_delete() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    bin_block = source.split("def _render_bin", 1)[1].split(
        "def render_admin_policies_page",
        1,
    )[0]
    assert '"Original File"' in bin_block
    assert "_render_original_file" in bin_block
    assert "Delete Permanently" in bin_block
    assert "_render_permanent_delete" in bin_block
