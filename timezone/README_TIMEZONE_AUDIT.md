# AI HR Assistant v8.8.249 — UTC Timestamp Display / History Audit Pilot

## Scope and root cause

- `database/base.py` uses `server_default=func.now()` for the `created_at` and `updated_at` columns. SQLite persists UTC instants as naive datetimes on read; PostgreSQL TIMESTAMPTZ can be aware.
- The central Audit Trail and several History/Archive UI views were formatting those values with `.strftime` before timezone conversion. A stored `05:03` UTC thus appears as `05:03 AM` instead of `01:03 PM` in `Asia/Manila`.
- Other pages already explicitly convert timestamps (announcements, notifications, leave administration, company forms, uploaded policies, attendance/OT and operational reports); they are preserved.
- The new shared helper handles both SQLite-naive UTC and aware timestamps; `DISPLAY_TIMEZONE` / `get_settings().display_timezone` remains authoritative. No hardcoded `+8` operation or automatic database rewrite.
- Audit before/after ISO datetime values are converted for display **only for known instant fields**, leaving calendar dates and other data unchanged.

## Changed code (nine existing modules)

1. `ui/pages/admin/audit_trail_page.py` — list, selected event, details, before/after and metadata display.
2. `ui/pages/admin/employees_page.py` — Employee History, archived employees, history before/after.
3. `ui/pages/admin/onboarding_management.py` — completed checklist timestamp.
4. `ui/pages/admin/hr_contacts_management.py` — archive timestamp.
5. `ui/components/disciplinary_records.py` — archive timestamp.
6. `ui/pages/user/leave_management_page.py` — last-updated credits timestamp.
7. `ui/pages/admin/integrations_page.py` — test email sent-at confirmation.
8. `services/edit_conflict.py` — concurrent-edit conflict message timestamp.
9. `services/audit_trail_service.py` — stable central history sorting even when UTC timestamps are a mix of timezone-naive and timezone-aware types.

Two added files: `utils/utc_timestamps.py` and `tests/test_v88249_audit_history_timezone_display.py`.

## Safe installation workflow — do this ONLY after the running Full 45-QA suite finishes

**Do not** use `Expand-Archive` directly over your project for this ZIP. It is an installer bundle with an explicit preflight to preserve your current code.

1. Stop Streamlit and make sure terminal QA has completed.
2. Unzip the bundle into a separate `Downloads\HR_TZ_Pilot` folder.
3. In PowerShell:

```powershell
$bundle = "$env:USERPROFILE\Downloads\HR_TZ_Pilot"
$project = 'C:\User_dev\HR_Assistant'
python "$bundle\install_timezone_pilot.py" --project "$project" --check
```

If `CHECK PASSED`, apply:

```powershell
python "$bundle\install_timezone_pilot.py" --project "$project" --apply
```

The installer checks SHA-256 checksums of all 9 original modules against the audited v8.8.249 baseline, **refuses modified/conflicting files**, preserves original modules in `.timezone_display_backups`, and installs only if safe. It never touches `.env`, HR data, DB, policy files, Qdrant, `modules/smart_ai/portal_ai.py`, or terminal QA scripts.

If any file mismatches, **stop** and supply the current file for a safe merge. Do not force overwrite.

## QA verification

```powershell
python -m pytest -q tests/test_v88249_audit_history_timezone_display.py tests/test_v88160_audit_trail_import.py tests/test_v88159_admin_concurrency_audit.py
```

Reference result: **30 passed** in the patch development environment (Streamlit UI itself was not exercised because Streamlit is not available here).

The focused existing 112 QA/RAG tests also passed unchanged on reconstructed source.

After restarting Streamlit: open Admin > Audit Trail and Employee > History; compare a known event timestamp with the local Philippine clock. Verify details and archived records, plus another unaffected control such as an attendance report.

## Rollback

Stop Streamlit, then:

```powershell
python "$bundle\install_timezone_pilot.py" --project "$project" --rollback
```

Rollback verifies files haven't changed since the patch; if later edits exist, it refuses to overwrite them.

## Important caveats

- Existing data is preserved; the patch corrects **display only** for event instants known to be UTC.
- If a historical record was written as *local time but incorrectly stored without tzinfo*, the patch cannot reliably infer that from the column. Such legacy exceptions require separate data provenance review before any migration.
- A real Windows Streamlit UI smoke test is still required before production rollout.
- There are no new case IDs, hardcoded QA questions, or company-specific audit values in production logic.
