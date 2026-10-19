"""Generic RAG regressions for editor-created policies and unsupported rules.

Contains no evaluation answer keys, expected tenant policy text, or fixture links
into the production RAG corpus.
"""
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.hr_policy import HRPolicy
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.smart_ai import portal_ai
from authentication.current_user import AuthenticatedUser


def _user(company=17):
    return AuthenticatedUser(
        user_id=1, company_id=company, company_code="TEST", company_name="Test",
        role_id=1, role_name="admin", clearance=1, username="tester",
        email="test@example.invalid", employee_id=None, employee_number=None,
        employee_name=None, must_change_password=False,
    )


def _policy(*, company, title, content, status="published", effective=None):
    return HRPolicy(company_id=company, created_by_user_id=1, title=title,
                    category="HR", summary="", content=content, version="1.0",
                    status=status, effective_date=effective)


def _minimal_policy_db():
    engine = create_engine("sqlite:///:memory:")
    HRPolicy.__table__.create(engine)
    return engine


def _stub_live(monkeypatch):
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "_add_live_company_records",
                        lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(portal_ai.PolicyViolationService, "list_employee_visible",
                        lambda self, **_kw: [])
    monkeypatch.setattr(portal_ai.PolicySectionRepository, "list_searchable",
                        lambda self, **_kw: [])


def test_editor_policies_are_retrievable_and_still_company_status_date_safe(monkeypatch):
    engine = _minimal_policy_db()
    _stub_live(monkeypatch)
    today = date.today()
    with Session(engine) as session:
        active = _policy(company=17, title="Equipment Returns", content=(
            "Employees must return all checked-out safety equipment to the store "
            "before their final shift ends. The store keeper must record each return."
        ))
        session.add_all([
            active,
            _policy(company=17, title="Withdrawn", content="Disallowed obsolete guidance", status="trashed"),
            _policy(company=17, title="Unpublished", content="Disallowed draft guidance", status="draft"),
            _policy(company=17, title="Future", content="Disallowed future guidance", effective=today + timedelta(days=90)),
            _policy(company=99, title="Other Tenant", content="Disallowed other-company guidance"),
        ])
        session.commit()
        docs = portal_ai.PortalKnowledgeBuilder(session).build(current_user=_user(), role_scope="employee")
        policies = [d for d in docs if d.source_type == "policy"]
        assert len(policies) == 1
        found = policies[0]
        assert found.company_id == 17 and found.role_scope == "shared"
        assert found.metadata["policy_id"] == active.id
        assert "store keeper must record" in found.text.lower()
        assert found.metadata["filename"] == active.title
        assert found.metadata["file_key"] and found.metadata["chunk_index"] == 1
        # The normal BM25/file selection pipeline, not just the builder,
        # must now surface the previously missing policy.
        monkeypatch.setattr(portal_ai.QdrantRetriever, "search", lambda *a, **kw: [])
        matched = portal_ai.HybridRetriever().search(
            "Who must record equipment returns?", docs,
            company_id=17, role_scope="employee")
        assert any(x.document.metadata.get("policy_id") == active.id for x in matched)
        assert all(x.document.company_id == 17 for x in matched)
    engine.dispose()


def test_uploaded_sections_take_precedence_over_editor_policy_body(monkeypatch):
    engine = _minimal_policy_db()
    _stub_live(monkeypatch)
    with Session(engine) as session:
        record = _policy(company=17, title="Shift Handover", content="Full policy editor backup.")
        session.add(record); session.commit()
        document = SimpleNamespace(id=8, original_filename="shift-handover.pdf")
        section = SimpleNamespace(heading="Records", text="Handover must be signed.", page_number=1)
        monkeypatch.setattr(portal_ai.PolicySectionRepository, "list_searchable",
                            lambda self, **kwargs: [(record, document, section)])
        docs = portal_ai.PortalKnowledgeBuilder(session).build(current_user=_user(), role_scope="admin")
        policy_docs = [d for d in docs if d.source_type == "policy"]
        assert len(policy_docs) == 1
        assert policy_docs[0].metadata["policy_document_id"] == 8
        assert "editor backup" not in policy_docs[0].text.lower()
    engine.dispose()


def test_unsupported_normative_rule_abstains_without_local_generation(monkeypatch):
    assistant = portal_ai.SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, "terminal_debug_enabled", False)
    monkeypatch.setattr(assistant.settings, "terminal_debug_log_enabled", False)
    unrelated = portal_ai.KnowledgeDocument(
        "company:17:portal:guide", "Staff can request inventory reports from the portal.",
        "Inventory Help", "portal_guide", 17, "shared", {"title":"Inventory Help"},
    )
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder, "build", lambda self, **kw: [unrelated])
    monkeypatch.setattr(assistant.retriever, "search", lambda *a, **kw:
                        [portal_ai.RetrievedDocument(unrelated, .9)])
    monkeypatch.setattr(assistant.ollama, "generate", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("Ollama must be skipped")))
    response = assistant.enhance(
        current_user=_user(), role_scope="admin",
        question="What happens if a worker fails the protective-gear inspection?",
        history=[],
        deterministic_response=HRAssistantResponse(
            answer="Visit the attendance menu to see reports.", intent="attendance",
        ),
    )
    assert response.answer == portal_ai.NOT_FOUND_ANSWER
    assert not response.sources
