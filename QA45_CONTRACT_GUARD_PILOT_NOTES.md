# AI HR Assistant v8.8.249 — QA45 Question–Answer Contract Guard (Evaluation Pilot)

**Base**: Windows clean v8.8.249 **with the Consolidated Quality Pilot already applied** (i.e., current project after the 55-passing-tests step). This is **not** a version bump, a new full distribution, or a replacement for the previous cleanup. Do **not** install it on a different version without reviewing compatibility.

## Root cause from the 45-case QA and classification

The answer-selection path accepted some *related* policy snippets even though they did not establish the asked conditional premise (case family: conditional yes/no), the actual awarding event (when-and-where), or both independent payment dates (parallel temporal targets). The problem was *not* that these evidence topics were absent from the retrieval log. The file selection and keyword relevance checks were too permissive to be a final answer validator. This patch does not encode the expected QA answers.

## Changes (only `modules/smart_ai/portal_ai.py`)

- Added an **explicit question–answer contract** for three general grammatical question shapes:
  - Conditional yes/no scenarios (`If ..., can/may/does ...?`): a positive extractive answer requires direct evidence of both the membership rule and the premise in the **same authorized policy chunk**. A negative/unsupported premise does **not** automatically produce Yes; it defers to grounded synthesis.
  - Joint event time/place (`When and where ...?`): a fast answer needs an explicit event/action and time/place clause in a policy document named by the question, not merely the timing of eligibility. Related additional acknowledgements may be included only from the same chunk.
  - Parallel deadlines (`When is X paid, and when is Y paid?`): requires a distinct topic-specific paid/deadline/date clause for **each** subject, from the **same authorized originating document** (different chunks are allowed).
- If the contract cannot be proven, the fast extraction is **rejected** and the existing authorized grounded synthesis path handles the request. The trace shows `explicit-question-contract-unproven` in `EXTRACTIVE VALIDATION TIMING`.
- Added basic grammatical singular/plural matching for identifying named document titles. It does not rewrite or fabricate policy content.

**Unchanged:** Qdrant, BM25/vector/reranking, embeddings, Ollama/Groq/model selection, request timeouts, adaptive multi-query default (OFF), HR records, permission boundaries, Streamlit UI, database, `.env`, and existing knowledge. No remote access or external LLM call was added by this patch.

## Testing and limitations

- **16 synthetic new contract tests passed** including false-premise rejection, wrong-source rejection, same-source temporal pairing, unrelated-event guards, and company-isolation cases.
- **71 focused tests passed** including all previously validated v8.8.249 pilot suites.
- **202 passed + 6 historical test failures** in a wider selection. All six are **identical pre-existing failures** reproduced on the unchanged previous pilot (**186 passed + the same 6 failed**): five stale exact-version expectations and one stale source-code-text assertion.
- This pilot has **not** been executed against the user's actual Windows company database/policy environment. The previous 45-case run was **21 PASS, 20 PARTIAL, 4 FAIL**, provisional. Expected outcomes are hypotheses, not certified until actual retest.
- **No claim of fixing local Qwen timeouts** or the broader ADD-045 workflow issue. Some previously wrong fast paths may fall back to slower authorized LLM generation if the precise evidence is absent.

## Apply (Windows PowerShell; stop Streamlit first)

From `C:\User_dev\HR_Assistant` (project root):

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py' 'modules\smart_ai\portal_ai.py.before_qa45_contract_guard' -Force
Copy-Item "$env:USERPROFILE\Downloads\AI_HR_Assistant_v8.8.249_QA45_Contract_Guard_Pilot.zip" '.'
Expand-Archive -Path '.\AI_HR_Assistant_v8.8.249_QA45_Contract_Guard_Pilot.zip' -DestinationPath '.' -Force
python -m pytest -q tests/test_qa45_question_contract_guard.py tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py
```

Expected locally: **71 passed** (your installed packages may report the same pre-existing pytest config warning).

Controlled runtime check, with `.env`, role, source, and model unchanged:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-017,ADD-020,ADD-032,ADD-015,ADD-016,ADD-019,ADD-041
```

Review not only PASS/PARTIAL/FAIL but also `EXTRACTIVE VALIDATION TIMING`, resulting file citation, `OLLAMA REQUEST`, latency, and any fallback. **Stop and restore** if prior passing cases regress:

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py.before_qa45_contract_guard' 'modules\smart_ai\portal_ai.py' -Force
```

If focused regression is acceptable, perform an unchanged-settings full 45-case benchmark before deciding whether to keep the pilot. Do not copy reference QA expected answers into production policy data or use this evaluation JSON as RAG knowledge.
