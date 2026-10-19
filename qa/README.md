# QA reference review — v8.8.233

The supplementary 45 reference Q&A cases are used for **evaluation only**. The HR Assistant does not import this CSV as company knowledge, does not train on it, and does not use it to return canned answers. Actual permitted company documents and records remain authoritative.

The previously existing Focused 50, Focused 55, and Comprehensive 185 questions + 17 UI checks remain separate suites. Their original Excel files were not supplied with this release, so no rows from those suites have been manufactured or overwritten. Once available, export their question sheets to UTF-8 CSV with a `question` (or `User Query`) column and optional `expected_answer` column; review them with the same command below.

## Windows / VS Code procedure

1. Launch v8.8.233 the normal way: `streamlit run app.py`. The v8.8.232 native terminal logger remains active, creating a `Terminal_Session_*.log` after app.py first executes.
2. Open a **single authorized company and portal**. Paste or type the 45 questions from `qa/reference/additional_45_sample_behavior.csv` in the Chat Assistant, retaining the unified chat session log. Use Admin and Employee portals in separate runs for permission coverage.
3. When finished, save the log and use the **offline** review generator:

```powershell
python scripts/qa_reference_review.py --reference qa/reference/additional_45_sample_behavior.csv --log "logs/chat_assistant/YOUR_COMPANY/admin/YOUR_USER/QA_Session_YYYY.log" --output "logs/qa_reviews/additional_45_admin_review.csv"
```

The paths shown for company/user are placeholders. Specify exact logs. This command makes no web request and reads no database data. Never mix companies' logs in one review.

4. Open the generated CSV in Excel, compare `actual_answer` against `expected_answer` **and the actual authorized company policy**, then enter `reviewer_verdict` (PASS / PARTIAL / FAIL / NEEDS SOURCE CHECK) and `reviewer_notes`. No automatic semantic PASS is assigned.
5. Repeat for Employee, verifying user-specific permissions and access control. Compare totals and latency, but **do not** treat high similarity or a completed retrieval as proof of correctness.
6. For the 50/55/185 suites, use the actual retained Excel questions, not reconstructed guesses. The 17 UI checks require visual/manual testing, not the text QA log parser.

## What gets extracted from QA session logs

The parser reads the numbered question sections and extracts exact question, final answer, trace ID, portal, response time, and run result. It matches case-insensitive normalized **question text only**. A paraphrased question is treated as unmatched rather than silently mapped to the wrong ground truth; reviewers can explicitly reconcile paraphrases outside this tool. Multiple exact runs use the last provided observation and report how often it was seen. An Ollama timeout or unavailable-information answer receives `Needs Investigation`. Everything else requires human verification against the live company record.

**Security:** The generated review CSV contains employee questions and answer text. Restrict file access and redact sensitive details before sharing. Do not commit HR runtime logs, private policy content or credentials to source control.

## v8.8.239 — Grounded evidence cohesion and new 185-case QA reference

- Branched from v8.8.238; **no changes to UI/loading, SQLite, Qdrant, HR rules or permissions**.
- Production: the extractive fast path selects multiple policy clauses only from one authorized original document; a compound query missing an explicit second fact falls through to grounded synthesis. Document RAG prompts no longer portray unsourced portal-help text as verified policy evidence. No reference question, person, date or expected answer is copied into production routing.
- `qa/reference/comprehensive_185_behavior_reference.csv` holds 185 user-supplied *evaluation-only* cases (113 Admin, 38 Employee, 34 shared). These describe seeded QA data; they **do not create or verify** live records. Do not index this CSV as RAG data.
- `scripts/qa_reference_review.py` isolates results by portal, company and employee; tests with an account login require an explicit private login→user-id mapping via `--account-map` (JSON), and results from multiple user scopes must be reviewed separately. It NEVER auto-marks PASS.
- Do not interpret automated unit tests as evidence that 185 live Windows QA questions pass; they require real seeded data and authorized Admin/Employee tests.
