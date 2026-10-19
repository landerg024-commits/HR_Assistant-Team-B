"""v8.8.230 — direct-fact fidelity, bounded retry, Streamlit watcher QA."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _grounded_extractive_answer,
    _explicit_notification_recipients,
)
from scripts.run_with_terminal_log import capture


def doc(text: str, *, file_key: str="policy:one", company: int=1, source: str="procedure.docx") -> RetrievedDocument:
    return RetrievedDocument(KnowledgeDocument(
        document_id=f"{file_key}:{len(text)}", text=text, title="Procedure",
        source_type="policy", company_id=company, role_scope="shared",
        metadata={"filename": source, "file_key": file_key, "section": "Procedure", "version": "1"},
    ), 0.9)


def ask(q: str, docs: list[RetrievedDocument]):
    return _grounded_extractive_answer(q, docs, max_items=6, max_chars=1800)


def test_recipient_parser_does_not_confuse_airports_or_simple_questions():
    q = "Who is responsible for notifying the North Admin Manager, General Manager, and Partner Office about a delayed flight?"
    assert _explicit_notification_recipients(q, target="notify") == (
        "north admin manager", "general manager", "partner office",
    )
    assert _explicit_notification_recipients("Who should notify the manager about an incident?", target="notify") == ()
    assert _explicit_notification_recipients("Where are Philippine and Japan airports?", target="notify") == ()


def test_question_two_prefers_complete_recipient_list_over_coordination_sentence():
    q = "Who is responsible for notifying the North Admin Manager, General Manager, and Partner Office about the delayed flight?"
    d = doc(
        "The direct supervisor is in charge of informing the North Admin Manager, General Manager and Partner Office about the delayed flight. "
        "Hence the direct supervisor shall coordinate with the Admin Manager and Partner Office on informing the clients about the delay."
    )
    answer, meta = ask(q, [d])
    assert "General Manager" in answer
    assert "in charge of informing" in answer
    assert "informing the clients" not in answer
    assert meta["decision"] == "accepted-explicit-recipient-coverage"


def test_question_two_declines_without_every_named_recipient():
    q = "Who should notify the North Admin Manager, General Manager and Partner Office about the incident?"
    answer, meta = ask(q, [doc("The direct supervisor shall coordinate with the North Admin Manager and Partner Office to inform clients about the incident.")])
    assert answer == ""
    assert meta["decision"] == "explicit-recipients-incomplete"


def test_question_three_expenses_split_across_same_original_policy_file():
    q = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"
    transport = doc(
        "4.1 Transportation Expenses In case of a flight delay, the passenger may request transport from the airline officer. "
        "Any incurred expenses brought about by the delayed flight should be appropriately shouldered by the airline.",
        file_key="policy:transit"
    )
    hotel = doc(
        "4.2 Hotel Accommodation If a flight delay requires an overnight stay, the employee may request "
        "a hotel accommodation charged to the airline.",
        file_key="policy:transit"
    )
    answer, meta = ask(q, [transport, hotel])
    assert meta["decision"] == "accepted-compound-action-coverage", meta
    assert "Transportation Expenses" in answer
    assert "shouldered by the airline" in answer
    assert "hotel accommodation charged to the airline" in answer
    assert "food expenses" not in answer
    assert len(meta["sources"]) == 1


def test_compound_refuses_cross_tenant_and_cross_file_claim_merge():
    q = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"
    transport = doc("Transportation expenses for delays should be shouldered by the airline.", file_key="p:a")
    hotel = doc("The hotel accommodation expenses should be paid by the airline.", file_key="p:b")
    answer, meta = ask(q, [transport, hotel])
    assert answer == "" and meta["decision"] == "compound-action-coverage-incomplete"
    hotel = doc("The hotel accommodation expenses should be paid by the airline.", file_key="p:a", company=2)
    answer, meta = ask(q, [transport, hotel])
    assert answer == "" and meta["decision"] == "compound-action-coverage-incomplete"


def test_payment_question_does_not_take_unavailable_transport_condition_as_paid_transport():
    q = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"
    text = "If no transportation is available after a flight delay, the hotel accommodation should be charged to the airline."
    answer, meta = ask(q, [doc(text)])
    assert answer == ""
    assert meta["decision"] == "compound-action-coverage-incomplete"


def test_existing_first_contact_unchanged():
    answer, _ = ask(
        "If someone is sick during a business trip, who should the employee inform first?",
        [doc("The employee must inform the immediate superior first. If unavailable, contact a colleague instead.")],
    )
    assert "immediate superior" in answer and "colleague" not in answer


def test_launcher_disables_file_watcher_but_respects_explicit_override(tmp_path, monkeypatch):
    cmd = [sys.executable, "-u", "-c", "import os;print(os.environ.get('STREAMLIT_SERVER_FILE_WATCHER_TYPE'))"]
    monkeypatch.delenv("STREAMLIT_SERVER_FILE_WATCHER_TYPE", raising=False)
    assert capture(cmd, root=tmp_path, log_dir=tmp_path / "logs") == 0
    log = sorted((tmp_path / "logs").glob("Terminal_Session_*.log"))[-1]
    assert "Streamlit file watcher: none" in log.read_text(encoding="utf-8")
    monkeypatch.setenv("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "auto")
    assert capture(cmd, root=tmp_path, log_dir=tmp_path / "logs_alt") == 0
    log = next((tmp_path / "logs_alt").glob("Terminal_Session_*.log"))
    assert "Streamlit file watcher: auto" in log.read_text(encoding="utf-8")


def test_only_rejected_direct_fact_gets_a_short_no_retry_budget():
    root = Path(__file__).resolve().parents[1]
    source = (root / "modules/smart_ai/portal_ai.py").read_text(encoding="utf-8")
    settings = (root / "config/chat_assistant_settings.py").read_text(encoding="utf-8")
    assert 'direct_fact_rejected = True' in source
    assert 'and not direct_fact_rejected' in source
    assert 'if direct_fact_rejected:' in source
    assert 'UNDETERMINED_ANSWER if direct_fact_rejected' in source
    assert 'grounded_direct_fact_ollama_timeout_seconds: int = 30' in settings


def test_end_to_end_answer_selection_uses_correct_receivers_without_ollama(monkeypatch):
    from authentication.current_user import AuthenticatedUser
    from modules.hr_assistant.hr_assistant import HRAssistantResponse
    from modules.smart_ai import portal_ai

    q = "Who is responsible for notifying the North Admin Manager, General Manager, and Partner Office about the delayed flight?"
    policy = doc(
        "The direct supervisor is in charge of informing the North Admin Manager, General Manager and Partner Office about the delayed flight. "
        "Hence the direct supervisor shall coordinate with the Admin Manager and Partner Office on informing clients about the delay."
    )
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kwargs: [policy.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *args, **kwargs: [policy])
    monkeypatch.setattr(assistant.ollama, "generate", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No Qwen expected")))
    u = AuthenticatedUser(
        user_id=1, company_id=1, company_code="QA", company_name="QA", role_id=1,
        role_name="Admin", clearance=1, username="admin", email="qa@example.com",
        employee_id=None, employee_number=None, employee_name=None,
        must_change_password=False,
    )
    result = assistant.enhance(
        current_user=u, role_scope="admin", question=q, history=[],
        deterministic_response=HRAssistantResponse(answer=policy.document.text, intent="policy_fallback"),
    )
    assert "General Manager" in result.answer
    assert "in charge of informing" in result.answer
    assert "informing clients" not in result.answer


def test_end_to_end_multi_fact_skips_ollama_when_two_sections_are_grounded(monkeypatch):
    from authentication.current_user import AuthenticatedUser
    from modules.hr_assistant.hr_assistant import HRAssistantResponse
    from modules.smart_ai import portal_ai

    q = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"
    d1 = doc(
        "4.1 Transportation Expenses In case of delayed flights, the employee may request transport from an airline officer. "
        "Any incurred expenses brought about by the delayed flight should be appropriately shouldered by the airline.",
        file_key="policy:document:1",
    )
    d2 = doc(
        "4.2 Hotel Accommodation If an overnight stay is needed due to a delayed flight, "
        "the employee may request hotel accommodation charged to the airline.",
        file_key="policy:document:1",
    )
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kwargs: [d1.document, d2.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *args, **kwargs: [d1, d2])
    monkeypatch.setattr(assistant.ollama, "generate", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No Qwen expected")))
    u = AuthenticatedUser(
        user_id=1, company_id=1, company_code="QA", company_name="QA", role_id=1,
        role_name="Admin", clearance=1, username="admin", email="qa@example.com",
        employee_id=None, employee_number=None, employee_name=None, must_change_password=False,
    )
    result = assistant.enhance(
        current_user=u, role_scope="admin", question=q, history=[],
        deterministic_response=HRAssistantResponse(answer=d1.document.text+" "+d2.document.text, intent="policy_fallback"),
    )
    assert "shouldered by the airline" in result.answer
    assert "hotel accommodation charged to the airline" in result.answer


def test_rejected_direct_fact_runs_one_bounded_model_call_without_retry(monkeypatch):
    from authentication.current_user import AuthenticatedUser
    from modules.hr_assistant.hr_assistant import HRAssistantResponse
    from modules.smart_ai import portal_ai
    from services.runtime_connection_service import RuntimeServiceTimeoutError

    q = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"
    retrieved = doc(
        "Transportation expenses caused by delayed flights should be shouldered by the airline. "
        "Hotel accommodation is arranged by the airline officer if the flight is delayed."
    )
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kwargs: [retrieved.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *args, **kwargs: [retrieved])
    monkeypatch.setattr(portal_ai, "_grounded_extractive_answer", lambda *args, **kwargs: (
        "", {"decision": "compound-action-coverage-incomplete", "target": "payment"}
    ))
    monkeypatch.setattr(portal_ai, "log_runtime_connection_issue", lambda *args, **kwargs: None)
    calls = []

    def slow_generate(_prompt, *, quality, timeout_seconds=None):
        calls.append((quality, timeout_seconds))
        raise RuntimeServiceTimeoutError("ollama", operation="generation", timeout_seconds=timeout_seconds)

    monkeypatch.setattr(assistant.ollama, "generate", slow_generate)
    user = AuthenticatedUser(
        user_id=1, company_id=1, company_code="QA", company_name="QA", role_id=1,
        role_name="Admin", clearance=1, username="admin", email="qa@example.com",
        employee_id=None, employee_number=None, employee_name=None, must_change_password=False,
    )
    answer = assistant.enhance(
        current_user=user, role_scope="admin", question=q, history=[],
        deterministic_response=HRAssistantResponse(answer=retrieved.document.text, intent="policy_fallback"),
    )
    assert calls == [(False, 30.0)]
    assert "Cannot be determined" in answer.answer
    assert answer.runtime_warning_code is not None
