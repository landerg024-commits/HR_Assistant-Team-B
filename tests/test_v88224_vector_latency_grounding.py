"""v8.8.224 vector activation, grounded fast path, and latency regressions."""

from pathlib import Path

from modules.smart_ai.portal_ai import (
    KnowledgeDocument,
    QdrantRetriever,
    RetrievedDocument,
    _grounded_extractive_answer,
)

ROOT = Path(__file__).resolve().parents[1]


def _policy(doc_id: str, text: str, *, title: str, section: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=doc_id,
        text=f"Policy: {title}. Version: 1.0. Section: {section}. {text}",
        title=f"{title} — {section}",
        source_type="policy",
        company_id=1,
        role_scope="shared",
        metadata={
            "title": title,
            "version": "1.0",
            "section": section,
            "filename": f"{title}.docx",
        },
    )


def test_vector_runtime_dependency_is_installed_with_qdrant() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "qdrant-client>=1.19.1,<2.0" in requirements
    assert "sentence-transformers>=6.1.0,<7.0" in requirements


def test_qdrant_signature_is_stable_when_authorized_order_changes() -> None:
    first = _policy("a", "Alpha policy text.", title="Alpha", section="One")
    second = _policy("b", "Beta policy text.", title="Beta", section="Two")
    assert QdrantRetriever._signature([first, second]) == QdrantRetriever._signature(
        [second, first]
    )


def test_grounded_procedure_fast_path_preserves_scope_qualifier() -> None:
    document = _policy(
        "business-visa",
        (
            "Employee on business visa is required to inform his immediate superior "
            "(Supervisory/Managerial Level) if his departure flight in Philippine "
            "International Airport or Japan International Airport will be delayed. "
            "The immediate superior shall then inform the Administrative Manager."
        ),
        title="Business Visa",
        section="Delayed or Cancelled Flight Schedule",
    )
    answer, meta = _grounded_extractive_answer(
        "What should an employee do first if their flight is delayed at the Philippine or Japan International Airport?",
        [RetrievedDocument(document, 0.9)],
        max_items=6,
        max_chars=1800,
    )
    assert "Employee on business visa" in answer
    assert "inform his immediate superior" in answer
    assert "Administrative Manager" not in answer
    assert meta["items"] == 1


def test_grounded_benefit_fast_path_keeps_five_year_facts_and_excludes_ten_year_rule() -> None:
    document = _policy(
        "service-award",
        (
            "Employees who have rendered five (5) years or more of service to the company "
            "are entitled to the following cash awards and benefit, in addition to the "
            "service incentive leaves and plaque of appreciation already provided by the company. "
            "1.1 Five (5) years of service - Five Thousand (P5,000.00) Pesos. "
            "In addition to the Plaque of Recognition given to employee who reached his five (5) "
            "years in the Company, he shall be entitled to a P5,000 worth award in cash or in kind. "
            "The employee shall likewise be given an additional of two (2) days vacation leave "
            "credit and two (2) days sick leave credit. "
            "1.2 Ten (10) years of service - Five Thousand (P5,000.00) Pesos or 10% of latest salary."
        ),
        title="Service Award",
        section="Section 1",
    )
    answer, meta = _grounded_extractive_answer(
        "What benefits are given to employees who reach five years of service?",
        [RetrievedDocument(document, 0.9)],
        max_items=6,
        max_chars=1800,
    )
    assert "P5,000.00" in answer
    assert "Plaque of Recognition" in answer
    assert "two (2) days vacation leave" in answer
    assert "two (2) days sick leave" in answer
    assert "Ten (10) years" not in answer
    assert meta["items"] >= 3


def test_fast_path_settings_and_vector_diagnostics_are_exposed() -> None:
    settings = (ROOT / "config" / "chat_assistant_settings.py").read_text(encoding="utf-8")
    source = (ROOT / "modules" / "smart_ai" / "portal_ai.py").read_text(encoding="utf-8")
    assert "grounded_extractive_fast_path_enabled: bool = True" in settings
    assert "embedding_batch_size: int = 64" in settings
    assert "qdrant_upsert_batch_size: int = 128" in settings
    assert 'trace.line("FILE VECTOR STATUS", self.file_vector.diagnostic)' in source
    assert 'trace.line("CHUNK VECTOR STATUS", self.vector.diagnostic)' in source
    fast_index = source.index('"GROUNDED EXTRACTIVE FAST PATH"')
    ollama_index = source.index('"OLLAMA REQUEST"')
    assert fast_index < ollama_index


def test_enhance_skips_ollama_for_direct_grounded_policy_procedure(monkeypatch) -> None:
    from authentication.current_user import AuthenticatedUser
    from modules.hr_assistant.hr_assistant import HRAssistantResponse
    from modules.smart_ai import portal_ai

    document = _policy(
        "business-visa-fast",
        (
            "Employee on business visa is required to inform his immediate superior "
            "(Supervisory/Managerial Level) if his departure flight in Philippine "
            "International Airport or Japan International Airport will be delayed."
        ),
        title="Business Visa",
        section="Delayed or Cancelled Flight Schedule",
    )
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(
        portal_ai.PortalKnowledgeBuilder,
        "build",
        lambda self, **kwargs: [document],
    )
    monkeypatch.setattr(
        assistant.retriever,
        "search",
        lambda *args, **kwargs: [RetrievedDocument(document, 0.9)],
    )

    def _unexpected_ollama(*args, **kwargs):
        raise AssertionError("Ollama must be skipped for the grounded direct-policy fast path")

    monkeypatch.setattr(assistant.ollama, "generate", _unexpected_ollama)
    user = AuthenticatedUser(
        user_id=1,
        company_id=1,
        company_code="QA",
        company_name="QA Company",
        role_id=1,
        role_name="Admin",
        clearance=1,
        username="admin",
        email="admin@example.com",
        employee_id=None,
        employee_number=None,
        employee_name=None,
        must_change_password=False,
    )
    response = assistant.enhance(
        current_user=user,
        role_scope="admin",
        question=(
            "What should an employee do first if their flight is delayed at the "
            "Philippine or Japan International Airport?"
        ),
        history=[],
        deterministic_response=HRAssistantResponse(
            answer=document.text,
            intent="policy_fallback",
        ),
    )
    assert "Employee on business visa" in response.answer
    assert "inform his immediate superior" in response.answer


def test_v88224_version_and_runtime_tuning_markers() -> None:
    app_settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'app_version: str = "0.8.8.224"' in app_settings
    assert "APP_VERSION=0.8.8.224" in env
    assert "SMART_AI_EMBEDDING_BATCH_SIZE=64" in env
    assert "SMART_AI_QDRANT_UPSERT_BATCH_SIZE=128" in env
    assert "SMART_AI_GROUNDED_EXTRACTIVE_FAST_PATH_ENABLED=true" in env
    assert "SMART_AI_GROUNDED_EXTRACTIVE_MIN_ANCHOR_COVERAGE=0.60" in env
    assert "v8.8.224 — Vector Activation, Grounded Fast Path & Latency Hardening" in readme
