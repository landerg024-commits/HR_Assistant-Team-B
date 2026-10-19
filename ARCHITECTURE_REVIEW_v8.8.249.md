# AI HR Assistant — Architecture audit & bounded retrieval pilot
**Code baseline:** v8.8.248. **Candidate:** v8.8.249. **Status:** Isolated regression-tested; NOT certified by Windows Ollama/45-case runtime.

## Decision
**Adaptive Multi-Query Retrieval is technically compatible and useful for explicit compound questions. Do not enable it globally.** The highest-priority observed defect is frequently *answer assembly* after retrieval, not insufficient retrieval recall. This candidate fixes one **generic, same-chunk multi-facet proof** and includes an **opt-in**, BM25-only compound-query expansion for controlled A/B testing. It does not replace the existing two-stage hybrid retrieval, local embeddings, Qdrant, reranker, or local/cloud LLM modes.

## Current source-level request path (audited)
1. Authenticated Admin/Employee + company and role scope; deterministic HR routing remains authoritative for live records.
2. Source routing / shape validation; published/current policy knowledge, company guides, structured records collected by `PortalKnowledgeBuilder`.
3. Exact complete-policy overview pre-retrieval path for unambiguous published source; bypasses Qdrant/Ollama.
4. Hierarchical hybrid retrieval in `HybridRetriever`: shortlist authorized files; BM25 + Qdrant over authorized chunks and structured records; RRF fusion; optional cached local CrossEncoder; diversity and neighbor expansion.
5. Relevance guard and authorized evidence recovery. Competing policy sections can cause false no-match, wrong-subsection ranking, or factual fragments being selected over complete evidence.
6. Verbatim extraction for eligible question types, otherwise evidence-grounded `qwen2.5:7b` (or configured provider). Prompt generation, answer cleaning, and evidence-grounded source attribution occur before the final response.
7. 180s standard local Ollama timeout, 30s no-retry special direct-fact fallback. Changing the general timeout does not help the latter.

## Measured evidence from supplied Windows logs
- v8.8.247 full 45-case baseline: 19 fully aligned / 18 partial / 8 failed under **provisional user-QA rubric**; median elapsed 57.33s; 29 answers used Qwen; four relevance-guard rejections; one 30s fallback timeout. Not independently certified against current HR policy.
- v8.8.248 focused 6-case run: four earlier false abstentions returned answers, but several omitted mandatory facets; ADD-041 still timed out at its 30s special budget. Some successful Qwen responses took 74–176 seconds.
- Critical diagnostic in ADD-041: the SAME authorized `Training & Development` source chunk contained BOTH required attendee and duration sentences; the existing extraction chose the wrong units and emitted `missing-requested-numeric-evidence`. Merely adding queries or extending timeouts would not fix that selection error.
- Local embedding cold startup ~33–35s in earlier runs. Warm Qdrant retrieval typically much faster; Qwen generation is often the main long-tail source. Timing is hardware-dependent.

## Candidate source changes
1. `modules/smart_ai/portal_ai.py`: a *source-verbatim* coordinated-fact path activates only if the question explicitly has two independently introduced interrogatives — currently **who** and **how long**, separated by `, and`. It returns two locally related sentences only when both actor obligation and duration are present in the same authorized policy chunk, near each other, and the duration sentence mentions the user's policy subject. No synthetic QA expected answers or company rules are embedded. Otherwise, original RAG/generation flow applies.
2. `modules/smart_ai/portal_ai.py`: bounded lexical subquery planner for questions with independent interrogatives separated by `, and`. When enabled, it runs up to **two extra BM25 searches within the existing authorized search space**, fuses small secondary signals into the ranked candidates, reuses **the single existing Qdrant vector pass**, and calls **no LLM** for query rewriting. Never imports a document outside the scoped search space. It cannot rescue relevant files excluded upstream at the file-shortlist stage; this is a deliberately limited pilot.
3. `config/chat_assistant_settings.py`: new `adaptive_multi_query_enabled: bool = False`. Enable only by adding `SMART_AI_ADAPTIVE_MULTI_QUERY_ENABLED=true` to the existing local `.env` and restarting. False is the tested/default baseline. Keep `ollama_timeout_seconds=180` and short direct-fact timeout=30.
4. New source-independent synthetic tests cover complete paired facts, unrelated cross-sentence durations, other policy chunks, title conjunctions, nonpolicy sources, plan specificity, auth-scoped fusion, and disabled defaults.

## Why NOT blanket multi-query or LLM query rewriting yet?
- **Accuracy:** high recall without a per-facet evidence/provenance check can *increase* wrong-policy mixing.
- **Latency:** generating alternate queries using local `qwen2.5:7b` would consume tens of seconds even before retrieval, offsetting the performance gain. Multiple Qdrant calls on cold startup would increase cost.
- **Scope:** ordinary exact policy questions are already successful at ~0.42 seconds using complete authorized source retrieval; do not slow them down.
- **Eligibility:** e.g., a simple 'Who is eligible...?' without multiple interrogatives is currently *not* expanded. Its missing conditions should be solved through a general evidence-completeness mechanism and tests, not by guessing unmentioned qualification categories from hardcoded prompts.

## Controlled rollout and acceptance gates
- **Stage A:** Leave `SMART_AI_ADAPTIVE_MULTI_QUERY_ENABLED=false`, install candidate, run unit tests and retest ADD-041 plus easy negative controls. Verify `accepted-same-chunk-coordinated-facts` is logged and the cited chunk includes both facts, without an Ollama request.
- **Stage B:** Run the six focused questions and record accuracy/latency with MQ **off**. Then switch only `SMART_AI_ADAPTIVE_MULTI_QUERY_ENABLED=true`, restart, run the identical six cases and compare original versus added BM25 hits, policy section provenance, p50/p90 latency and full-facet score. Return to false if results worsen.
- **Stage C:** Do not publish 'overall QA improvement' without all 45-case replay on the same scoped company data. Assess correctness (not lexical overlap), relevant policy publication/effectivity, source authorization, abstention/unsupported claims, p50/p90 latency.
- **Business gates:** preserve **zero cross-company/role leakage**, no false benefit/discipline claim, no QA-answer leakage into production, unchanged database/Qdrant; target demonstrable increase over baseline 19/45 full-alignment and lower warm median latency. Set numerical target with user before release to production.

## Regression and remaining limitations
The 72 selected RAG/provider tests passed. Adding legacy `test_smart_portal_ai.py` yielded 75 pass and one old UI source-text assertion fail, identically reproducible against unchanged v8.8.248. Synthetic pilot tests verify algorithm behavior, not real Windows performance. Broader multi-part/eligibility/exception completeness and final-answer claim-level provenance still need architectural work and a controlled benchmark; this pilot is explicitly NOT a full solution to those remaining issues.
