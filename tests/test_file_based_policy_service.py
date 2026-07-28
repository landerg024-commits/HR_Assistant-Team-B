"""End-to-end tests for uploaded policy storage and Q&A."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from modules.documents.policy_file_storage import PolicyFileStorage
from schemas.policy_schema import PolicyUploadRequest
from scripts.create_initial_data import seed_initial_data
from services.policy_service import (
    NO_POLICY_ANSWER,
    PolicyService,
)


def _settings(code: str, email: str) -> Settings:
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
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _upload(
    service,
    seed,
    *,
    filename="Annual_Leave.txt",
    version="1.0-file",
    publish=True,
    content=(
        b"ENTITLEMENT:\n"
        b"Employees receive fifteen annual leave days.\n\n"
        b"REQUEST PROCEDURE:\n"
        b"Submit requests five working days in advance."
    ),
):
    return service.create_policy_from_upload(
        values=PolicyUploadRequest(
            company_id=seed["company"].id,
            created_by_user_id=seed["admin_user"].id,
            title="Annual Leave Policy",
            category="Leave",
            summary="Annual leave rules.",
            version=version,
            publish_immediately=publish,
        ),
        filename=filename,
        file_bytes=content,
        mime_type="text/plain",
        maximum_size_bytes=1024 * 1024,
    )


def test_uploaded_file_is_stored_and_answer_source_has_filename(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "FILEPOL",
                "file.policy@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(service, seed)

        document = service.document_repository.get_by_policy(
            company_id=seed["company"].id,
            policy_id=policy.id,
        )

        assert document is not None
        assert (tmp_path / document.storage_path).is_file()

        answer = service.answer_question(
            company_id=seed["company"].id,
            question=(
                "How many annual leave days do employees receive?"
            ),
        )

        assert answer.matched is True
        assert answer.sources[0].filename == "Annual_Leave.txt"
        assert "fifteen annual leave days" in answer.answer.lower()


def test_employee_can_download_published_company_file(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "DOWNLOAD",
                "download.policy@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(service, seed)

        download = service.get_policy_download(
            company_id=seed["company"].id,
            policy_id=policy.id,
            published_only=True,
        )

        assert download.filename == "Annual_Leave.txt"
        assert b"fifteen annual leave days" in download.data


def test_uploaded_file_is_published_even_with_legacy_false_flag(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "AUTOPUBLISH",
                "auto.publish@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(service, seed, publish=False)

        assert policy.status == "published"
        answer = service.answer_question(
            company_id=seed["company"].id,
            question="How many annual leave days are provided?",
        )
        assert answer.matched is True


def test_exact_duplicate_file_is_blocked_per_company(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "DUPFILE",
                "duplicate.file@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        _upload(service, seed)

        try:
            _upload(
                service,
                seed,
                version="2.0-file",
            )
        except ValueError as error:
            assert "exact file" in str(error)
        else:
            raise AssertionError("Duplicate file was accepted.")


def test_other_company_cannot_download_file(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "FIRSTFILE",
                "first.file@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "SECONDFILE",
                "second.file@example.com",
            ),
        )
        service = PolicyService(
            session,
            storage=PolicyFileStorage(tmp_path),
        )
        policy = _upload(service, first)

        try:
            service.get_policy_download(
                company_id=second["company"].id,
                policy_id=policy.id,
                published_only=True,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Another company downloaded the policy file."
            )
