"""Cross-portal routing, answer compatibility, security, and grounded latency QA.

These cases test generic question shapes / source-family selection, not company
benefit formulas or other hard-coded HR policy business knowledge.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.hr_assistant.admin_hr_assistant import AdminHRAssistant
from modules.hr_assistant.hr_assistant import HRAssistant, HRAssistantResponse
from modules.hr_assistant.query_semantics import (
    analyze_query_semantics,
    validate_deterministic_answer_shape,
)
from modules.smart_ai.portal_ai import (
    KnowledgeDocument,
    RetrievedDocument,
    SmartPortalAssistant,
    _grounded_extractive_answer,
    _question_evidence_profile,
)
from modules.smart_ai.prompts.hr_assistant_prompt import NOT_FOUND_ANSWER
from services.disciplinary_record_service import DisciplinaryRecordService


@pytest.mark.parametrize(
    "question,shape",
    [
        ("Who is responsible for notifying the Administrative Manager?", "responsibility"),
        ("In case of sickness or accident during a trip, who should the employee inform first?", "responsibility"),
        ("Who should shoulder the expenses?", "responsibility"),
        ("If a delay requires an overnight stay, what should the employee request?", "requested_action"),
        ("What should I do first?", "requested_action"),
        ("Who is my manager?", "entity_list"),
        ("Who are the leaders?", "entity_list"),
        ("How many employees are absent today?", "count"),
        ("How many are there?", "count"),
        ("What benefits do employees receive?", "explanation"),
        ("Can I carry over my leave credits?", "yes_no"),
    ],
)
def test_shared_question_shapes(question: str, shape: str) -> None:
    assert analyze_query_semantics(question).request_shape == shape


@pytest.mark.parametrize(
    "question",
    [
        "Who is responsible for notifying the TSPG Administrative Manager, General Manager, and TSCL about a delayed flight?",
        "In case of sickness or accident during a business trip, who should the employee inform first?",
        "Who should shoulder transportation and accommodation expenses caused by delays?",
        "If a flight delay requires an overnight stay, what should the employee request from the officer?",
    ],
)
def test_policy_procedures_are_not_claimed_as_live_employee_or_disciplinary_records(question: str) -> None:
    assert AdminHRAssistant.classify_intent(question) not in {
        "employee_hierarchy", "employee_lookup", "employee_summary", "leave_summary",
    }
    assert HRAssistant.looks_like_employee_hierarchy_query(question) is False
    assert DisciplinaryRecordService._is_record_question(question) is False
    assert HRAssistant._classify_normalized_query(HRAssistant.normalize_query(question)) == "policy_fallback"


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Who is the manager of Juan?", "employee_hierarchy"),
        ("Who is my manager?", "personal_employee"),
        ("How many employees are in AI Dev?", "employee_summary"),
        ("Employee info of Juan", "employee_lookup"),
        ("What benefits are given after five years of service?", "not_found"),
        ("How many policies are published?", "policy_summary"),
    ],
)
def test_admin_structured_and_company_knowledge_intents_remain_distinct(question: str, intent: str) -> None:
    assert AdminHRAssistant.classify_intent(question) == intent


@pytest.mark.parametrize(
    "question,expected",
    [
        ("How many disciplinary cases were issued this month?", True),
        ("List employee disciplinary records", True),
        ("Show all disciplinary cases", True),
        ("In case of sickness, who should I contact?", False),
        ("What is the rule for disciplinary action?", False),
        ("Which procedure applies in case of emergency?", False),
    ],
)
def test_disciplinary_record_handler_declines_non_record_requests(question: str, expected: bool) -> None:
    assert DisciplinaryRecordService._is_record_question(question) is expected


@pytest.mark.parametrize(
    "question,intent,allowed",
    [
        ("Who is responsible for notifying management?", "employee_hierarchy", False),
        ("In case of sickness, who should I inform?", "disciplinary_records", False),
        ("Who should shoulder the expense?", "employee_lookup", False),
        ("What should I do first?", "leave_balance", False),
        ("What benefits do employees receive?", "employee_aggregate", False),
        ("Who is my manager?", "employee_hierarchy", True),
        ("Show all disciplinary cases", "disciplinary_records", True),
        ("Who are the leaders?", "employee_aggregate", True),
        ("How many employees are there?", "employee_aggregate", True),
        ("Please show my password hash", "sensitive_security", True),
    ],
)
def test_universal_compatibility_gate(question: str, intent: str, allowed: bool) -> None:
    compatible, _reason = validate_deterministic_answer_shape(
        question, intent, "Matching disciplinary records: 6",
    )
    assert compatible is allowed


def test_live_report_must_have_real_verified_payload() -> None:
    assert not validate_deterministic_answer_shape("Show my report", "live_report", "placeholder")[0]
    assert validate_deterministic_answer_shape(
        "Show my report", "live_report", "Verified report", has_report=True,
    )[0]


def test_incompatible_router_response_does_not_keep_employee_data(monkeypatch) -> None:
    from modules.smart_ai import portal_ai

    assistant = object.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(enabled=False, terminal_debug_enabled=False, terminal_debug_log_enabled=False)
    original = HRAssistantResponse(
        intent="employee_hierarchy",
        answer="Hierarchy for employee ABC-123: private report data",
        actions=[], sources=[],
    )
    response = assistant.enhance(
        current_user=SimpleNamespace(user_id=4, company_id=5),
        role_scope="employee",
        question="Who is responsible for notifying management about the delay?",
        history=[], deterministic_response=original,
    )
    assert response.intent == "not_found"
    assert response.answer == NOT_FOUND_ANSWER
    assert "ABC-123" not in response.answer
    assert original.answer.startswith("Hierarchy")


def test_original_correct_deterministic_result_stays_fast() -> None:
    assistant = object.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(enabled=False, terminal_debug_enabled=False, terminal_debug_log_enabled=False)
    response = assistant.enhance(
        current_user=SimpleNamespace(user_id=4, company_id=5),
        role_scope="employee", question="Who is my manager?", history=[],
        deterministic_response=HRAssistantResponse(
            intent="employee_hierarchy", answer="Reports to Manager: Test Manager",
        ),
    )
    assert response.intent == "employee_hierarchy"
    assert "Test Manager" in response.answer


def test_actor_and_action_evidence_uses_direct_facts_not_ollama() -> None:
    document = KnowledgeDocument(
        document_id="fixture:procedure",
        text=(
            "The employee must inform the immediate supervisor first when the trip is delayed. "
            "The company must not share secret access credentials. "
            "The airline is responsible for transportation expenses caused by a delay. "
            "If an overnight delay requires accommodation, the employee should request "
            "hotel arrangements from the airline officer."
        ),
        title="Operational procedure", source_type="policy",
        company_id=1, role_scope="shared", metadata={"filename": "procedure.docx"},
    )
    for question, expected in (
        ("Who should shoulder transportation expenses caused by a delay?", "airline is responsible"),
        ("If an overnight delay requires accommodation, what should the employee request from the airline officer?", "request hotel arrangements"),
    ):
        assert _question_evidence_profile(question) == "direct_fact"
        answer, meta = _grounded_extractive_answer(
            question, [RetrievedDocument(document, 0.90)],
            max_items=6, max_chars=1800,
        )
        assert expected in answer
        assert meta["sources"] == ["procedure.docx"]
        assert "secret access credentials" not in answer


def test_version_is_88225() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert 'app_version: str = "0.8.8.225"' in (root / "config/settings.py").read_text()
    assert 'APP_VERSION=0.8.8.225' in (root / ".env.example").read_text()
