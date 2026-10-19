"""v8.8.210 company-only document-aware chunking/retrieval regressions."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from modules.smart_ai import portal_ai
from modules.smart_ai.portal_ai import HybridRetriever, KnowledgeDocument


ROOT = Path(__file__).resolve().parents[1]


def _doc(
    doc_id: str,
    text: str,
    *,
    title: str,
    source_type: str = "policy",
    company_id: int = 1,
    role_scope: str = "shared",
    file_key: str | None = None,
    chunk_index: int = 1,
    section: str = "General",
) -> KnowledgeDocument:
    metadata = {
        "title": title,
        "section": section,
        "chunk_index": chunk_index,
        "filename": f"{title}.pdf",
    }
    if file_key is not None:
        metadata["file_key"] = file_key
    return KnowledgeDocument(
        document_id=doc_id,
        text=text,
        title=title,
        source_type=source_type,
        company_id=company_id,
        role_scope=role_scope,
        metadata=metadata,
    )


def test_sentence_aware_chunking_preserves_rows_and_uses_overlap() -> None:
    text = (
        "Annual leave credits may be carried over when the company rule allows it. "
        "Unused credits remain subject to the configured annual reset.\n\n"
        "Employee | Credits | Status\n"
        "Ana Cruz | 5 | Available\n"
        "Ben Santos | 2 | Used\n\n"
        + " ".join(
            f"Sentence {index} explains another leave condition."
            for index in range(1, 70)
        )
    )
    chunks = portal_ai._split_text(text, 90, 12)
    assert len(chunks) > 1
    assert any("Ana Cruz | 5 | Available" in chunk for chunk in chunks)
    assert any("Ben Santos | 2 | Used" in chunk for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)
    assert max(len(chunk.split()) for chunk in chunks) <= 90


def test_document_sections_preserve_pages_and_headings() -> None:
    sections = portal_ai._document_sections(
        "Page 1: Intro rule.\nMore details.\n\n"
        "Page 2: Second page rule.\n"
        "## Approval Process\nManager approval is required."
    )
    labels = [label for label, _ in sections]
    assert labels == ["Page 1", "Page 2", "Approval Process"]
    assert "Manager approval" in sections[-1][1]


def test_file_aware_retrieval_filters_company_and_role_and_limits_file_dominance(monkeypatch) -> None:
    retriever = HybridRetriever()
    monkeypatch.setattr(retriever.vector, "search", lambda *_a, **_k: [])
    monkeypatch.setattr(retriever.file_vector, "search", lambda *_a, **_k: [])

    documents = [
        _doc(
            "leave-1",
            "Unused annual leave carry over is allowed under the configured reset rule.",
            title="Annual Leave Policy",
            file_key="policy:leave",
            chunk_index=1,
            section="Carry Over",
        ),
        _doc(
            "leave-2",
            "Carry over limits and forfeiture are described in this section.",
            title="Annual Leave Policy",
            file_key="policy:leave",
            chunk_index=2,
            section="Carry Over",
        ),
        _doc(
            "leave-3",
            "Additional leave administration wording for the same policy file.",
            title="Annual Leave Policy",
            file_key="policy:leave",
            chunk_index=3,
            section="Administration",
        ),
        _doc(
            "attendance-1",
            "Attendance lateness and work schedules are recorded here.",
            title="Attendance Policy",
            file_key="policy:attendance",
            chunk_index=1,
            section="Lateness",
        ),
        # Same query terms but wrong tenant: must be excluded before ranking.
        _doc(
            "rogue-company",
            "Unused annual leave carry over is always unlimited.",
            title="Other Company Leave Policy",
            company_id=2,
            file_key="policy:rogue-company",
        ),
        # Same tenant but wrong private role: must also be excluded.
        _doc(
            "rogue-role",
            "Unused annual leave carry over is unlimited for a private employee.",
            title="Private Employee Note",
            role_scope="employee",
            file_key="policy:rogue-role",
        ),
    ]

    results = retriever.search(
        "Can unused annual leave carry over?",
        documents,
        company_id=1,
        role_scope="admin",
    )
    assert results
    assert all(item.document.company_id == 1 for item in results)
    assert all(item.document.role_scope in {"shared", "admin"} for item in results)
    assert results[0].document.metadata.get("file_key") == "policy:leave"
    counts = Counter(
        item.document.metadata.get("file_key")
        for item in results
        if item.document.metadata.get("file_key")
    )
    assert max(counts.values(), default=0) <= retriever.settings.max_chunks_per_file



def test_file_stage_can_find_rule_near_end_of_large_file(monkeypatch) -> None:
    retriever = HybridRetriever()
    monkeypatch.setattr(retriever.vector, "search", lambda *_a, **_k: [])
    monkeypatch.setattr(retriever.file_vector, "search", lambda *_a, **_k: [])

    documents: list[KnowledgeDocument] = []
    for file_number in range(1, 8):
        for chunk_number in range(1, 9):
            text = (
                f"General procedure for department {file_number}, part {chunk_number}."
            )
            if file_number == 6 and chunk_number == 8:
                text = (
                    "Unused vacation leave carry over is permitted under the annual "
                    "reset rule and remains subject to the configured credit limit."
                )
            documents.append(_doc(
                f"f{file_number}-c{chunk_number}",
                text,
                title=f"Policy {file_number}",
                file_key=f"policy:file:{file_number}",
                chunk_index=chunk_number,
                section="Carry Over" if file_number == 6 else "General",
            ))

    results = retriever.search(
        "Can unused vacation leave carry over?",
        documents,
        company_id=1,
        role_scope="admin",
    )
    assert results
    assert results[0].document.document_id == "f6-c8"


def test_retrieval_settings_are_tuned_for_document_aware_search() -> None:
    settings = retriever_settings = portal_ai.get_chat_assistant_settings()
    assert settings.policy_chunk_size == 260
    assert settings.policy_chunk_overlap == 48
    assert settings.company_document_chunk_size == 300
    assert settings.company_document_chunk_overlap == 56
    assert settings.file_top_k == 5
    assert settings.max_chunks_per_file == 3
    assert settings.neighbor_chunk_window == 1
    assert settings.bm25_top_k == 10
    assert settings.vector_top_k == 10
    assert retriever_settings.final_top_k == 6


def test_company_form_docx_extractor_preserves_heading_marker() -> None:
    source = (ROOT / "services" / "company_form_knowledge_service.py").read_text(
        encoding="utf-8"
    )
    assert "DOCXStructureExtractor.extract" in source
    assert 'f"## {section.heading}\\n{section.text}"' in source
    assert "reliable_heading_count == 0" in source



def test_qdrant_query_is_partitioned_to_exact_authorized_snapshot(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakePointStruct:
        def __init__(self, *, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeVectorParams:
        def __init__(self, *, size, distance):
            self.size = size
            self.distance = distance

    class FakeMatchValue:
        def __init__(self, *, value):
            self.value = value

    class FakeFieldCondition:
        def __init__(self, *, key, match):
            self.key = key
            self.match = match

    class FakeFilter:
        def __init__(self, *, must):
            self.must = must

    class FakeDistance:
        COSINE = "cosine"

    class FakeModels(ModuleType):
        PointStruct = FakePointStruct
        VectorParams = FakeVectorParams
        MatchValue = FakeMatchValue
        FieldCondition = FakeFieldCondition
        Filter = FakeFilter
        Distance = FakeDistance

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.created = False

        def collection_exists(self, collection_name):
            captured["collection_exists"] = collection_name
            return self.created

        def create_collection(self, *, collection_name, vectors_config):
            captured["created_collection"] = collection_name
            captured["vector_size"] = vectors_config.size
            self.created = True

        def upsert(self, *, collection_name, points, wait):
            captured["upsert_collection"] = collection_name
            captured["points"] = points
            captured["wait"] = wait

        def query_points(self, *, collection_name, query, query_filter, limit, with_payload, with_vectors):
            captured["query_collection"] = collection_name
            captured["query_filter"] = query_filter
            point_id = captured["points"][0].id
            return SimpleNamespace(points=[SimpleNamespace(id=point_id, score=0.9)])

    class FakeModel:
        def encode(self, values, normalize_embeddings=True):
            class Encoded(list):
                def tolist(self):
                    return list(self)
            return Encoded([[0.1, 0.2] for _ in values])

    fake_qdrant = ModuleType("qdrant_client")
    fake_qdrant.QdrantClient = FakeClient
    fake_models = FakeModels("qdrant_client.models")
    fake_qdrant.models = fake_models
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_qdrant)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)

    portal_ai.QdrantRetriever._clients.clear()
    portal_ai.QdrantRetriever._indexed_signatures.clear()
    retriever = portal_ai.QdrantRetriever()
    retriever.settings.qdrant_dir = str(tmp_path / "qdrant")
    retriever._embedding_model = FakeModel()
    documents = [
        _doc(
            "policy-1",
            "Annual leave carry over rule.",
            title="Leave Policy",
            file_key="policy:1",
        )
    ]
    results = retriever.search(
        "carry over",
        documents,
        1,
        access_partition="company:1:role:admin:user:1",
    )
    assert results and results[0].document.document_id == "policy-1"
    assert captured["created_collection"] == "hr_portal_knowledge"
    assert captured["vector_size"] == 2
    points = captured["points"]
    assert len(points) == 1
    assert points[0].payload["document_id"] == "policy-1"
    query_filter = captured["query_filter"]
    assert query_filter.must[0].key == "retrieval_scope"
    assert points[0].payload["retrieval_scope"] == query_filter.must[0].match.value
    assert captured["client_kwargs"]["force_disable_check_same_thread"] is True


def test_smart_assistant_passes_company_and_role_scope_to_retriever() -> None:
    source = (ROOT / "modules" / "smart_ai" / "portal_ai.py").read_text(
        encoding="utf-8"
    )
    assert "company_id=current_user.company_id" in source
    assert "role_scope=role_scope" in source
    assert 'key="retrieval_scope"' in source
    assert "models.MatchValue(value=retrieval_scope)" in source
    assert "user:{current_user.user_id}" in source
