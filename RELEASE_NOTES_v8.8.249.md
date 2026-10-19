# v8.8.249 — Architecture pilot, not blanket multi-query

**Base:** v8.8.248 source. **Scope:** retrieval and evidence assembly, plus tests/docs.

- Add strict same-authorized-chunk, verbatim actor + duration evidence assembly for two-part questions. Do not call Ollama if both facts are independently proven; leave unrelated combinations to original RAG.
- Introduce experimental adaptive BM25-only multi-query for questions explicitly combining two interrogatives. It is **OFF by default** and reuses the current authorized file shortlist; no extra vector query, extra LLM, changed HR rule, or index rebuild.
- Add `SMART_AI_ADAPTIVE_MULTI_QUERY_ENABLED=false` to `.env.example`. The existing `.env` file is not included or overwritten.
- Default local Ollama 180-second timeout and short direct-fact 30-second budget unchanged.
- Version bumped to `0.8.8.249`.

**Selected verification:** 72 RAG/provider tests pass. Additional legacy UI string test still fails on untouched v8.8.248, as before. Pilot algorithm cases use synthetic policy text; Windows-hosted Qwen and 45-case benchmark **not tested in this environment**.

**Safe installation:** Stop Streamlit; back up project; apply Patch Only on top of v8.8.248; preserve `.env`, SQLite and Qdrant directories; run targeted tests; start with MQ flag `false`. See `ARCHITECTURE_REVIEW_v8.8.249.md` for the opt-in A/B protocol. Do not interpret an earlier QA expected answer as authoritative live policy without checking publication/effectivity.
