"""Provider-independent, company-safe tests for complete uploaded policy overviews.

Synthetic policy names and text only; never seed production HR answers.
"""
from authentication.current_user import AuthenticatedUser
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.smart_ai import portal_ai
from services.runtime_connection_service import RuntimeServiceTimeoutError


def source_chunks(title="Asset Handling", *, company=41, role="shared", file_id=77,
                  chunk_count=3, overlap=0):
    bodies = [
        f"{title} Award. Policy Statement. The organization maintains an asset handling program. "
        "Employees can request approved equipment for assigned duties.",
        "Eligibility. Assigned employees must sign the equipment register. "
        "Records are maintained by the authorized asset custodian.",
        "Example: For the January 2011 example period the illustrated reward was 100 pesos. "
        "This is an example for the dated period, not a current payout statement.",
    ][:chunk_count]
    rows = []
    for i, body in enumerate(bodies, 1):
        metadata = {
            "policy_id": 25, "policy_document_id": file_id,
            "file_key": f"policy:25:document:{file_id}",
            "title": title, "filename": "asset-handling.docx", "version": "1.0",
            "section": f"Section {i}", "chunk_index": i,
            "total_chunks": chunk_count, "chunk_overlap_words": overlap,
        }
        doc = portal_ai.KnowledgeDocument(
            f"company:{company}:policy:25:{file_id}:{i}",
            f"Policy: {title}. Version: 1.0. Section: Section {i}. {body}",
            f"{title} — Section {i}", "policy", company, role, metadata,
        )
        rows.append(portal_ai.RetrievedDocument(doc, .05-i*.001))
    return rows


def candidate(question, rows, **kwargs):
    return portal_ai._verbatim_complete_document_policy_overview(
        question, rows, company_id=41, role_scope="admin", **kwargs
    )


def user():
    return AuthenticatedUser(
        user_id=1, company_id=41, company_code="Q", company_name="QA",
        role_id=1, role_name="admin", clearance=1, username="tester",
        email="test@example.invalid", employee_id=None,
        employee_number=None, employee_name=None, must_change_password=False,
    )


def assistant_with_rows(monkeypatch, rows):
    assistant = portal_ai.SmartPortalAssistant(None)
    for prop, val in [
        ("terminal_debug_enabled", False), ("terminal_debug_log_enabled", False),
        ("grounded_extractive_fast_path_enabled", True), ("llm_mode", "local"),
    ]:
        monkeypatch.setattr(assistant.settings, prop, val)
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kw: [x.document for x in rows])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw: rows)
    return assistant


def test_whole_uploaded_document_orders_chunks_preserves_text_and_labels_dated_example():
    rows = source_chunks()
    answer, meta = candidate("What is the Asset Handling Award policy?", [rows[2], rows[0], rows[1]])
    assert meta["decision"] == "accepted" and meta["chunks"] == 3
    assert meta["file_key"] == "policy:25:document:77"
    assert answer.index("Policy Statement") < answer.index("Eligibility") < answer.index("Example:")
    assert "dated examples" in answer and "asset-handling.docx" in answer
    for item in rows:
        assert portal_ai._document_body_text(item.document) in answer


def test_no_partial_cross_tenant_other_role_duplicate_mixed_or_overlapping_chunks():
    rows = source_chunks()
    rejected = [
        rows[:2], rows[:1] + rows[2:], [rows[0], rows[0], rows[2]],
        source_chunks(overlap=3), source_chunks(company=999),
        source_chunks(role="employee"), rows + source_chunks(file_id=80),
    ]
    for case in rejected:
        assert not candidate("What is the Asset Handling Award policy?", case)[0]
    assert not candidate("What is the Asset Handling Award policy?", rows, max_chars=90)[0]


def test_only_unqualified_whole_document_requests_are_accepted():
    rows = source_chunks()
    for question in [
        "Who is eligible for the Asset Handling Award?",
        "What is the Asset Handling Award policy for contractors?",
        "What is the Asset Handling Award policy currently?",
        "What is the Asset Handling Award policy and reimbursement rate?",
        "What are the exceptions to the Asset Handling Award policy?",
        "What is the Storage Handling Award policy?",
        "What is the Asset Handling Award policy compared with another policy?",
    ]:
        assert not candidate(question, rows)[0], question


def test_integration_source_overview_skips_ollama_and_never_uses_router_hint(monkeypatch):
    rows = source_chunks()
    assistant = assistant_with_rows(monkeypatch, rows)
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("model must not run")))
    result = assistant.enhance(
        current_user=user(), role_scope="admin",
        question="What is the Asset Handling Award policy?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the dashboard and navigate to attendance.",
            intent="attendance", sources=[],
        ),
    )
    assert "Employees can request approved equipment" in result.answer
    assert "dashboard" not in result.answer.casefold()
    assert result.sources


def test_timeout_without_complete_document_does_not_show_unsourced_navigation(monkeypatch):
    rows = source_chunks()[:2]
    assistant = assistant_with_rows(monkeypatch, rows)
    monkeypatch.setattr(assistant.settings, "ollama_timeout_retry_enabled", False)
    # Treat a normal generation timeout as a real RuntimeServiceTimeoutError.
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(RuntimeServiceTimeoutError("ollama", operation="generation")))
    result = assistant.enhance(
        current_user=user(), role_scope="admin",
        question="What is the Asset Handling Award policy?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the dashboard and navigate to attendance.",
            intent="attendance", sources=[],
        ),
    )
    assert "could not be generated" in result.answer
    assert "dashboard" not in result.answer.casefold()
    assert result.runtime_warning_code


def test_complete_policy_bypasses_cold_vector_retrieval(monkeypatch):
    rows = source_chunks()
    assistant = assistant_with_rows(monkeypatch, rows)
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("vector must not run")))
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("Ollama must not run")))
    result = assistant.enhance(
        current_user=user(), role_scope="admin",
        question="What is the Asset Handling Award policy?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the dashboard.", intent="attendance", sources=[],
        ),
    )
    assert "Eligibility" in result.answer
    assert result.sources


def test_text_only_policy_bypasses_cold_vector_even_when_not_first_document(monkeypatch):
    rows = source_chunks()
    policy = portal_ai.KnowledgeDocument(
        "company:41:policy:199:record:1",
        "Policy: Records Disposal Policy. Version: 1.0. Section: Published Policy Text. "
        "Employees must put confidential printed materials in locked collection bins. "
        "Assigned custodians track disposal receipts and retain them for audit.",
        "Records Disposal Policy — Published Policy Text", "policy", 41, "shared",
        {"policy_id": 199, "file_key": "policy:199:record", "title": "Records Disposal Policy",
         "filename": "Records Disposal Policy", "version": "1.0",
         "section": "Published Policy Text", "chunk_index": 1, "total_chunks": 1},
    )
    assistant = assistant_with_rows(monkeypatch, rows + [portal_ai.RetrievedDocument(policy, 0.03)])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("vector must not run")))
    result = assistant.enhance(
        current_user=user(), role_scope="admin",
        question="What is the records disposal policy?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the dashboard.", intent="attendance", sources=[],
        ),
    )
    assert "locked collection bins" in result.answer
    assert result.sources
