# v8.8.243 Local-only — 45 Question Accuracy Retest

## Scope and integrity

- v8.8.243 builds directly on v8.8.242. `SMART_AI_LLM_MODE=local`; Groq/hybrid code is retained but not exercised.
- All 45 external evaluation questions remain **outside production**. Nothing from QA references is added to RAG, Ollama prompts, production routing rules, embeddings, or the company database.
- `qa/reference/V88243_45_Question_Retest_Matrix.csv` is an **evaluation-only matrix** of all 45 cases, expected source names and required facets; not an accuracy report.
- Latest local 5-question smoke (October 14 2026): ADD-001..003 provisional pass; ADD-004..005 provisional fail. Cases ADD-006..045 are NOT RUN under this new patch.
- Prior v8.8.241 full 45-question run returned many not-found answers and zero sources; that run was a different data/retrieval state and is not an accuracy benchmark for v8.8.243.

## Coverage of 45 evaluation cases

| Policy group | Cases | Count |
|---|---|---:|
| Perfect Attendance | ADD-001–ADD-005 | 5 |
| Work Schedule & Office Rules | ADD-006–ADD-015 | 10 |
| Leveling Award | ADD-016–ADD-020 | 5 |
| Business VISA & Travel | ADD-021–ADD-025 | 5 |
| Employee Benefits & Leave | ADD-026–ADD-035 | 10 |
| Training & Development | ADD-036–ADD-045 | 10 |

## Procedure on Windows (VS Code PowerShell)

Use the **same SQLite data, logged-in admin scope, Qdrant configuration, and local Ollama model** for all comparable runs. Keep a backup of any existing `.env` and local database; do not reset or reindex them unnecessarily.

1. Keep `.env`: `SMART_AI_LLM_MODE=local`; `SMART_AI_OLLAMA_MODEL=qwen2.5:7b`. No Groq API key is required.
2. If already installed, retain your removable `Terminal_QA_Test` folder in the project root. It is NOT bundled with this production ZIP, to prevent introducing QA answer keys into the app distribution.
3. Test the two unresolved cases first:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --ids ADD-004,ADD-005
```

4. If retrieval/source and answer behavior improve, run one contiguous full 45:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin
```

5. Upload both `QA_Terminal_*.txt` and the matching `QA_Session_*.log` from `Terminal_QA_Test/results/engine_traces` for manual PASS/PARTIAL/FAIL plus latency review.

## What each question must pass

- **Correctness**: requested answer against external ground truth, including conditions, exclusions, numeric/date rules, and cross-policy effects.
- **Evidence**: authorized company-only source with matching **answer-bearing section**, not merely the correct filename.
- **Behavior**: correct YES/NO conclusion, lists, workflow order, fallback conditions; safe abstention only if sources truly cannot support the answer.
- **Security**: no cross-company or unauthorized employee records; full source access remains controlled by existing permissions.
- **Latency**: capture total time, first-run index/model warmup separately from warm generation; avoid comparing cold and warm averages as equivalent.

## Release-specific interpretation

v8.8.243 uses a bounded local evidence-only retry when a YES/NO-prefixed model response is contradictory. It can improve logical consistency but may cost another local model generation for that question. For direct consequence/procedure questions, one second directly relevant policy passage may be retained when all high-ranking seeds belong to one file. Neither mechanism guarantees that all 45 questions pass; Windows real-data/real-Ollama validation is still required.

No automatic `PASS` based only on string overlap; review the actual policies and QA expected facets.
