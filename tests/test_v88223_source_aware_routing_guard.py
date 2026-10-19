"""v8.8.223 source-aware routing and fail-closed aggregate regressions."""

from __future__ import annotations

from pathlib import Path
from datetime import date
from types import SimpleNamespace

from modules.hr_assistant.admin_hr_assistant import AdminHRAssistant
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.hr_assistant.query_semantics import (
    analyze_query_semantics,
    employee_aggregate_shape_compatible,
)
from modules.smart_ai.portal_ai import (
    KnowledgeDocument,
    PortalKnowledgeBuilder,
    RetrievedDocument,
    SmartPortalAssistant,
)
from modules.smart_ai.prompts.hr_assistant_prompt import NOT_FOUND_ANSWER
from services.employee_company_query_service import EmployeeCompanyQueryService


ROOT = Path(__file__).resolve().parents[1]


def _admin_user():
    return SimpleNamespace(clearance=1, company_id=1, user_id=1, employee_id=1)


def test_relative_who_does_not_turn_explanatory_question_into_employee_list() -> None:
    question = "What benefits are given to employees who reach five years of service?"

    semantics = analyze_query_semantics(question)
    assert semantics.request_shape == "explanation"
    assert employee_aggregate_shape_compatible(question) is False
    assert AdminHRAssistant.classify_intent(question) == "not_found"

    service = EmployeeCompanyQueryService(None)  # query must be rejected before DB access
    assert service.try_answer(current_user=_admin_user(), question=question) is None


def test_true_collection_requests_remain_collection_shaped() -> None:
    assert employee_aggregate_shape_compatible("Who are the leaders?") is True
    assert employee_aggregate_shape_compatible("How many managers are there?") is True
    assert employee_aggregate_shape_compatible("What departments are the leaders in?") is True
    assert employee_aggregate_shape_compatible("Sino ang leaders?") is True
    assert analyze_query_semantics("Ilan ang managers?").request_shape == "count"


def test_employee_aggregate_declines_unapplied_conditions(monkeypatch) -> None:
    service = EmployeeCompanyQueryService(None)
    monkeypatch.setattr(service, "_rows", lambda company_id: [])

    # The collection shape is real, but the extra tenure/qualification condition
    # is not implemented by this live-record engine and therefore must not be
    # silently discarded.
    result = service.try_answer(
        current_user=_admin_user(),
        question="Which employees reach five years of service?",
    )
    assert result is None


def test_supported_manager_collection_still_uses_deterministic_service(monkeypatch) -> None:
    service = EmployeeCompanyQueryService(None)
    monkeypatch.setattr(service, "_rows", lambda company_id: [])

    result = service.try_answer(
        current_user=_admin_user(),
        question="Who are the managers?",
    )
    assert result is not None
    assert result.intent == "employee_aggregate"


def test_specific_policy_question_is_not_policy_library_summary() -> None:
    assert (
        AdminHRAssistant.classify_intent("Which policy applies to this eligibility condition?")
        == "policy_question"
    )
    assert AdminHRAssistant.classify_intent("How many policies are published?") == "policy_summary"


def test_smart_ai_recovers_incompatible_never_enhance_employee_aggregate() -> None:
    assistant = object.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(enabled=False)

    response = assistant.enhance(
        current_user=_admin_user(),
        role_scope="admin",
        question="What benefits are given to employees who reach five years of service?",
        history=None,
        deterministic_response=HRAssistantResponse(
            answer="Employees in the current company records: 1. Wrong list",
            intent="employee_aggregate",
        ),
    )

    assert response.intent == "not_found"
    assert response.answer == NOT_FOUND_ANSWER




def test_active_company_benefits_are_added_as_shared_rag_knowledge() -> None:
    benefit = SimpleNamespace(
        id=9,
        name="Service Recognition",
        category="Recognition",
        description="Recognition benefit configured by the company.",
        eligibility="Employees who satisfy the configured service requirement.",
        effective_date=date(2026, 1, 1),
        enrollment_instructions="Contact HR for the configured workflow.",
        contact_person="HR Benefits Desk",
    )

    class _ScalarResult:
        def all(self):
            return [benefit]

    class _Session:
        def scalars(self, _statement):
            return _ScalarResult()

    builder = object.__new__(PortalKnowledgeBuilder)
    builder.session = _Session()
    documents = []
    builder._add_company_benefit_records(documents, current_user=_admin_user())

    assert len(documents) == 1
    assert documents[0].source_type == "live_company_benefit"
    assert documents[0].role_scope == "shared"
    assert "Service Recognition" in documents[0].text
    assert "Eligibility:" in documents[0].text

def test_benefit_question_requires_matching_company_evidence_not_just_topic() -> None:
    question = "What benefits are given to employees who reach five years of service?"
    weak = KnowledgeDocument(
        document_id="benefit:weak",
        text=(
            "Company benefit: Medical Assistance. Description: Medical support. "
            "Eligibility: All active employees."
        ),
        title="Company benefit — Medical Assistance",
        source_type="live_company_benefit",
        company_id=1,
        role_scope="shared",
        metadata={"title": "Medical Assistance"},
    )
    strong = KnowledgeDocument(
        document_id="benefit:strong",
        text=(
            "Company benefit: Service Recognition. Eligibility: Employees who reach "
            "five years of service receive the configured recognition benefit."
        ),
        title="Company benefit — Service Recognition",
        source_type="live_company_benefit",
        company_id=1,
        role_scope="shared",
        metadata={"title": "Service Recognition"},
    )

    weak_result = SmartPortalAssistant._retrieval_relevance_snapshot(
        query=question,
        retrieved=[RetrievedDocument(weak, 1.0)],
        require_answer_cue=True,
        min_answer_cue=0.70,
    )
    strong_result = SmartPortalAssistant._retrieval_relevance_snapshot(
        query=question,
        retrieved=[RetrievedDocument(strong, 1.0)],
        require_answer_cue=True,
        min_answer_cue=0.70,
    )

    assert weak_result["accepted"] is False
    assert strong_result["accepted"] is True


def test_version_markers_are_v88223() -> None:
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'app_version: str = "0.8.8.223"' in settings
    assert env.splitlines()[1] == "APP_VERSION=0.8.8.223"
    assert "v8.8.223" in readme
