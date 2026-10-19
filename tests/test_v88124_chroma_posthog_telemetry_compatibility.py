"""Legacy telemetry checkpoint plus current Qdrant migration regression checks."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_chroma_runtime_dependency_was_replaced_by_qdrant() -> None:
    smart_ai = _source("modules/smart_ai/portal_ai.py")
    requirements = _source("requirements.txt")

    assert "import chromadb" not in smart_ai
    assert "ChromaSettings" not in smart_ai
    assert "chromadb>=" not in requirements
    assert "posthog>=" not in requirements
    assert "from qdrant_client import QdrantClient" in smart_ai
    assert "qdrant-client>=1.19.1,<2.0" in requirements


def test_qdrant_migration_keeps_vector_and_bm25_retrieval() -> None:
    smart_ai = _source("modules/smart_ai/portal_ai.py")

    assert "self.bm25.search" in smart_ai
    assert "self.vector.search" in smart_ai
    assert "client.query_points" in smart_ai
    assert "self.settings.enabled" in smart_ai


def test_v88124_checkpoint_is_documented() -> None:
    readme = _source("README.md")

    assert "v8.8.221 — Qdrant Vector Database Migration" in readme
