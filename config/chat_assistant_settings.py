"""Dedicated configuration for the local Chat Assistant.

Purpose:
- Keep Chat Assistant model, generation, retrieval, and quality tuning values
  out of the main application settings module.
- Make AI-specific configuration easy to find and adjust in one place.
- Preserve environment overrides through SMART_AI_* variables in `.env`.

These settings affect only the Admin/Employee Chat Assistant. They do not
change authentication, HR workflows, reports, notifications, or other portal
modules.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatAssistantSettings(BaseSettings):
    """Environment-driven settings used only by the Chat Assistant."""

    # Master switch.
    enabled: bool = True

    # v8.8.242: one .env switch; local is the safe, backwards-compatible default.
    # local: Ollama only; groq: Groq only; hybrid: Groq primary with Ollama fallback.
    llm_mode: Literal["local", "groq", "hybrid"] = "local"
    groq_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("SMART_AI_GROQ_API_KEY", "GROQ_API_KEY"),
        repr=False,
    )
    groq_model: str = "qwen/qwen3.8-27b"
    groq_timeout_seconds: float = 25.0

    # Ollama connection and models.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    quality_ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: int = 180
    ollama_health_timeout_seconds: float = 5.0
    ollama_retry_timeout_seconds: int = 90
    ollama_timeout_retry_enabled: bool = True
    # Grounded simple facts failing safe extractive coverage: one short attempt
    # (no automatic 180s+90s retry). Other LLM workflows keep prior budgets.
    grounded_direct_fact_ollama_timeout_seconds: int = 30
    # Local-only contradiction correction: at most one short evidence-grounded retry.
    binary_repair_enabled: bool = True
    binary_repair_timeout_seconds: float = 45.0

    # Terminal-only retrieval / answer diagnostics. With request logging enabled,
    # stderr stays compact while the full forensic trace is preserved per request
    # under ``terminal_debug_log_dir``. Nothing is rendered in the Streamlit UI.
    terminal_debug_enabled: bool = True
    terminal_debug_top_k: int = 10
    terminal_debug_excerpt_chars: int = 520
    terminal_debug_answer_chars: int = 1800
    terminal_debug_candidate_answer_chars: int = 760
    terminal_debug_log_enabled: bool = True
    terminal_debug_log_dir: str = "logs/chat_assistant"
    # A new chat/QA conversation produces one consolidated, scoped log file.
    # Set false for the legacy per-question files. Disable forensic logging in
    # production environments where raw Q&A/evidence must not be retained.
    terminal_debug_session_logging_enabled: bool = True

    # Grounded generation controls.
    temperature: float = 0.0
    context_window: int = 4096
    standard_max_tokens: int = 320
    quality_max_tokens: int = 480
    keep_alive: str = "30m"
    history_messages: int = 4

    # Decide when the LLM enhancement/quality path is useful.
    min_question_tokens: int = 18
    quality_min_question_tokens: int = 14
    quality_min_retrieved_documents: int = 3

    # Knowledge chunking and document-aware hybrid retrieval.
    # ``chunk_size`` remains as a compatibility fallback for older integrations;
    # policy/company-document content uses the source-specific settings below.
    chunk_size: int = 256
    chunk_overlap: int = 40
    policy_chunk_size: int = 260
    policy_chunk_overlap: int = 48
    company_document_chunk_size: int = 300
    company_document_chunk_overlap: int = 56
    # v8.8.222 adaptive chunking keeps intact semantic sections whenever they
    # fit inside the hard maximum, then uses these soft targets only when a
    # section actually needs splitting.  The legacy size/overlap fields above
    # remain as compatibility fallbacks for older integrations/tests.
    adaptive_chunking_enabled: bool = True
    policy_chunk_min_words: int = 120
    policy_chunk_target_words: int = 220
    policy_chunk_max_words: int = 300
    company_document_chunk_min_words: int = 160
    company_document_chunk_target_words: int = 280
    company_document_chunk_max_words: int = 360
    adaptive_overlap_ratio: float = 0.14
    adaptive_overlap_min_words: int = 16
    adaptive_overlap_max_words: int = 44
    chunk_diagnostics_enabled: bool = True
    chunk_diagnostics_full_text: bool = False
    file_top_k: int = 5
    file_candidate_k: int = 10
    max_chunks_per_file: int = 3
    neighbor_chunk_window: int = 1
    # Opt-in bounded lexical multi-query for explicit two-part questions.
    # Only extra BM25 lookups within the already authorized search space;
    # no extra Qdrant/vector call and no LLM query-generation call.
    # Leave off until A/B retrieval + answer-quality review is complete.
    adaptive_multi_query_enabled: bool = False
    bm25_top_k: int = 10
    vector_top_k: int = 10
    final_top_k: int = 6
    evidence_neighbor_reserve: int = 1
    evidence_file_representatives: int = 2
    evidence_min_score_ratio: float = 0.80
    evidence_excerpt_chars: int = 900
    # Deterministic pre-generation gate for document-centric RAG requests.
    # It rejects weak topic matches before Qwen is allowed to synthesize an
    # answer; no additional LLM/judge call is introduced.
    evidence_gate_enabled: bool = True
    evidence_gate_min_answer_cue: float = 0.70
    qdrant_dir: str = "data/smart_ai/qdrant"
    qdrant_collection: str = "hr_portal_knowledge"
    embedding_model: str = "intfloat/multilingual-e5-small"
    # Prefer an already cached local model snapshot; online fallback remains
    # available for a genuinely missing model (first run / model switch).
    embedding_prefer_local_cache: bool = True
    embedding_batch_size: int = 64
    qdrant_upsert_batch_size: int = 128

    # High-confidence policy/document questions can be answered extractively
    # from the accepted company evidence without paying the latency of a local
    # 7B generation pass.  This path never invents or paraphrases business
    # rules; it only selects complete source sentences/rows.  Ambiguous,
    # conversational, YES/NO, and synthesis-heavy questions still use Qwen.
    grounded_extractive_fast_path_enabled: bool = True
    grounded_extractive_min_anchor_coverage: float = 0.60
    grounded_extractive_max_items: int = 6
    grounded_extractive_max_chars: int = 1800

    # Candidate selection / ambiguity tuning.
    reciprocal_rank_constant: int = 60
    candidate_multiplier: int = 3
    candidate_minimum: int = 8
    ambiguity_min_candidates: int = 4
    ambiguity_score_gap: float = 0.006
    complex_query_min_tokens: int = 12

    # Optional CrossEncoder reranker.
    # Conditional, cache-only reranking. If no local model is present, the
    # current BM25/Qdrant evidence path remains unchanged and no download runs.
    reranker_enabled: bool = True
    reranker_local_only: bool = True
    reranker_competing_gap: float = 0.003
    reranker_model: str = "BAAI/bge-reranker-base"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SMART_AI_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_chat_assistant_settings() -> ChatAssistantSettings:
    """Return one cached Chat Assistant settings object."""

    return ChatAssistantSettings()


class ChatAssistantSettingsCompatibilityMixin:
    """Legacy SMART_AI attribute bridge for the main Settings object.

    New Chat Assistant code should use `get_chat_assistant_settings()`
    directly. These properties preserve older integrations without keeping AI
    configuration fields inside `config/settings.py`.
    """

    @property
    def smart_ai_enabled(self) -> bool:
        return get_chat_assistant_settings().enabled

    @property
    def smart_ai_ollama_base_url(self) -> str:
        return get_chat_assistant_settings().ollama_base_url

    @property
    def smart_ai_ollama_model(self) -> str:
        return get_chat_assistant_settings().ollama_model

    @property
    def smart_ai_quality_ollama_model(self) -> str:
        return get_chat_assistant_settings().quality_ollama_model

    @property
    def smart_ai_ollama_timeout_seconds(self) -> int:
        return get_chat_assistant_settings().ollama_timeout_seconds

    @property
    def smart_ai_ollama_health_timeout_seconds(self) -> float:
        return get_chat_assistant_settings().ollama_health_timeout_seconds

    @property
    def smart_ai_ollama_retry_timeout_seconds(self) -> int:
        return get_chat_assistant_settings().ollama_retry_timeout_seconds

    @property
    def smart_ai_terminal_debug_enabled(self) -> bool:
        return get_chat_assistant_settings().terminal_debug_enabled

    @property
    def smart_ai_chunk_size(self) -> int:
        return get_chat_assistant_settings().chunk_size

    @property
    def smart_ai_chunk_overlap(self) -> int:
        return get_chat_assistant_settings().chunk_overlap

    @property
    def smart_ai_policy_chunk_size(self) -> int:
        return get_chat_assistant_settings().policy_chunk_size

    @property
    def smart_ai_policy_chunk_overlap(self) -> int:
        return get_chat_assistant_settings().policy_chunk_overlap

    @property
    def smart_ai_company_document_chunk_size(self) -> int:
        return get_chat_assistant_settings().company_document_chunk_size

    @property
    def smart_ai_company_document_chunk_overlap(self) -> int:
        return get_chat_assistant_settings().company_document_chunk_overlap

    @property
    def smart_ai_adaptive_chunking_enabled(self) -> bool:
        return get_chat_assistant_settings().adaptive_chunking_enabled

    @property
    def smart_ai_file_top_k(self) -> int:
        return get_chat_assistant_settings().file_top_k

    @property
    def smart_ai_bm25_top_k(self) -> int:
        return get_chat_assistant_settings().bm25_top_k

    @property
    def smart_ai_vector_top_k(self) -> int:
        return get_chat_assistant_settings().vector_top_k

    @property
    def smart_ai_final_top_k(self) -> int:
        return get_chat_assistant_settings().final_top_k

    @property
    def smart_ai_qdrant_dir(self) -> str:
        return get_chat_assistant_settings().qdrant_dir

    @property
    def smart_ai_qdrant_collection(self) -> str:
        return get_chat_assistant_settings().qdrant_collection

    @property
    def smart_ai_embedding_model(self) -> str:
        return get_chat_assistant_settings().embedding_model

    @property
    def smart_ai_reranker_enabled(self) -> bool:
        return get_chat_assistant_settings().reranker_enabled

    @property
    def smart_ai_reranker_model(self) -> str:
        return get_chat_assistant_settings().reranker_model
