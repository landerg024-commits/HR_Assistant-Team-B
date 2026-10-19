"""Generic 8.8.240 RAG component regression tests, no QA answers embedded."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _document_search_text,
    _record_answer_relevance, _rerank_candidates,
    _prepare_document_chunks_detailed, _focused_evidence_excerpt,
)


def doc(section, text, key="sample"):
    return KnowledgeDocument("doc_"+section, text, "Policy Handbook", "policy", 3, "shared",
                             {"section": section, "filename": key + ".docx", "file_key": key})


def test_topic_guard_rejects_unrelated_live_record_not_generic_human_terms():
    assert not _record_answer_relevance("What are the qualification conditions for a certification program?",
                                        "Employee record: administrator email and hierarchy manager")
    assert _record_answer_relevance("What are the qualification conditions for a certification program?",
                                     "Certification program eligibility conditions include work experience")
    assert _record_answer_relevance("Show my details", "My account has two approvals")  # pronouns allowed


def test_section_heading_in_searchable_evidence():
    source = doc("Section 8 - Approval Conditions", "A manager verifies the request.")
    assert "Approval Conditions" in _document_search_text(source)


def test_reranker_combines_hybrid_and_source_relevance_without_llm():
    class Mock:
        def predict(self, pairs):
            return [-2.0, 2.0]
    candidates = [RetrievedDocument(doc("A", "First rule"), .05),
                  RetrievedDocument(doc("B", "Second rule"), .04)]
    result = _rerank_candidates("What rule applies?", candidates, Mock())
    assert result[0].document.document_id == "doc_B"
    assert all(0 <= x.score <= 1 for x in result)


def test_adaptive_does_not_merge_different_enumerations_in_policy():
    sections = [("A", "1. Step alpha\n2. Step beta", None),
                ("B", "1. Rule gamma\n2. Rule delta", None)]
    chunks = _prepare_document_chunks_detailed(sections, chunk_size=260, overlap=48,
                                               adaptive=True, min_words=120,
                                               target_words=220, max_words=300)
    assert len(chunks) == 2
    assert [x.section for x in chunks] == ["A", "B"]


def test_excerpt_keeps_adjacent_list_rows():
    text = "Introduction sentence.\n- First permitted action\n- Second permitted action\n- Third permitted action"
    excerpt = _focused_evidence_excerpt("Which permitted actions are there?", text, 500)
    assert "First permitted" in excerpt and "Third permitted" in excerpt


def test_binary_negation_contradiction_fails_closed():
    from modules.smart_ai.portal_ai import SmartPortalAssistant, UNDETERMINED_ANSWER
    result = SmartPortalAssistant._normalize_yes_no_answer(
        "NO. The policy does not disqualify the applicant under this condition.")
    assert result == UNDETERMINED_ANSWER
    assert SmartPortalAssistant._normalize_yes_no_answer("NO. Applicant is excluded.").startswith("**NO.")
