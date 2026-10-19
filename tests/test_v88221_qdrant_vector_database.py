"""v8.8.221 Qdrant vector database migration regression checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_qdrant_is_the_only_chat_vector_database_dependency() -> None:
    requirements = _source("requirements.txt")
    source = _source("modules/smart_ai/portal_ai.py")
    assert "qdrant-client>=1.19.1,<2.0" in requirements
    assert "chromadb" not in requirements.lower()
    assert "posthog" not in requirements.lower()
    assert "class QdrantRetriever" in source
    assert "class ChromaRetriever" not in source


def test_qdrant_uses_local_persistent_mode_and_exact_scope_filter() -> None:
    source = _source("modules/smart_ai/portal_ai.py")
    assert "QdrantClient(" in source
    assert "path=path" in source
    assert "force_disable_check_same_thread=True" in source
    assert "models.Distance.COSINE" in source
    assert 'key="retrieval_scope"' in source
    assert "models.MatchValue(value=retrieval_scope)" in source
    assert "threading.RLock()" in source


def test_qdrant_settings_and_version_marker() -> None:
    settings = _source("config/chat_assistant_settings.py")
    app_settings = _source("config/settings.py")
    env_example = _source(".env.example")
    readme = _source("README.md")
    assert 'qdrant_dir: str = "data/smart_ai/qdrant"' in settings
    assert 'qdrant_collection: str = "hr_portal_knowledge"' in settings
    assert 'app_version: str = "0.8.8.221"' in app_settings
    assert "APP_VERSION=0.8.8.221" in env_example
    assert "SMART_AI_QDRANT_DIR=data/smart_ai/qdrant" in env_example
    assert "v8.8.221 — Qdrant Vector Database Migration" in readme


def test_old_chroma_cache_is_not_shipped_as_active_vector_data() -> None:
    assert not (ROOT / "data" / "smart_ai" / "chroma").exists()
    assert (ROOT / "data" / "smart_ai" / "qdrant").exists()
