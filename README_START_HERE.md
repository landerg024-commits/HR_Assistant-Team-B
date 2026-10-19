# AI HR Assistant v8.8.249 — Generalized Source Fidelity + UTC History Display Pilots

## Windows user steps

**Prerequisite:** full QA terminal run has completed. Stop Streamlit before applying either patch.
Keep your `.env`, SQLite HR DB, Qdrant indexes and published policies unchanged.

Run from PowerShell (virtualenv active, cwd `C:\User_dev\HR_Assistant`):

```powershell
$bundle = "$env:USERPROFILE\Downloads\HR_Quality_Time_Pilot"
$zip = "$env:USERPROFILE\Downloads\AI_HR_Assistant_v8.8.249_Generalized_Quality_And_Timezone_Pilot.zip"
$project = "C:\User_dev\HR_Assistant"
Test-Path $zip
Expand-Archive -LiteralPath $zip -DestinationPath $bundle -Force
python "$bundle\quality\install_quality_pilot.py" --project "$project" --check
python "$bundle\timezone\install_timezone_pilot.py" --project "$project" --check
```

**Only if BOTH commands print `CHECK PASSED`:**

```powershell
python "$bundle\timezone\install_timezone_pilot.py" --project "$project" --apply
python "$bundle\quality\install_quality_pilot.py" --project "$project" --apply
```

Each installer checks SHA-256 content, backs up originals, refuses unknown customized files, and supports rollback. An initial `--check` may say `already applied` if the exact same version was installed previously. That is safe.

## Code scope and behavior

The quality pilot updates only `modules/smart_ai/portal_ai.py` and adds one synthetic regression test file. No policy answers, company-specific constants, actual QA IDs, expected CSV or policy text are embedded in production code.

It adds generic, fail-closed source extraction for:
- A uniquely identified uploaded policy's top-level Policy Statement, avoiding a wrong nested sub-process `Purpose` section;
- A named policy definition with a complete examples list, retaining violation context;
- Two adjacent consequences/conditions and a complete progressive sanction table within one already authorized policy source;
- A `who + when effective` guard to reject a fast answer with recipient but no actual effective date.

The timezone pilot is the *previously audited* `v8.8.249_UTC_Time_History_Display_Pilot`, unchanged in content. It uses the configured display timezone and fixes known UTC audit/history instant rendering without rewriting database dates. Check its `README_TIMEZONE_AUDIT.md` for detailed scope and caveats.

These two patches touch disjoint production files, so one cannot silently overwrite the other.

## Local reference checks

- **153 passed** in the reconstructed development environment: 112 prior QA/RAG regression tests, 11 new synthetic quality tests, 30 timezone/audit tests.
- Archived authorized-source replay for three evidence shapes succeeded. This is NOT an actual Windows end-to-end test; run those after installation.
- The quality code paths are not guaranteed to eliminate all 12 PARTIAL and 3 FAIL cases. Retest and inspect new traces.

Windows tests (one line per command):

```powershell
python -m pytest -q tests/test_qa45_generalized_source_evidence.py tests/test_qa45_contiguous_conditional_policy_chunks.py tests/test_qa45_bounded_linked_clauses.py tests/test_qa45_scoped_workflow_candidate.py tests/test_qa45_question_contract_guard.py tests/test_consolidated_structural_quality_candidate.py tests/test_v88249_architecture_and_multiquery.py tests/test_v88248_qa_quality_hardening.py tests/test_v88247_complete_uploaded_policy_fallback.py tests/test_v88245_verbatim_published_policy_overview.py tests/test_v88244_published_policy_index_and_rule_gate.py tests/test_v88243_local_grounding_and_evidence.py tests/test_v88249_audit_history_timezone_display.py tests/test_v88160_audit_trail_import.py tests/test_v88159_admin_concurrency_audit.py
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-010,ADD-014,ADD-033,ADD-036,ADD-007,ADD-012,ADD-015,ADD-039,ADD-045
```

Manually verify Admin Audit Trail and Employee History timezone by comparing a known **UTC** DB audit instant to `Asia/Manila`, particularly around midnight; do not alter attendance punch clock time or calendar-only values.

Rollback, after stopping Streamlit (quality first, then timezone):

```powershell
python "$bundle\quality\install_quality_pilot.py" --project "$project" --rollback
python "$bundle\timezone\install_timezone_pilot.py" --project "$project" --rollback
```

If either preflight reports a source mismatch, STOP. Upload the mismatched source files to reconcile; do not use `Expand-Archive -Force` into the project.
