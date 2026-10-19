# AI HR Assistant v8.8.249 — QA45 Partial-Answer Completeness Pilot

## Scope and base

Patch only, **apply after** the existing v8.8.249 Scoped Workflow Pilot. The only runtime file changed is `modules/smart_ai/portal_ai.py`. One new regression test is included. No version bump, DB migration, `.env` edits, secrets, HR data, Qdrant files, or company policies.

The changes are source-structure-aware and **question-pattern-based**, not hard-coded production answers or a lookup of QA questions. No evaluation reference, real policy paragraph, or test answer key is included in the production code or patch ZIP.

## Shared completeness problems addressed

1. **Paired actor and evaluation:** Questions asking *who is required to attend/undergo a named subject and how participants are evaluated*. Accept both contiguous `(a)/(b)` clauses from one already authorized policy chunk only when the named subject is proven in the actor clause. Do not import another course's evaluation.
2. **When + local exception:** Preserve adjacent timing and `unless` exception from the same original policy section. Reject section-crossing or unrelated exceptions.
3. **Named policy explanation with example:** Return a bounded `Article … Section 1` mechanism, including an actual worked example, only when the subject title matches and the next `Section 2`/article boundary is present. Do not truncate.
4. **Conditional numbered priority:** Accept a complete consecutive `(1), (2), …` rule with its preceding conditional preamble **when all branches are within one retrieved chunk**. This is fail-closed if the original chunk is split and is not yet claimed to fix ADD-012 in the live QA.

## Validation, 2026-10-16

- **98/98 relevant tests passed** (`15` new synthetic tests + `83` existing baseline controls).
- Source-level replay of the October 15 QA trace text showed complete source candidates for **ADD-007, ADD-011, ADD-039**, not an actual Windows runtime certification. Synthetic tests cover cross-subsection contamination, adjacent but unrelated policies, incomplete numbered lists, missing boundaries, unauthorized record sources, competing sources, and answer size limits.
- A full project test discovery attempt hit pre-existing environment blockers: the container lacks `streamlit` for UI imports, and an unrelated legacy test tries to import `_explicit_exception_yes_no`. The relevant AI/RAG test selection still passed.

## Installation — Windows PowerShell

1. Stop Streamlit. Start inside `C:\User_dev\HR_Assistant` with `.venv` activated.
2. Confirm the currently installed Scoped Workflow Pilot: `Select-String -Path 'modules\smart_ai\portal_ai.py' -Pattern 'accepted-scoped-numbered-workflow' -SimpleMatch`.
3. Backup your current code: `Copy-Item 'modules\smart_ai\portal_ai.py' 'modules\smart_ai\portal_ai.py.before_partial_completeness_pilot' -Force`.
4. Download this ZIP and find its actual path (usually Downloads). Then run: `Expand-Archive -LiteralPath '<actual full zip path>' -DestinationPath 'C:\User_dev\HR_Assistant' -Force`. Never expand without verifying the path exists.
5. Confirm: `Select-String -Path 'modules\smart_ai\portal_ai.py' -Pattern 'accepted-bounded-linked-clauses' -SimpleMatch`.

Regression command:

```powershell
python -m pytest -q tests/test_qa45_bounded_linked_clauses.py tests/test_qa45_scoped_workflow_candidate.py tests/test_qa45_question_contract_guard.py tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py
```

Expected (tested here): **98 passed** (plus your existing local pytest config warning).

Targeted actual Windows QA:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-007,ADD-011,ADD-039,ADD-015,ADD-016,ADD-017,ADD-019,ADD-020,ADD-032,ADD-041,ADD-045
```

**Success conditions:** ADD-007 includes 15-minute/no-grace rule, time-out adjustment and worked example; ADD-011 includes the main-door closing exception; ADD-039 contains engineering personnel and the correct technical-training evaluation (not the non-technical participant-feedback procedure). All eight control cases remain correct. The trace's actual `decision=accepted-bounded-linked-clauses` is helpful but a complete final answer is essential.

Do not infer improvements to the remaining 17 partial cases from these targeted tests. ADD-012 and other cross-chunk/multi-document requests need separate evidence-coverage validation. These patterns alone do not optimize the E5 model's cold start or Qwen latency.

Rollback if any regression:

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py.before_partial_completeness_pilot' 'modules\smart_ai\portal_ai.py' -Force
```
