"""Tests for company-scoped HR Policy Q&A."""

from datetime import date, timedelta

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from schemas.policy_schema import PolicyCreateRequest
from scripts.create_initial_data import seed_initial_data
from services.policy_service import (
    NO_POLICY_ANSWER,
    PolicyService,
)


def _settings(
    code: str,
    email: str,
) -> Settings:
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


def _create_policy(
    service,
    seed,
    *,
    title="Annual Leave Policy",
    version="1.0",
    content=None,
    publish=True,
    effective_date=None,
):
    return service.create_policy(
        PolicyCreateRequest(
            company_id=seed["company"].id,
            created_by_user_id=seed["admin_user"].id,
            title=title,
            category="Leave",
            summary="Annual leave rules.",
            content=content or (
                "Entitlement:\n"
                "Employees receive fifteen annual leave days.\n\n"
                "Request Procedure:\n"
                "Submit requests five working days in advance."
            ),
            version=version,
            effective_date=(
                effective_date or date.today()
            ),
            publish_immediately=publish,
        )
    )


def test_published_policy_answers_question_with_source() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "POLICY",
                "policy.admin@example.com",
            ),
        )
        service = PolicyService(session)
        _create_policy(service, seed)

        result = service.answer_question(
            company_id=seed["company"].id,
            question=(
                "How many annual leave days do employees receive?"
            ),
        )

        assert result.matched is True
        assert "fifteen annual leave days" in result.answer.lower()
        assert result.sources[0].title == "Annual Leave Policy"


def test_draft_policy_is_not_available_to_employee() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "DRAFT",
                "draft.admin@example.com",
            ),
        )
        service = PolicyService(session)
        _create_policy(
            service,
            seed,
            publish=False,
        )

        result = service.answer_question(
            company_id=seed["company"].id,
            question="How many annual leave days are provided?",
        )

        assert result.matched is False
        assert result.answer == NO_POLICY_ANSWER


def test_future_effective_policy_is_excluded() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "FUTURE",
                "future.admin@example.com",
            ),
        )
        service = PolicyService(session)
        _create_policy(
            service,
            seed,
            effective_date=(
                date.today() + timedelta(days=30)
            ),
        )

        assert (
            service.list_published(seed["company"].id)
            == []
        )


def test_unknown_question_returns_exact_fallback() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "UNKNOWN",
                "unknown.admin@example.com",
            ),
        )
        service = PolicyService(session)
        _create_policy(service, seed)

        result = service.answer_question(
            company_id=seed["company"].id,
            question="What is the company spaceship launch code?",
        )

        assert result.answer == NO_POLICY_ANSWER
        assert result.sources == []


def test_policy_data_is_company_isolated() -> None:
    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "FIRSTPOL",
                "first.policy@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "SECONDPOL",
                "second.policy@example.com",
            ),
        )
        service = PolicyService(session)

        _create_policy(
            service,
            first,
            content=(
                "Unique Benefit:\n"
                "First company employees receive a blue badge."
            ),
        )

        second_result = service.answer_question(
            company_id=second["company"].id,
            question="Who receives a blue badge?",
        )

        assert second_result.answer == NO_POLICY_ANSWER


def test_same_title_version_allowed_in_different_companies() -> None:
    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "TITLEONE",
                "title.one@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "TITLETWO",
                "title.two@example.com",
            ),
        )
        service = PolicyService(session)

        first_policy = _create_policy(service, first)
        second_policy = _create_policy(service, second)

        assert (
            first_policy.company_id
            != second_policy.company_id
        )


def test_duplicate_title_version_blocked_in_same_company() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "DUPPOL",
                "duplicate.policy@example.com",
            ),
        )
        service = PolicyService(session)
        _create_policy(service, seed)

        try:
            _create_policy(service, seed)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Duplicate policy title/version was accepted."
            )
