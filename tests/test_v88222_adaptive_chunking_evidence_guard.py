"""v8.8.222 adaptive chunking, evidence gating, and diagnostics regressions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modules.smart_ai.portal_ai import (
    HybridRetriever,
    KnowledgeDocument,
    RetrievedDocument,
    SmartPortalAssistant,
    _prepare_document_chunks_detailed,
)
from modules.smart_ai.terminal_trace import TerminalChatTrace


ROOT = Path(__file__).resolve().parents[1]


def _doc(
    doc_id: str,
    text: str,
    *,
    chunk_index: int = 1,
    section_chunk_index: int = 1,
    section_chunk_total: int = 1,
    continuation_before: int = 0,
    continuation_after: int = 0,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=doc_id,
        text=text,
        title="Leave Policy — Carry-over",
        source_type="policy",
        company_id=1,
        role_scope="shared",
        metadata={
            "file_key": "policy:leave",
            "filename": "Leave Policy.pdf",
            "section": "Carry-over",
            "chunk_index": chunk_index,
            "total_chunks": 3,
            "section_chunk_index": section_chunk_index,
            "section_chunk_total": section_chunk_total,
            "continuation_before": continuation_before,
            "continuation_after": continuation_after,
        },
    )


def test_adaptive_chunking_keeps_complete_semantic_section_intact() -> None:
    text = " ".join(f"word{index}" for index in range(250))
    chunks = _prepare_document_chunks_detailed(
        [("Annual Leave", text, 4)],
        chunk_size=260,
        overlap=48,
        adaptive=True,
        min_words=120,
        target_words=220,
        max_words=300,
        overlap_ratio=0.14,
        overlap_min_words=16,
        overlap_max_words=44,
    )

    assert len(chunks) == 1
    assert chunks[0].word_count == 250
    assert chunks[0].boundary_reason == "semantic_section"
    assert chunks[0].overlap_words == 0
    assert chunks[0].section_chunk_total == 1
    assert chunks[0].continuation_before is False
    assert chunks[0].continuation_after is False


def test_adaptive_chunking_splits_long_section_with_bounded_overlap_and_metadata() -> None:
    text = " ".join(
        f"Sentence {index} states a company leave condition and supporting detail."
        for index in range(1, 101)
    )
    chunks = _prepare_document_chunks_detailed(
        [("Carry-over", text, 8)],
        chunk_size=260,
        overlap=48,
        adaptive=True,
        min_words=120,
        target_words=220,
        max_words=300,
        overlap_ratio=0.14,
        overlap_min_words=16,
        overlap_max_words=44,
    )

    assert len(chunks) >= 3
    assert all(chunk.word_count <= 300 for chunk in chunks)
    assert all(chunk.section_chunk_total == len(chunks) for chunk in chunks)
    assert chunks[0].continuation_before is False
    assert chunks[0].continuation_after is True
    assert chunks[-1].continuation_before is True
    assert chunks[-1].continuation_after is False
    assert any(chunk.overlap_words > 0 for chunk in chunks[1:])
    assert all(chunk.overlap_words <= 44 for chunk in chunks)
    assert {chunk.boundary_reason for chunk in chunks}.intersection(
        {"target_boundary", "hard_max_boundary", "section_tail"}
    )


def test_adaptive_chunking_prefers_clause_boundaries_before_word_fallback() -> None:
    clause = " ".join(f"term{index}" for index in range(70))
    text = "; ".join([clause, clause, clause, clause, clause])
    chunks = _prepare_document_chunks_detailed(
        [("Long Rule", text, None)],
        chunk_size=260,
        overlap=48,
        adaptive=True,
        min_words=120,
        target_words=180,
        max_words=220,
        overlap_ratio=0.14,
        overlap_min_words=16,
        overlap_max_words=44,
    )

    assert len(chunks) >= 2
    assert all(chunk.word_count <= 220 for chunk in chunks)
    assert any(chunk.boundary_reason == "clause_boundary" for chunk in chunks)
    assert not all(chunk.boundary_reason == "word_fallback" for chunk in chunks)


def test_neighbor_expansion_only_uses_split_section_continuations(monkeypatch) -> None:
    retriever = HybridRetriever()
    monkeypatch.setattr(retriever.settings, "final_top_k", 2)
    monkeypatch.setattr(retriever.settings, "neighbor_chunk_window", 1)

    intact = _doc(
        "intact",
        "Managers may carry over thirteen vacation leave credits.",
        chunk_index=1,
    )
    unrelated_neighbor = _doc(
        "intact-next",
        "Unrelated next section details.",
        chunk_index=2,
    )
    intact_result = retriever._expand_neighbors(
        "How many vacation leave credits can managers carry over?",
        [RetrievedDocument(intact, 1.0)],
        {"policy:leave": [intact, unrelated_neighbor]},
        fallback_candidates=[],
    )
    assert [item.document.document_id for item in intact_result] == ["intact"]

    split = _doc(
        "split-1",
        "Managers may carry over vacation leave credits subject to the following limit:",
        chunk_index=1,
        section_chunk_index=1,
        section_chunk_total=2,
        continuation_after=1,
    )
    continuation = _doc(
        "split-2",
        "The maximum carry-over is thirteen vacation leave credits.",
        chunk_index=2,
        section_chunk_index=2,
        section_chunk_total=2,
        continuation_before=1,
    )
    split_result = retriever._expand_neighbors(
        "How many vacation leave credits can managers carry over?",
        [RetrievedDocument(split, 1.0)],
        {"policy:leave": [split, continuation]},
        fallback_candidates=[],
    )
    assert [item.document.document_id for item in split_result] == [
        "split-1",
        "split-2",
    ]


def test_exact_fact_evidence_gate_rejects_topic_only_amount_match() -> None:
    weak = KnowledgeDocument(
        document_id="weak",
        text="Taxi reimbursement requests require supervisor review.",
        title="Taxi reimbursement policy",
        source_type="policy",
        company_id=1,
        role_scope="shared",
        metadata={"filename": "Taxi Policy.pdf"},
    )
    result = SmartPortalAssistant._retrieval_relevance_snapshot(
        query="What is the maximum taxi reimbursement amount?",
        retrieved=[RetrievedDocument(weak, 1.0)],
        require_answer_cue=True,
        min_answer_cue=0.70,
    )

    assert result["accepted"] is False
    assert result["evidence_profile"] == "amount"
    assert float(result["answer_cue"]) < 0.70
    assert "answer-bearing fact" in str(result["reason"])


def test_exact_fact_evidence_gate_accepts_direct_supported_amount() -> None:
    strong = KnowledgeDocument(
        document_id="strong",
        text="The maximum taxi reimbursement is P300.00 per day.",
        title="Taxi reimbursement policy",
        source_type="policy",
        company_id=1,
        role_scope="shared",
        metadata={"filename": "Taxi Policy.pdf"},
    )
    result = SmartPortalAssistant._retrieval_relevance_snapshot(
        query="What is the maximum taxi reimbursement amount?",
        retrieved=[RetrievedDocument(strong, 1.0)],
        require_answer_cue=True,
        min_answer_cue=0.70,
    )

    assert result["accepted"] is True
    assert float(result["answer_cue"]) == 1.0


def test_chunk_diagnostics_are_written_without_full_chunk_text_by_default(tmp_path) -> None:
    secret_text = "PRIVATE_CHUNK_TEXT_SHOULD_NOT_BE_DUPLICATED"
    settings = SimpleNamespace(
        terminal_debug_enabled=True,
        terminal_debug_top_k=10,
        terminal_debug_excerpt_chars=520,
        terminal_debug_answer_chars=1800,
        terminal_debug_candidate_answer_chars=760,
        terminal_debug_log_enabled=True,
        terminal_debug_log_dir=str(tmp_path),
        chunk_diagnostics_enabled=True,
        chunk_diagnostics_full_text=False,
    )
    trace = TerminalChatTrace.create(settings)
    trace.chunking_file(
        source="policy",
        filename="Leave Policy.pdf",
        sections=1,
        chunks=[
            {
                "section": "Carry-over",
                "text": secret_text,
                "page_number": 8,
                "word_count": 210,
                "overlap_words": 31,
                "boundary_reason": "target_boundary",
                "section_chunk_index": 1,
                "section_chunk_total": 2,
            }
        ],
        strategy="adaptive-structure-aware",
        min_words=120,
        target_words=220,
        max_words=300,
        overlap_ratio=0.14,
    )
    trace.chunking_batch_summary(
        [{"filename": "Leave Policy.pdf", "sections": 1, "chunks": 1, "word_fallbacks": 0}]
    )
    trace.finish(status="test")

    assert trace.log_path
    log_text = Path(trace.log_path).read_text(encoding="utf-8")
    assert "CHUNK DIAGNOSTICS" in log_text
    assert "CHUNKING BATCH SUMMARY" in log_text
    assert "target_boundary" in log_text
    assert secret_text not in log_text


def test_v88222_settings_version_and_documentation() -> None:
    settings = (ROOT / "config/chat_assistant_settings.py").read_text(encoding="utf-8")
    app_settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'app_version: str = "0.8.8.222"' in app_settings
    assert env.splitlines()[1] == "APP_VERSION=0.8.8.222"
    assert "adaptive_chunking_enabled: bool = True" in settings
    assert "policy_chunk_target_words: int = 220" in settings
    assert "company_document_chunk_target_words: int = 280" in settings
    assert "evidence_gate_min_answer_cue: float = 0.70" in settings
    assert "SMART_AI_CHUNK_DIAGNOSTICS_FULL_TEXT=false" in env
    assert "v8.8.222 — Adaptive Chunking, Evidence Gate & Chunk Diagnostics" in readme
