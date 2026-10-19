"""v8.8.231 regression: real DOCX layout, timeout messaging, local HF cache."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, QdrantRetriever,
    _grounded_extractive_answer,
)

QUESTION = "Who should shoulder transportation and hotel accommodation expenses caused by flight delays?"


def source(text, *, file_key="policy:5:document:2", company_id=1, rank=.9):
    return RetrievedDocument(KnowledgeDocument(
        document_id=f"chunk:{len(text)}:{rank}", text=text, title="Business Visa",
        source_type="policy", company_id=company_id, role_scope="shared",
        metadata={"title":"Business Visa", "version":"1.0", "file_key":file_key,
                  "filename":"Business VISA.docx", "section":"Travel Procedures"}
    ), rank)


def extract(docs):
    return _grounded_extractive_answer(QUESTION, docs, max_items=6, max_chars=1800)


def test_real_policy_split_lines_join_transport_and_hotel_with_payer():
    # Real DOCX extraction: numbered section heading and instruction occur on
    # separate lines, not within one punctuation-delimited sentence.
    transport = source(
        "4.1 Transportation Expenses\n\n"
        "In case the transportation and pick-up arrangement made by TSCL shall no longer be "
        "available on the arrival of the employee due to the delayed flight schedule, "
        "the concerned employee may request the airline officer to provide transportation "
        "that would bring him to the location of hotel or apartment where s/he shall be accommodated. "
        "Any incurred expenses brought about by the delayed flight should be appropriately "
        "shouldered by the airline. Thus, the employee is expected to assert this right.\n\n"
        "4.2 Hotel Accommodation"
    )
    hotel = source(
        "4.2 Hotel Accommodation\n\n"
        "If in case the employee's flight is delayed and there will be a need for an "
        "overnight stay because there are no transportation available at the time of arrival, "
        "the employee concerned is advised to request the airline officer to make "
        "the proper arrangement for a hotel accommodation charged to their airline."
    )
    answer, meta = extract([transport, hotel])
    assert meta["decision"] == "accepted-compound-action-coverage", meta
    assert meta["covered_facets"] == ["hotel", "transportation"]
    assert "shouldered by the airline" in answer
    assert "hotel accommodation charged to their airline" in answer
    assert "4.1 Transportation" not in answer or "airline" in answer


def test_unavailable_transport_does_not_get_credited_as_paid_transport():
    hotel = source(
        "4.2 Hotel Accommodation\n\n"
        "If no transportation is available after a delayed flight, the employee shall request "
        "hotel accommodation charged to the airline."
    )
    answer, meta = extract([hotel])
    assert answer == ""
    assert meta["decision"] == "compound-action-coverage-incomplete"


def test_same_file_different_company_cannot_merge():
    transport = source(
        "4.1 Transportation Expenses\n\nThe employee can request transport from an airline officer. "
        "Any incurred expenses brought about by the delayed flight shall be paid by the airline.",
        company_id=1,
    )
    hotel = source("Hotel accommodation expenses are paid by the airline.", company_id=2)
    answer, meta = extract([transport, hotel])
    assert answer == "" and meta["decision"] == "compound-action-coverage-incomplete"


def test_first_contact_and_complete_recipient_unchanged():
    q = "Who is responsible for notifying the North Admin Manager, General Manager, and Partner Office?"
    d = source("The supervisor will inform the North Admin Manager, General Manager and Partner Office. "
               "The supervisor will coordinate with the North Admin Manager and Partner Office.")
    a, m = _grounded_extractive_answer(q, [d], max_items=6, max_chars=1800)
    assert m["decision"] == "accepted-explicit-recipient-coverage"
    assert "General Manager" in a
    e = source("6.1 The employee will inform the immediate superior. "
               "If unavailable the employee may contact a co-worker.")
    a, _ = _grounded_extractive_answer("Who should the employee inform first in an emergency?", [e], max_items=6, max_chars=1800)
    assert "immediate superior" in a and "co-worker" not in a


def test_local_cached_model_snapshot_preferred_no_online_resolution(tmp_path, monkeypatch):
    path = tmp_path / "hf-snapshot"
    path.mkdir()
    (path / "config.json").write_text("{}")
    (path / "tokenizer.json").write_text("{}")
    hf = ModuleType("huggingface_hub")
    called = []
    def snapshot_download(*, repo_id, local_files_only):
        called.append((repo_id, local_files_only))
        return str(path)
    hf.snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf)
    models = ModuleType("sentence_transformers")
    class DummyST:
        def __init__(self, path_or_id):
            called.append(path_or_id)
        def encode(self, values, **kwargs):
            return [[1,0] for _ in values]
    models.SentenceTransformer = DummyST
    monkeypatch.setitem(sys.modules, "sentence_transformers", models)
    # fake model name config can be overridden safely on the instance
    retriever = QdrantRetriever()
    monkeypatch.setattr(retriever.settings, "embedding_model", "example/local-embed")
    with QdrantRetriever._embedding_load_lock:
        before = dict(QdrantRetriever._embedding_models)
        before_locks = dict(QdrantRetriever._embedding_encode_locks)
        QdrantRetriever._embedding_models.clear()
        QdrantRetriever._embedding_encode_locks.clear()
    try:
        retriever._model()
        assert called == [("example/local-embed", True), str(path)]
        assert retriever._model_cache_state == "loaded-local-cache"
        again = QdrantRetriever()
        assert again._model() is retriever._model()
        assert again._model_cache_state in {"reused", "instance"}
    finally:
        with QdrantRetriever._embedding_load_lock:
            QdrantRetriever._embedding_models.clear()
            QdrantRetriever._embedding_models.update(before)
            QdrantRetriever._embedding_encode_locks.clear()
            QdrantRetriever._embedding_encode_locks.update(before_locks)


def test_missing_local_snapshot_falls_back_to_original_model(monkeypatch):
    hf = ModuleType("huggingface_hub")
    def missing(**kwargs):
        raise OSError("no cached snapshot")
    hf.snapshot_download = missing
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf)
    m = ModuleType("sentence_transformers")
    constructed = []
    class FakeST:
        def __init__(self, name):
            constructed.append(name)
    m.SentenceTransformer = FakeST
    monkeypatch.setitem(sys.modules,"sentence_transformers",m)
    retriever = QdrantRetriever()
    monkeypatch.setattr(retriever.settings,"embedding_model","example/uncached-model")
    with QdrantRetriever._embedding_load_lock:
        before = dict(QdrantRetriever._embedding_models)
        before_locks = dict(QdrantRetriever._embedding_encode_locks)
        QdrantRetriever._embedding_models.clear()
        QdrantRetriever._embedding_encode_locks.clear()
    try:
        retriever._model()
        assert constructed == ["example/uncached-model"]
        assert retriever._model_cache_state == "loaded"
    finally:
        with QdrantRetriever._embedding_load_lock:
            QdrantRetriever._embedding_models.clear()
            QdrantRetriever._embedding_models.update(before)
            QdrantRetriever._embedding_encode_locks.clear()
            QdrantRetriever._embedding_encode_locks.update(before_locks)


def test_timeout_warning_text_no_false_retry_claim():
    from services.runtime_connection_service import (
        RuntimeServiceTimeoutError, classify_runtime_connection_issue,
    )
    exc = RuntimeServiceTimeoutError(service="Ollama", operation="generate", timeout_seconds=30)
    issue = classify_runtime_connection_issue(exc, service_hint="ollama")
    assert issue.code == "ollama_response_timeout"
    assert "was attempted" not in issue.message
    assert "do not retry" in issue.message
