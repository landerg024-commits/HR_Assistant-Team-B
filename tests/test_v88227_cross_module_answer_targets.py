"""v8.8.227 generic answer-target, default/exception and timing QA."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import re

import pytest

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _direct_action_target,
    _exception_only_sentence, _grounded_extractive_answer,
)


def _doc(text: str, *, source_type: str = "policy", section: str = "Procedure") -> RetrievedDocument:
    return RetrievedDocument(KnowledgeDocument(
        document_id="fixture:1", text=text, title="Workplace procedure",
        source_type=source_type, company_id=1, role_scope="shared",
        metadata={"filename": "generic-procedure.docx", "section": section},
    ), 0.9)


def _extract(question: str, text: str, *, source_type: str = "policy") -> tuple[str, dict]:
    return _grounded_extractive_answer(
        question, [_doc(text, source_type=source_type)], max_items=6, max_chars=1800,
    )


def test_default_first_action_rejects_unasked_exception_and_uses_adjacent_context():
    text = (
        "Section 6. For Emergency Incidents\n"
        "In case of business trip emergency cases, such as sickness or accidents, the following procedures apply.\n"
        "6.1 Employee will inform (e-mail or phone call) his/her Immediate Superior about the emergency case.\n"
        "Note: If in case the immediate superior is not available or could not be contacted, "
        "the employee may call any of his co-employee during the business trip."
    )
    answer, info = _extract(
        "In case of sickness or accident during a business trip, who should the employee inform first?", text
    )
    assert "Immediate Superior" in answer, (answer, info)
    assert "co-employee" not in answer
    assert info["decision"] == "accepted"
    assert info["target"] == "notify"


def test_explicit_fallback_question_can_use_exception():
    text = (
        "The employee should inform the supervisor first when a workplace incident occurs. "
        "If the supervisor is unavailable, the employee may call a co-worker for assistance."
    )
    answer, info = _extract("Who should the employee call if the supervisor is unavailable?", text)
    assert "co-worker" in answer, (answer, info)


def test_who_shoulder_selects_payer_not_process_description():
    text = (
        "4.1 Transportation Expenses\n"
        "If a flight is delayed, employees may request transportation from an airline officer.\n"
        "Any expenses for delayed flight transportation should be appropriately shouldered by the airline.\n"
        "4.2 Hotel Accommodation\n"
        "If an overnight flight delay requires a hotel stay, employees may request hotel accommodation charged to the airline."
    )
    answer, info = _extract(
        "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?", text
    )
    assert "shouldered by the airline" in answer, (answer, info)
    assert "hotel accommodation charged to the airline" in answer, (answer, info)
    assert info["target"] == "payment"


def test_multi_object_question_defers_if_evidence_covers_only_one():
    text = "Delayed transportation expenses should be shouldered by the airline."
    answer, info = _extract(
        "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?", text
    )
    assert answer == ""
    assert info.get("decision", "no-candidates") in {"compound-target-incomplete", "answer-target-not-met", "no-candidates"}


def test_requested_object_remains_relevant_not_unrelated_neighbor():
    text = (
        "An employee may request replacement access cards after a lost badge.\n"
        "If a flight delay requires an overnight stay, the employee should request hotel arrangements from the airline officer."
    )
    answer, info = _extract(
        "If a flight delay requires an overnight stay, what should the employee request from the airline officer?", text
    )
    assert "hotel arrangements" in answer, (answer, info)
    assert "replacement access cards" not in answer


def test_no_answer_target_causes_fast_path_to_defer():
    text = "Flight delay procedure: the immediate supervisor is listed on the travel approval sheet."
    answer, info = _extract("Who should inform the administrative manager during the flight delay?", text)
    assert not answer


def test_permissible_sources_unchanged_and_private_records_not_eligible():
    text = "The employee should inform the supervisor first when an incident occurs."
    answer, _ = _extract("Who should the employee inform first in an incident?", text, source_type="live_employee")
    assert answer == ""


@pytest.mark.parametrize("query, target", [
    ("Who should shoulder expenses?", "payment"),
    ("Who is responsible for notifying the administrator?", "notify"),
    ("In case of emergency, who should the employee inform first?", "notify"),
    ("If an overnight stay is needed, what should the employee request?", "request"),
    ("Who should approve the leave request?", "approve"),
    ("Who should submit an overtime request?", "submit"),
    ("Who should provide approval for a request?", "provide"),
    ("Who are the managers?", None),
    ("What is my disciplinary case status?", None),
])
def test_generic_action_grammar(query, target):
    assert _direct_action_target(query) == target


def test_unasked_exception_only_detected_not_arbitrary_condition():
    assert _exception_only_sentence(
        "If the supervisor is not available, contact the administrator instead."
    )
    assert not _exception_only_sentence(
        "If the flight is delayed, request accommodation from the airline."
    )


def test_timing_stage_labels_and_version_markers():
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules/smart_ai/portal_ai.py").read_text(encoding="utf-8")
    assert "FILE SEARCH TIMING" in source
    assert "CHUNK SEARCH TIMING" in source
    assert "KNOWLEDGE BUILD TIMING" in source
    assert "RETRIEVAL TIMING" in source
    assert "EXTRACTIVE VALIDATION TIMING" in source
    assert "RERANK TIMING" in source
    for field in ("model_setup_s", "index_s", "query_embed_s", "qdrant_query_s"):
        assert field in source
    assert 'app_version: str = "0.8.8.227"' in (root / 'config/settings.py').read_text(encoding='utf-8')
