# AI HR Assistant v8.8.249 — QA45 Contiguous Policy Chain Pilot

## Build and scope

**Cumulative, minimal patch** built directly on top of the **QA45 Partial Completeness Pilot**, which already includes the Contract Guard and Scoped Workflow pilots. One production file is replaced: `modules/smart_ai/portal_ai.py`. One new synthetic pytest file is added. There is no version bump.

**No company policy text, QA answer keys, customer documents, user data, SQLite DB, Qdrant indexes, `.env`, credentials, embedding/reranker/LLM settings, or UI changes are included.** The archived policy was only used locally for source-level replay; its bytes are not in this patch.

## Why the next QA category is incomplete

A policy may store the introductory *conditional rule* as the heading of one uploaded section, while the enumerated priority branches live in the next indexed chunk. Search may rank the introductory chunk higher and omit or down-rank the numbered steps; unrelated page/HR record text then reaches Qwen instead. The deterministic router can additionally label a general policy responsibility question as an `attendance` query, so the existing narrow policy fast path is never consulted.

## Generic corrections

1. `_contiguous_conditional_list_answer`: Recognizes an `If ... who` conditional responsibility question and requires an intact numbered rule sequence from two **consecutive** authorized policy chunks with matching company, role, source file key, policy/document IDs, and version. The condition can be in the current chunk's body or in either chunk's structured heading. Multiple distinct equally supported policies are ambiguous and rejected. It requires consecutive `(1), (2), ...` ordinals, a tie/conditional later branch and an explicit next-section boundary; returns the bounded **source verbatim**, not a model guess.
2. `HybridRetriever._expand_neighbors`: When a relevant policy seed is retrieved, the next chunk can be included **only after the complete conditional chain has already been proven**. No extra BM25, Qdrant, embedding, or Ollama calls. This runs before the ordinary unrelated fallback-candidate fill and respects existing `final_top_k` and neighbor window.
3. `portal_ai` answer routing: If the deterministic router mislabeled a complete **policy** priority rule as `attendance`, a narrowly verified source chain may be returned directly after the normal company/HR scope check. It never bypasses the company/role guard for records and never accepts incomplete policy evidence. Trace marker: `VERIFIED CONDITIONAL POLICY CHAIN`, `decision=accepted-contiguous-conditional-list`, `ollama_skipped=yes`.

## Local validation

- 14 new synthetic tests for cross-chunk completeness, heading-only preambles, merged heading labels, same file/version/tenant/role matching, missing clauses, conflicting sources, neighbor recovery and unrelated-question controls.
- 98 existing QA/RAG pilot tests preserved.
- **112/112 focused tests passed** in the local container.
- Archived source-level read-only replay recovered all numbered condition branches for the class of rule tested by **ADD-012**. The original company source and expected QA answer were **not** copied into the patch.
- This **does not yet certify Windows ADD-012 PASS** or improvement for any other remaining PARTIAL cases. The latest confirmed full baseline remains provisional until an actual 45-case Windows rerun.

## Windows installation (VS Code PowerShell)

Stop the Streamlit app. In `C:\User_dev\HR_Assistant` with `.venv` active:

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py' 'modules\smart_ai\portal_ai.py.before_contiguous_policy_chain_pilot' -Force
$zip = "$env:USERPROFILE\Downloads\AI_HR_Assistant_v8.8.249_QA45_Contiguous_Policy_Chain_Pilot.zip"
Test-Path $zip
```

If the result is `False`, save/download the ZIP in your **actual** Downloads folder or use its real path. **Do not run Expand-Archive while it is False.** When `True`:

```powershell
Expand-Archive -LiteralPath $zip -DestinationPath 'C:\User_dev\HR_Assistant' -Force
Test-Path 'tests\test_qa45_contiguous_conditional_policy_chunks.py'
Select-String -Path 'modules\smart_ai\portal_ai.py' -Pattern 'accepted-contiguous-conditional-list' -SimpleMatch
```

## Focused tests

```powershell
python -m pytest -q tests/test_qa45_contiguous_conditional_policy_chunks.py tests/test_qa45_bounded_linked_clauses.py tests/test_qa45_scoped_workflow_candidate.py tests/test_qa45_question_contract_guard.py tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py
```

**Expected: 112 passed**, plus possibly the previously known `asyncio_default_fixture_loop_scope` pytest configuration warning on Windows.

## Targeted QA (run only after pytest)

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-012,ADD-007,ADD-011,ADD-039,ADD-015,ADD-016,ADD-017,ADD-019,ADD-020,ADD-032,ADD-041,ADD-045
```

Target: **ADD-012** must preserve all tiered responsibility branches without unrelated office rules or timeouts. The other 11 cases are controls, with ADD-007/011/039 for prior partial-completeness gains and ADD-045 for the scoped-workflow fix. Inspect both `QA_Terminal_*.txt` and `QA_Session_*.log`; do not treat `REVIEW_REQUIRED` as automatic PASS. A full 45-case rerun should be done only after targeted checks pass.

## Rollback

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py.before_contiguous_policy_chain_pilot' 'modules\smart_ai\portal_ai.py' -Force
```
