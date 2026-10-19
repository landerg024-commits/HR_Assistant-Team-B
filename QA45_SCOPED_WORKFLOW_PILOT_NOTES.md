# AI HR Assistant v8.8.249 — QA45 Scoped Workflow & Bounded Fallback Pilot

**Install base:** Current Windows v8.8.249 project **after** Consolidated Quality Pilot and QA45 Contract Guard Pilot. This patch contains **only three files**, is not a new version/full-project bundle, and does not create or modify HR data.

## QA classification addressed

- **Primary:** Procedure / Workflow — complex, ordered, multi-role responsibility chains.
- **Secondary:** Multi-facet completeness, named subsection grounding, multi-stage approvals, latency/timeout.
- **Observed regression family:** Retrieval finds the right document but the answer path either picks a neighboring procedure (e.g. non-technical vs technical) or sends an already-present policy procedure to a long LLM generation/retry.

## Generalized change

Only `modules/smart_ai/portal_ai.py` changes:

1. Classify passive, explicitly multi-action questions (`How are [subject] organized and approved?`, `How are [subject] reviewed and processed?`) as **procedure** rather than `standard`.
2. When evidence contains a **named lettered subsection** followed by a **contiguous numbered procedure**, extract **all steps in their original order** from **one already authorized policy chunk**. Require exact named-subject overlap including negative/non- qualifiers, evidence for **every requested action**, complete numbering, and no ongoing unverified chunk continuation. Never combine neighboring subsections, separate original documents, or other companies. Never silently truncate mandatory steps.
3. If this strict procedure proof is **not** available, deny the fast shortcut; attempt grounded synthesis using the **existing bounded direct-fact timeout setting** (by default around 30 seconds, capped by code at 60), the compact prompt, and **no local retry**. The global/model timeout settings are unchanged. On failure the assistant abstains; it does not present generic navigation or an unrelated policy as proof.

This is **not** an expected-answer map; there are no production QA IDs, actual company award/training answers, seeded HR records, or QA reference CSVs in this patch. Only syntactic workflow patterns and generic structural checks.

## Validation

- **12/12 new synthetic workflow tests passed**, including wrong subsection, missing action, interrupted numbering, truncated chunks, mixed-source/company, and unsupported source type.
- **83/83 focused regression tests passed** (new tests plus preceding pilots and v8.8.249 regression controls).
- **262 passed, 15 historical failures** in a broader local selection. Exact same **15 failures** reproduce on the unmodified prior candidate (250 passed, 15 failed). These include stale version assertions, missing QA references in the data-safe distribution, and one historical UI test; not caused by this change. A separate legacy fidelity test cannot import an old removed internal helper on either baseline or candidate, so it was excluded from the comparable broad run.
- Source-level replay using the user's previously archived policy file (internal inspection only; **not** shipped) correctly extracted all three numbered in-house technical training steps, including organizer, syllabus/schedule and approval, and evaluation/reporting, without adjacent non-technical steps.
- **Not yet tested on the user's Windows runtime**, real vector retrieval, or actual Ollama performance. Do not claim that the end-to-end ADD-045 failure is solved until the user's QA logs confirm it.

## Install in VS Code PowerShell (after downloading ZIP)

Stop Streamlit, work from `C:\User_dev\HR_Assistant`:

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py' 'modules\smart_ai\portal_ai.py.before_workflow_scope_pilot' -Force
Copy-Item "$env:USERPROFILE\Downloads\AI_HR_Assistant_v8.8.249_QA45_Scoped_Workflow_Pilot.zip" '.'
Expand-Archive -Path '.\AI_HR_Assistant_v8.8.249_QA45_Scoped_Workflow_Pilot.zip' -DestinationPath '.' -Force
python -m pytest -q tests/test_qa45_scoped_workflow_candidate.py tests/test_qa45_question_contract_guard.py tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py
```

Expected in the local development snapshot: **83 passed**. The local Python/package environment may differ from Windows.

## Focused runtime QA

Keep `.env`, LLM provider, adaptive multi-query (off), uploaded policies, permissions, and runtime environment the same as the previous QA. Test the target and prior passing controls:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-045,ADD-041,ADD-017,ADD-020,ADD-032,ADD-015,ADD-016,ADD-019
```

In `QA_Session` check for `Evidence Profile : procedure`, `decision=accepted-scoped-numbered-workflow`, `GROUNDED EXTRACTIVE FAST PATH`, `ollama_skipped=yes`, authorized citations, and response time. If proof is absent, check `scoped-workflow-evidence-incomplete` and `BOUNDED WORKFLOW FALLBACK`, and ensure **no retry** occurs. These decisions indicate *why* the output happened; still manually grade the actual answer against policy evidence.

**Rollback:**

```powershell
Copy-Item 'modules\smart_ai\portal_ai.py.before_workflow_scope_pilot' 'modules\smart_ai\portal_ai.py' -Force
```

## Unchanged

UI, active policy files, database/SQLite, Qdrant, local embeddings, reranker, authorization/company isolation, Streamlit loading, model/provider configuration, global model timeouts, and `.env`. No release/version bump.
