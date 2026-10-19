"""v8.8.228 generic coordinated-fact coverage and process model-cache QA."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
from types import ModuleType
import time

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, QdrantRetriever,
    _grounded_extractive_answer,
)


def _doc(text, *, source_type="policy", file_name="fixture.docx", company=1):
    return RetrievedDocument(KnowledgeDocument(
        document_id="fixture:1", text=text, title="Business procedure",
        source_type=source_type, company_id=company, role_scope="shared",
        metadata={"filename": file_name, "section": "Travel rules"},
    ), 0.8)


def _extract(q, text):
    return _grounded_extractive_answer(
        q, [_doc(text)], max_items=6, max_chars=1800,
    )


def test_exact_user_qa_three_uses_both_linked_payer_rules():
    policy = (
        "4.1 Transportation Expenses In case the transportation and pick-up arrangement made by TSCL "
        "shall no longer be available on the arrival of the employee due to the delayed flight "
        "schedule, the concerned employee may request the airline officer to provide transportation "
        "that would bring him to the location of hotel or apartment where s/he shall be accommodated. "
        "Any incurred expenses brought about by the delayed flight should be appropriately "
        "shouldered by the airline. Thus, the employee is expected to assert this right. "
        "4.2 Hotel Accommodation If in case the employee's flight is delayed and there will be "
        "a need for an overnight stay because there are no transportation available at the time "
        "of arrival, the employee concerned is advised to request the airline officer to make "
        "the proper arrangement for a hotel accommodation charged to their airline. "
        "If there will be a delay in flight for one (1) day or more, due to the negligence "
        "of the airline, any incurred expenses (ex. food expenses, laundry services) "
        "shall be charged to the airline."
    )
    answer, meta = _extract(
        "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?", policy,
    )
    assert meta["decision"] == "accepted-compound-action-coverage"
    assert meta["covered_facets"] == ["hotel", "transportation"]
    assert "Transportation Expenses" in answer and "shouldered by the airline" in answer
    assert "hotel accommodation charged to their airline" in answer
    assert "food expenses" not in answer  # unasked exception must not displace requested cost


def test_compound_facet_in_unrelated_condition_does_not_satisfy_action():
    policy = (
        "If no transportation is available, hotel accommodation should be charged to the airline. "
        "The employee must ask the officer for directions."
    )
    answer, meta = _extract(
        "Who should shoulder transportation and hotel accommodation expenses?", policy,
    )
    assert answer == ""
    assert meta["decision"] == "compound-action-coverage-incomplete"


def test_direct_single_object_action_unchanged():
    answer, meta = _extract(
        "Who should approve the leave request?",
        "The line supervisor must approve the leave request before it can proceed."
    )
    assert "supervisor" in answer
    assert meta["decision"] == "accepted"


def test_unasked_exception_still_not_first_contact():
    answer, _ = _extract(
        "In case of an incident, who should the employee inform first?",
        "The employee should inform the direct supervisor immediately. "
        "If the direct supervisor is unavailable, contact the co-worker instead."
    )
    assert "direct supervisor immediately" in answer
    assert "co-worker" not in answer


def test_shared_embedding_model_reused_across_retrievers_and_queries(monkeypatch):
    created = []
    models = ModuleType("sentence_transformers")

    class FakeSentenceTransformer:
        def __init__(self, name):
            created.append(name)
            self.name = name
        def encode(self, values, **kwargs):
            return [[0.1, 0.2] for _ in values]

    models.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", models)
    with QdrantRetriever._embedding_load_lock:
        before = dict(QdrantRetriever._embedding_models)
        before_locks = dict(QdrantRetriever._embedding_encode_locks)
        QdrantRetriever._embedding_models.clear()
        QdrantRetriever._embedding_encode_locks.clear()
    try:
        file_retriever = QdrantRetriever(collection_suffix="_files")
        chunk_retriever = QdrantRetriever()
        assert file_retriever._model() is chunk_retriever._model()
        assert chunk_retriever._model_cache_state == "reused"
        assert QdrantRetriever()._model() is file_retriever._model()
        assert created == [str(file_retriever.settings.embedding_model)]
    finally:
        with QdrantRetriever._embedding_load_lock:
            QdrantRetriever._embedding_models.clear()
            QdrantRetriever._embedding_models.update(before)
            QdrantRetriever._embedding_encode_locks.clear()
            QdrantRetriever._embedding_encode_locks.update(before_locks)


def test_shared_embedding_initialization_thread_safe(monkeypatch):
    made = []
    make_lock = threading.Lock()
    models = ModuleType("sentence_transformers")

    class FakeModel:
        def __init__(self, name):
            with make_lock:
                made.append(name)
        def encode(self, values, **kwargs):
            return [[0.1, 0.2] for _ in values]

    models.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", models)
    with QdrantRetriever._embedding_load_lock:
        before = dict(QdrantRetriever._embedding_models)
        before_locks = dict(QdrantRetriever._embedding_encode_locks)
        QdrantRetriever._embedding_models.clear()
        QdrantRetriever._embedding_encode_locks.clear()
    try:
        def get_model(_):
            retriever = QdrantRetriever()
            return retriever._model()
        with ThreadPoolExecutor(max_workers=12) as pool:
            loaded = list(pool.map(get_model, range(30)))
        assert len({id(value) for value in loaded}) == 1
        assert len(made) == 1
    finally:
        with QdrantRetriever._embedding_load_lock:
            QdrantRetriever._embedding_models.clear()
            QdrantRetriever._embedding_models.update(before)
            QdrantRetriever._embedding_encode_locks.clear()
            QdrantRetriever._embedding_encode_locks.update(before_locks)


def test_shared_embedding_encode_serializes_concurrent_inference(monkeypatch):
    # Company/user queries are never cached or mixed. A single shared model
    # instance receives isolated encode calls, even from concurrent sessions.
    active = [0]
    max_active = [0]
    lock = threading.Lock()
    observed = []
    models = ModuleType("sentence_transformers")

    class FakeModel:
        def __init__(self, name):
            pass
        def encode(self, values, **kwargs):
            with lock:
                active[0] += 1
                max_active[0] = max(max_active[0], active[0])
            time.sleep(0.002)
            with lock:
                observed.append(values[0])
                active[0] -= 1
            return [[0.1, 0.2]]

    models.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", models)
    with QdrantRetriever._embedding_load_lock:
        before = dict(QdrantRetriever._embedding_models)
        before_locks = dict(QdrantRetriever._embedding_encode_locks)
        QdrantRetriever._embedding_models.clear()
        QdrantRetriever._embedding_encode_locks.clear()
    try:
        def encode_one(i):
            retriever = QdrantRetriever()
            model = retriever._model()
            return retriever._encode(model, [f"query:company:{i%3}:user:{i}"])
        with ThreadPoolExecutor(max_workers=10) as pool:
            vectors = list(pool.map(encode_one, range(30)))
        assert len(vectors) == len(observed) == 30
        assert max_active[0] == 1
        assert len(set(observed)) == 30
    finally:
        with QdrantRetriever._embedding_load_lock:
            QdrantRetriever._embedding_models.clear()
            QdrantRetriever._embedding_models.update(before)
            QdrantRetriever._embedding_encode_locks.clear()
            QdrantRetriever._embedding_encode_locks.update(before_locks)


def test_model_cache_does_not_cache_company_or_user_document_text():
    source = (Path(__file__).resolve().parents[1] / "modules/smart_ai/portal_ai.py").read_text(encoding="utf-8")
    assert 'self._embedding_models[name] = model' in source
    assert 'match=models.MatchValue(value=retrieval_scope)' in source
    assert 'key="retrieval_scope"' in source
    assert 'model_cache=' in source
