# AI HR Assistant v8.8.249 — Consolidated answer-quality candidate (NOT a new release)

## Scope

A small, opt-in-to-deploy candidate patch on top of the **clean v8.8.249** installation. **No version-number bump, data migration, schema changes, UI changes, retrieval/indexing changes, multi-query changes, new LLM dependency, or timeout setting change.**

The candidate addresses a general selection defect: a ranked sentence subset may omit necessary sibling rules in an otherwise authorized source. A conservative extraction stage uses one of three structural signals only when sufficient **same-source, authorized** evidence exists:

1. Complete explicitly named eligibility/coverage enumeration plus same-document classification conditions. No prices appended from table columns; no cross-company/source join.
2. A chronological `after ...` condition and immediately connected `shall/will then ...` action in the same policy chunk.
3. A `how long ... , and what is required for ...` question with a duration, requirement and approval evidence inside one policy chunk, excluding the next section.

If a structural proof is missing, the previous retrieval/extraction/LLM path is used. No company answers, synthetic grades, QA case IDs or expected outcomes have been hardcoded into production source. All existing role/company safety mechanisms remain in effect. Adaptive multi-query remains **disabled** unless separately enabled by the user's pre-existing configuration.

## Results in local test environment

- 81 tests passed across the new structural regression tests and v8.8.240–249 relevant suites.
- Broader selected suite with `tests/test_smart_portal_ai.py`: 84 pass, one historical UI-text assertion fail. The identical assertion fails on the untouched clean v8.8.249 source (not introduced by this candidate).
- Source-level smoke checks using archived user-provided policy document text returned full requested facets for three patterns. This is NOT the same as the Windows RAG run, and cannot establish real latency, availability or full 45-case accuracy.

## Install only after baseline smoke tests

1. Stop Streamlit and back up `modules/smart_ai/portal_ai.py`.
2. Extract the patch to the root of your CLEAN v8.8.249 project. It replaces exactly that active Python file and adds **one** synthetic regression test and these notes.
3. Run:
   `python -m pytest -q tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py`
4. Expected in the validated local environment: **55 passed**.
5. Run focused end-to-end terminal QA with multi-query still disabled:
   `python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-015,ADD-016,ADD-019,ADD-041`
6. Compare final answer facets, evidence source and latency to the previous four-case log. If any regression, restore the previous `portal_ai.py` backup. Do not enable the adaptive multi-query pilot during this comparison.

## Release decision

This is one optional controlled quality pilot, **not an instruction to deploy immediately** and not a claim that all 45 cases now pass. Clean v8.8.249 remains the stable test baseline. Do not stack older patch archives on this distribution.
