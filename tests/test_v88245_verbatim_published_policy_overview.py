"""Generic, company-safe RAG regressions for whole text-only policy summaries.

No seeded HR records, production policy details, or question answer keys.
"""

from authentication.current_user import AuthenticatedUser
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.smart_ai import portal_ai


def _overview(question, items, **kwargs):
    return portal_ai._verbatim_published_policy_overview(
        question, items, company_id=41, role_scope="admin", **kwargs
    )


def _record(title="Equipment Return Policy", *, company=41, body=None, **metadata_overrides):
    body = body or (
        "Employees must return issued equipment to the equipment desk. "
        "The desk records each item in the company asset register. "
        "Damaged items must be flagged before the return is marked complete."
    )
    metadata = {
        "policy_id": 121, "file_key": "policy:121:record", "title": title,
        "version": "1.0", "section": "Published Policy Text",
        "filename": title, "chunk_index": 1, "total_chunks": 1,
    }
    metadata.update(metadata_overrides)
    doc = portal_ai.KnowledgeDocument(
        "company:41:policy:121:record:1",
        f"Policy: {title}. Version: 1.0. Section: Published Policy Text. {body}",
        f"{title} — Published Policy Text", "policy", company,
        "shared", metadata,
    )
    return portal_ai.RetrievedDocument(doc, 0.041)


def _user():
    return AuthenticatedUser(
        user_id=1, company_id=41, company_code="QA", company_name="Test",
        role_id=1, role_name="admin", clearance=1, username="tester",
        email="test@example.invalid", employee_id=None, employee_number=None,
        employee_name=None, must_change_password=False,
    )


def test_published_overview_returns_complete_verbatim_source_not_rewritten():
    result = _record()
    answer, details = _overview(
        "What is the company's equipment return policy?", [result]
    )
    assert answer == portal_ai._document_body_text(result.document)
    assert details["decision"] == "accepted"
    assert details["policy_id"] == "121"


def test_overview_refuses_scenarios_uploaded_chunks_partial_and_ambiguous_sources():
    record = _record()
    requests = [
        "What is the equipment return policy for contractors?",
        "Does the equipment return policy allow exceptions?",
        "What is the equipment return policy and how many items are missing?",
        "What happens under the equipment return policy if an item is lost?",
    ]
    for question in requests:
        assert not _overview(question, [record])[0]

    assert not _overview(
        "What is the equipment return policy?",
        [_record(total_chunks=2)],
    )[0]
    assert not _overview(
        "What is the equipment return policy?",
        [_record(file_key="policy:121:uploaded")],
    )[0]
    assert not _overview(
        "What is the equipment return policy?",
        [_record(), _record(policy_id=122, file_key="policy:122:record")],
    )[0]
    assert not _overview(
        "What is the equipment return policy?",
        [_record(body="Only a partial clause.")],
    )[0]
    assert not _overview(
        "What is the equipment return policy?",
        [_record()], max_chars=60,
    )[0]


def test_overview_never_substitutes_topically_similar_policy():
    reply, details = _overview(
        "What is the laptop allocation policy?", [_record()]
    )
    assert not reply and details["decision"] == "none-or-ambiguous-policy"


def test_integration_misrouted_leave_like_summary_skips_ollama(monkeypatch):
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(assistant.settings, "grounded_extractive_fast_path_enabled", True)
    source = _record()
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kw: [source.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw: [source])
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("Ollama must not run")))
    result = assistant.enhance(
        current_user=_user(), role_scope="admin",
        question="What is the company's equipment return policy?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Inventory summary for the current year.",
            intent="leave_summary", sources=[],
        ),
    )
    assert "Employees must return issued equipment" in result.answer
    assert "inventory summary" not in result.answer.casefold()
    assert result.sources


def test_overview_never_discloses_other_company_or_private_role_source():
    assert not _overview(
        "What is the equipment return policy?", [_record(company=777)]
    )[0]
    private = _record()
    private_doc = portal_ai.KnowledgeDocument(
        private.document.document_id, private.document.text,
        private.document.title, private.document.source_type,
        private.document.company_id, "employee", private.document.metadata
    )
    assert not _overview(
        "What is the equipment return policy?",
        [portal_ai.RetrievedDocument(private_doc, .041)]
    )[0]


def test_title_matched_policy_rules_list_can_return_full_published_text():
    """Generic title matching handles rule-list wording without answer keys."""
    item = _record(title="Equipment Return Policy")
    answer, meta = _overview("What are the equipment return rules?", [item])
    assert answer == portal_ai._document_body_text(item.document)
    assert meta["decision"] == "accepted"

    other = _record(title="Scheduling and Punctuality Policy")
    answer, meta = _overview("What are the scheduling and punctuality rules?", [other])
    assert answer == portal_ai._document_body_text(other.document)
    assert meta["decision"] == "accepted"


def test_rules_overview_does_not_bypass_specific_qualifiers_or_topic_overlap():
    item = _record(title="Equipment Return Policy")
    for question in [
        "What are the equipment return rules for contractors?",
        "What are the equipment return rules for a lost laptop?",
        "What are the equipment return rules and penalties?",
        "What are the return rules?",
        "What are the equipment return exceptions?",
        "What are the equipment return rules compared with new hires?",
    ]:
        answer, _meta = _overview(question, [item])
        assert not answer, question


def test_integration_list_shaped_published_rules_skips_ollama(monkeypatch):
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(assistant.settings, "grounded_extractive_fast_path_enabled", True)
    source = _record(title="Equipment Return Policy")
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kw: [source.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw: [source])
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("Ollama must not run")))
    result = assistant.enhance(
        current_user=_user(), role_scope="admin",
        question="What are the equipment return rules?", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the equipment portal.", intent="attendance", sources=[],
        ),
    )
    assert "Employees must return issued equipment" in result.answer
    assert "equipment portal" not in result.answer.casefold()
    assert result.sources


def test_unverified_router_hint_does_not_enter_llm_prompt(monkeypatch):
    """Unverified navigation hints must not become model-visible pseudo-evidence."""
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    monkeypatch.setattr(assistant.settings, "grounded_extractive_fast_path_enabled", False)
    monkeypatch.setattr(assistant.settings, "llm_mode", "local")
    source = _record()
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kw: [source.document])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw: [source])
    captured = {}
    original = portal_ai.build_hr_assistant_prompt

    def capture_prompt(**kwargs):
        captured["router_answer"] = kwargs["router_answer"]
        return original(**kwargs)

    monkeypatch.setattr(portal_ai, "build_hr_assistant_prompt", capture_prompt)
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        "Employees must return issued equipment to the equipment desk.")
    assistant.enhance(
        current_user=_user(), role_scope="admin",
        question="Explain the equipment return process.", history=[],
        deterministic_response=HRAssistantResponse(
            answer="Open the employee portal to view attendance.",
            intent="attendance", sources=[],
        ),
    )
    assert captured["router_answer"] == ""
