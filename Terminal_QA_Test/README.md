# Terminal-only QA testing (removable)

This `Terminal_QA_Test/` folder is separate from production. Cut or delete the **entire folder** after testing. It does not install Playwright, open a browser, modify HR/RAG logic, or add questions to the company vector database.

## Installation

Copy `Terminal_QA_Test/` into your **AI HR Assistant v8.8.239 project root**, next to `app.py`. Use the project's usual Python/virtual environment and `.env`, existing SQLite database, local Qdrant, Ollama and dependencies. No Streamlit server needs to run, but local Ollama should be available for generation if enabled in your project.

Run inside VS Code **Terminal (PowerShell)** from the project root:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --limit 5
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin
python Terminal_QA_Test/run_terminal_qa.py --suite 185 --portal admin
python Terminal_QA_Test/run_terminal_qa.py --suite 185 --portal employee --username lgarcia
python Terminal_QA_Test/run_terminal_qa.py --suite both --portal admin
```

Each command requests a company code, account, and **hidden password**, then verifies them through the project's existing AuthService. Admin tests require actual Admin clearance. Employee cases are filtered by the actual username; to test other Employee accounts, log in separately and repeat. It does not elevate user scope or allow switching identity mid-run. Password-change-required accounts are rejected until normally changed.

The additional file contains **185 cases**, not 180. `both` is the 45 + 185 suite; there can be different number of applicable questions per portal. Use `--ids ADD-005,ADD-010` or `--start 10 --limit 5` for focused retesting. Example without login or model invocation:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 185 --portal admin --dry-run
```

## Output

Every case writes an append-and-flush UTF-8 `.txt` log to `Terminal_QA_Test/results/QA_Terminal_*.txt`. Includes question, exact user-supplied expected answer, actual engine answer, retrieved source metadata, warning/error, time, conservative auto-check and summary. Full existing engine forensic traces are redirected under `Terminal_QA_Test/results/engine_traces/`, grouped by company/portal/user. **Logs can contain private HR records**: keep private and do not commit or share openly.

Comparison defaults to `REVIEW_REQUIRED` unless an answer is exact text or an engine error, because string matching alone cannot honestly grade semantic correctness. Optional **second local Ollama call** may estimate PASS/PARTIAL/FAIL separately (and can be inaccurate):

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --judge ollama
```

The ground-truth answers are sent **only to the separate grader after** the production answer has returned, not to the production Chat Assistant. Ground truth describes expected QA seed data and is not proof that it exists in the currently configured database. Independent cases reset chat history; arrow-separated follow-up scenarios preserve context across each sequence. Cases requiring GUI report download/preview or unspecified actors are marked `MANUAL_UI` / `NEEDS_SETUP`, not fabricated as PASS.

The CLI calls the **same production deterministic + SmartPortalAssistant path** as the Streamlit chat pages, but does not test widget/browser UI behavior. First run may trigger local embedding/Qdrant index initialization. Stop with Ctrl+C; completed cases stay in text logs. Test accounts are authenticated to the same company as the active `.env` DB. Run only on a trusted machine.

**No source files outside this folder are changed by installing the runner.** The regular application may still have its usual runtime DB cache/index behavior when its real engine is invoked. On first login an outdated Argon2 password hash may be rehashed by the normal AuthService authentication procedure.
