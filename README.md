

### v8.8.235 — UI-only loading transition (based on v8.8.233)

- The browser's persisted Light Mode background remains active during Streamlit reruns.
- A delayed, reduced-motion-friendly spinner and skeleton replace sufficiently long blank rerender intervals and protected portal/sidebar transitions.
- An explicit page-ready signal is emitted after each login, Admin, and Employee page completes rendering; a 10-second browser-side fail-safe prevents stuck overlays.
- Ordinary chat and form spinners remain intact; no HR, Chat Assistant, RAG, embeddings, Qdrant, or permissions code was changed.
- On a full first-load, before Streamlit and the Python script initialize, custom JavaScript cannot be displayed; native theme background remains the fallback.
- This version intentionally forks the stable v8.8.233 code, **not** the v8.8.234 answer-routing changes that regressed in user QA.
# AI HR Assistant

AI HR Assistant is a local Streamlit HR portal with separate administrator and employee workspaces. It includes authentication, employee management, attendance/DTR, leave and overtime workflows, company forms/documents, announcements, reports, audit history, policy Q&A, and external email/SMS notifications.

This README is an execution and setup guide. Release history is intentionally not maintained here.

### Authoritative setup files

Use the project-root `README.md` and `requirements.txt` as the single source of truth for setup and dependencies. The legacy `schemas/README.md` and `schemas/requirements.txt` are compatibility pointers only and must not maintain a separate dependency/setup copy.

## 1. Requirements

Recommended local environment:

- Windows 10/11
- Python 3.11+
- PowerShell
- Internet connection only for features that call external services such as real email or SMS
- Ollama for the local Chat Assistant

The main HR application and database can still run locally without external email/SMS access.

## 2. Open the Project

Open PowerShell in the project root, where `app.py` and `requirements.txt` are located.

Example:

```powershell
cd C:\user_dev\hr_assistant
```

## 3. Create and Activate the Virtual Environment

Create the environment once:

```powershell
python -m venv .venv
```

Activate it whenever you work on the project:

```powershell
.\.venv\Scripts\Activate.ps1
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install project dependencies:

```powershell
python -m pip install -r requirements.txt
```

## 4. Configure `.env`

The project reads local configuration from `.env`.

If `.env` does not exist, copy `.env.example` first:

```powershell
Copy-Item .env.example .env
```

At minimum, review:

```text
DATABASE_URL
INITIAL_COMPANY_CODE
INITIAL_COMPANY_NAME
INITIAL_ADMIN_USERNAME
INITIAL_ADMIN_EMAIL
INITIAL_ADMIN_PASSWORD
```

Do not commit real passwords, SMTP credentials, SMS gateway tokens, or production secrets to Git.

## 5. Create / Verify the Database

Create the database when setting up a new local installation:

```powershell
python -m scripts.create_database
```

Verify the database:

```powershell
python -m scripts.check_database
```

Create the initial company and administrator account when needed:

```powershell
python -m scripts.create_initial_data
```

Verify initial data:

```powershell
python -m scripts.check_initial_data
```

The normal runtime schema upgrade path is additive and should preserve existing records.

## 6. Ollama Chat Assistant Setup

Install Ollama on the PC and make sure the Ollama service is running.

Pull the configured local model:

```powershell
ollama pull qwen2.5:7b
```

Check installed models:

```powershell
ollama list
```

Chat Assistant developer configuration is centralized in:

```text
config/chat_assistant_settings.py
modules/smart_ai/prompts/hr_assistant_prompt.py
```

Use `config/chat_assistant_settings.py` for model/generation/retrieval tuning and
`hr_assistant_prompt.py` for answer instructions and formatting rules. Matching
`SMART_AI_*` values in `.env` can override the safe defaults without editing
business logic.

The default local Ollama endpoint is:

```text
http://localhost:11434
```

The Chat Assistant uses a hybrid company-knowledge design: deterministic
company-scoped queries for structured HR records and permission-sensitive
data, plus grounded retrieval for published policies, portal workflows, and
readable Company Form/Documents file content. Admin questions can return live
employee lists, hierarchy-derived Manager/Leader sets, date-aware HR results,
follow-up counts/lists, and charts when the requested comparison benefits from
a visual. Employee responses remain restricted to the employee's authorized
self/team scope and published company information.

Long policy and Company Form/Documents content is indexed with document-aware
retrieval. Each file keeps its own file/title/section/page/chunk metadata; the
retriever first selects the most relevant company files, then ranks chunks
inside those files with BM25 plus the optional local Qdrant semantic path.
v8.8.222 uses adaptive structure-aware chunking: complete semantic sections are
kept intact when they fit inside the hard maximum, while oversized sections are
split on sentence/row/clause boundaries before any fixed-word fallback. Policy
splits use a 220-word soft target (120 minimum, 300 hard maximum); Company
Form/Documents use a 280-word soft target (160 minimum, 360 hard maximum).
Overlap is adaptive at 14% (bounded to 16-44 words) and is used only between
fragments of the same split section. The final context conditionally adds an
adjacent fragment only when the selected evidence came from a section that was
actually split. Structured employee, attendance, leave, overtime, and other
live HR records remain deterministic and are not flattened into document chunks.

The company-only boundary is unchanged: retrieval is scoped to the authenticated
company and current portal role before ranking, Qdrant queries are restricted
to the exact authorized document-set snapshot, and Qwen must not answer from
outside/general knowledge when company evidence is unavailable.

## 7. Run the Application

From the project root with the virtual environment active:

```powershell
streamlit run app.py
```

Open the local Streamlit URL shown in PowerShell, normally:

```text
http://localhost:8501
```

## 8. External Email Notifications

Normal setup is performed inside the application:

1. Log in as Administrator.
2. Open **External Notifications**.
3. Enter the **Company Sender Email**.
4. The app automatically detects supported common providers from the sender email domain.
5. Enter the sender credential or app password required by that account.
6. Save the settings.
7. Send a test email.
8. Turn on **Activate Email Notifications** when ready.

There is no Gmail/Outlook/Yahoo provider selector. The sender email is the input used for provider detection.

For custom/company domains, the email domain alone may not reveal the real outgoing server. In that case, **Advanced SMTP Settings** is shown so the company SMTP host, port, and encryption can be entered once.

Employee recipients do not need separate notification setup. The external recipient is taken automatically from:

```text
Employee Master Record -> Work Email
```

The saved email credential is never displayed back in the browser.

### Optional Email CLI Utilities

The existing scripts remain available as fallback/admin utilities if the UI cannot be used:

```powershell
python scripts\configure_smtp.py
python scripts\test_smtp_email.py
```

They are not required for the normal in-app setup flow.

## 9. External SMS Notifications

SMS is also configured inside **Admin Portal -> External Notifications**.

The company configures the SMS gateway once. Employees do not choose Globe, Smart, DITO, or another recipient network.

Normal setup:

1. Enter the company SMS gateway Account SID.
2. Enter the Auth Token.
3. Enter the SMS sender number or Messaging Service SID.
4. Confirm the default country code, such as `+63`.
5. Save the settings.
6. Send a test SMS.
7. Turn on **Activate SMS Notifications** when ready.

Employee recipients are taken automatically from:

```text
Employee Master Record -> Telephone / Mobile No.
```

For Philippine local numbers, the default `+63` configuration can normalize values such as:

```text
09171234567 -> +639171234567
```

The current internet SMS gateway adapter is Twilio Programmable Messaging. The adapter is isolated from HR business logic so another gateway can be added later without changing employee records or approval workflows.

### Optional SMS CLI Utilities

Fallback/admin utilities remain available:

```powershell
python scripts\configure_external_notifications.py
python scripts\test_sms_notification.py
```

They are not required for normal in-app setup.

## 10. External Notification Safety

External email/SMS is secondary to the in-app HR record.

The application preserves these rules:

- HR data is committed first.
- External delivery happens only after a successful transaction commit.
- A rollback sends no external notification.
- Email/SMS provider failure does not undo a successful leave, overtime, attendance, announcement, form, or other HR action.
- Existing rich leave emails are not duplicated by the generic external-email mirror.
- Email and SMS channels can be enabled independently.

## 11. Employee Contact Data

For external delivery to work, employee records should contain the applicable destination fields:

```text
Work Email
Telephone / Mobile No.
```

If an employee has no Work Email, email delivery for that recipient is skipped.

If an employee has no Telephone / Mobile No., SMS delivery for that recipient is skipped.

The remaining enabled channel can still be used.

## 12. Recommended Validation Commands

Basic project check:

```powershell
python -m scripts.check_project
```

Python syntax check:

```powershell
python -m compileall -q .
```

Run automated tests:

```powershell
python -m pytest -q
```

For focused notification checks:

```powershell
python -m pytest tests\test_email_integration_service.py tests\test_v88162_external_notifications.py tests\test_v88162_external_notifications_static.py -q
```

## 13. Common Troubleshooting

### `ModuleNotFoundError`

Make sure the virtual environment is active and dependencies are installed:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run project modules from the project root. For scripts that import project modules, prefer module execution where supported:

```powershell
python -m scripts.create_initial_data
```

### Streamlit command not found

Use:

```powershell
python -m streamlit run app.py
```

### Email test fails

Check:

- Sender email
- Provider/account SMTP permission
- App password or SMTP credential
- Custom SMTP host/port/encryption when using a company domain
- Internet/firewall access

Some email providers enforce account-specific authentication rules. The app detects common server settings where possible, but the provider still controls which authentication method the account may use.

### SMS test fails

Check:

- SMS gateway Account SID
- Auth Token
- Sender number or Messaging Service SID
- Destination number format
- Account permissions and balance/provider restrictions
- Internet/firewall access

### Changes to `.env` are not reflected

In-app notification settings clear the cached application settings and rerun the page automatically. For manual `.env` edits outside the app, restart Streamlit.

## 14. Important Local Data

Before replacing or moving a project installation, back up the live data you want to keep, especially:

```text
.env
data\hr_assistant.db
data\uploads\
data\smart_ai\
```

Do not replace a working production database with a sample database from another package.

## 15. Chat Assistant Terminal Retrieval Trace (v0.8.8.217)

The Admin and Employee Chat Assistants can print a developer-only retrieval
trace to the Streamlit server terminal. Nothing from this trace is rendered in
the portal UI.

Default package setting:

```text
SMART_AI_TERMINAL_DEBUG_ENABLED=true
```

The trace shows the user question, contextual retrieval query, authorized
knowledge counts, file-stage BM25/vector/hybrid scores, selected files,
chunk-stage BM25 scores, vector cosine nearest-neighbor scores, hybrid/RRF
ranking, selected/final evidence chunks, bounded chunk excerpts, deterministic
router answer, Ollama model/timing/retry status, raw Qwen answer, and final Chat
Assistant answer.

To disable the terminal trace, set:

```text
SMART_AI_TERMINAL_DEBUG_ENABLED=false
```

and restart Streamlit. Additional display limits are controlled by
`SMART_AI_TERMINAL_DEBUG_TOP_K`, `SMART_AI_TERMINAL_DEBUG_EXCERPT_CHARS`, and
`SMART_AI_TERMINAL_DEBUG_ANSWER_CHARS`.

## 16. Terminal Candidate Answers Trace (v0.8.8.218)

The Chat Assistant terminal diagnostics now also print **Candidate Answers — Retrieved Evidence**. Each candidate includes the final retrieval score, answer-fit diagnostic score, source document, section/page/chunk metadata, and a bounded question-focused `possible_answer` excerpt. The terminal also shows `ANSWER OPTION — ROUTER`, `ANSWER OPTION — QWEN`, and an `ANSWER SELECTION` line explaining which path produced the final chat answer. These diagnostics are terminal-only and do not add Streamlit UI elements or alter retrieval/ranking/generation behavior.

## v8.8.219 — Readable Chat Retrieval Debug + Relevance Guard + Top Source

This checkpoint keeps the v8.8.218 retrieval/chunking/parser architecture and focuses on Chat Assistant diagnostics and answer safety:

- Terminal retrieval diagnostics are rendered as a structured per-question report (question analysis, file/chunk ranking, candidate answers, final evidence, relevance decision, top nearest source, Ollama/Qwen status, final answer selection, and request summary).
- Each enabled terminal trace is mirrored to a request-local `.log` file under `logs/chat_assistant/` by default. Log writing is best-effort and cannot break the Chat Assistant if the folder is unavailable.
- A retrieval relevance/no-match guard prevents an unrelated nearest policy chunk from being forced into an answer. Existing out-of-company/HR scope behavior and current no-information answer categories are retained.
- Policy Q&A also applies a lightweight topic-support guard before accepting a deterministic policy match, so the same fail-closed behavior remains when Ollama is unavailable and Smart AI enhancement is skipped.
- Admin and Employee Chat UI display only one top approved policy source. Supporting chunks/sources remain visible in terminal/log diagnostics for debugging.
- The previously discussed special broad-topic coverage expansion (for example, expanding `Leave policy` into every leave-policy section) is intentionally **not** included. Short valid topics continue through the normal existing retrieval path.

Default diagnostics settings:

```text
SMART_AI_TERMINAL_DEBUG_ENABLED=true
SMART_AI_TERMINAL_DEBUG_LOG_ENABLED=true
SMART_AI_TERMINAL_DEBUG_LOG_DIR=logs/chat_assistant
```

## v8.8.220 — Compact Live Terminal + Full Forensic Log

This checkpoint is based strictly on v8.8.219 and changes only Chat Assistant
diagnostic presentation/version/tests. Retrieval ranking, relevance guard,
Qwen prompting, source selection, parsers, permissions, and HR workflows are
retained.

When the request-local evidence log is available, the **live terminal** now
shows only the information needed for fast debugging:

- user question;
- files/chunks searched and matched;
- final chunks used;
- top selected source files with file-level score, matched/total chunk count,
  and best chunk;
- up to three candidate answers with answer-fit score, retrieval score, source,
  chunk, and concise possible answer;
- final answer, top source/chunk/final score; and
- Ollama/retry/result timing plus the full-log path.

The per-request `.log` still keeps the **full forensic trace** from v8.8.219:
question analysis, all BM25/vector/hybrid stages, chunk excerpts, selected
evidence, relevance/no-match decision, router/Qwen options, top-nearest source,
runtime events, and request summary. If the log cannot be created, the terminal
automatically falls back to the verbose trace so diagnostic evidence is not
silently lost.


## v8.8.222 — Adaptive Chunking, Evidence Gate & Chunk Diagnostics

This checkpoint is based strictly on v8.8.221. Qdrant, local embeddings, BM25,
the optional CrossEncoder reranker, HR rules, tenant/role/user permissions, and
the existing Qwen/Ollama generation path are preserved.

The document chunker now keeps coherent sections whole whenever possible and
uses soft targets only for sections that exceed the configured hard maximum.
Oversized sentences/rows prefer clause boundaries before falling back to fixed
word windows. Every generated policy/company-document chunk stores diagnostic
metadata including word count, overlap words, boundary reason, section-local
chunk position, and continuation flags.

Per-question request logs now include privacy-safe **CHUNK DIAGNOSTICS** for
each processed file plus a **CHUNKING BATCH SUMMARY**. Full raw chunk text is
off by default; the existing retrieval diagnostics continue to show bounded
evidence excerpts. This makes it possible to distinguish parsing/chunking
problems from BM25/Qdrant/reranking/generation problems without duplicating all
HR document text into the log.

Document-centric RAG requests also use a deterministic pre-generation evidence
gate. Topic anchors must match, and exact-fact profiles such as amount,
count/duration, date/time, consequence, eligibility, and procedure must contain
a sufficiently direct answer-bearing cue before generation is allowed. Weak
matches therefore fail closed to the existing not-found/undetermined response
instead of asking the LLM to infer a missing fact. No second LLM/judge call is
added, so this safety layer has negligible model latency.

Default adaptive settings:

```text
SMART_AI_ADAPTIVE_CHUNKING_ENABLED=true
SMART_AI_POLICY_CHUNK_MIN_WORDS=120
SMART_AI_POLICY_CHUNK_TARGET_WORDS=220
SMART_AI_POLICY_CHUNK_MAX_WORDS=300
SMART_AI_COMPANY_DOCUMENT_CHUNK_MIN_WORDS=160
SMART_AI_COMPANY_DOCUMENT_CHUNK_TARGET_WORDS=280
SMART_AI_COMPANY_DOCUMENT_CHUNK_MAX_WORDS=360
SMART_AI_ADAPTIVE_OVERLAP_RATIO=0.14
SMART_AI_ADAPTIVE_OVERLAP_MIN_WORDS=16
SMART_AI_ADAPTIVE_OVERLAP_MAX_WORDS=44
SMART_AI_CHUNK_DIAGNOSTICS_ENABLED=true
SMART_AI_CHUNK_DIAGNOSTICS_FULL_TEXT=false
SMART_AI_EVIDENCE_GATE_ENABLED=true
SMART_AI_EVIDENCE_GATE_MIN_ANSWER_CUE=0.70
```


## v8.8.221 — Qdrant Vector Database Migration

This checkpoint is based strictly on v8.8.220 and changes the Chat Assistant
vector database from ChromaDB to **Qdrant** while preserving the existing
document parsing, chunking, BM25 + vector hybrid retrieval, local embedding
model, optional reranker, relevance guard, company/user/role permissions,
Qwen/Ollama generation path, and terminal/full-log diagnostics.

Qdrant runs in persistent **local mode** at `data/smart_ai/qdrant` by default,
so no separate Qdrant server, Docker container, cloud account, or internet
connection is required for vector retrieval. The exact authorized retrieval
snapshot remains stored as `retrieval_scope` payload metadata and is applied
as a Qdrant filter on every vector query. Existing Chroma index files are not
used by this checkpoint; Qdrant rebuilds vectors from the authorized source
documents on first retrieval.

Default vector settings:

```text
SMART_AI_QDRANT_DIR=data/smart_ai/qdrant
SMART_AI_QDRANT_COLLECTION=hr_portal_knowledge
```


## v8.8.223 — Source-Aware Routing Guard & Fail-Closed Aggregate Queries

This checkpoint hardens Chat Assistant routing without hard-coding company HR
benefits, entitlements, tenure rules, or other business facts. The employee
aggregate engine now accepts only explicit collection/count/group/chart request
shapes and rejects conditions it cannot actually apply. Relative-clause words
inside explanatory questions (for example, an employee noun followed later by
"who") no longer turn the request into an employee list.

Admin routing also no longer treats the bare presence of the word `employees`
as a headcount request. Specific policy questions are separated from policy
library-summary requests. A final source-routing guard in Smart AI can recover
an incompatible `employee_aggregate` result into the normal authorized,
evidence-gated retrieval path instead of returning a wrong deterministic list.

The design remains fail-closed: live structured handlers stay authoritative only
for query shapes and filters they truly support; otherwise the request falls
through to existing company-scoped retrieval and its evidence/no-match guard.
Active company-configured Benefits are now included as shared RAG knowledge
(name, category, description, eligibility, effective date, enrollment guidance,
and contact), while archived Benefits are excluded. Qdrant, local embeddings,
BM25, reranker, adaptive chunking, permissions, and LLM routing are otherwise
unchanged.

## v8.8.224 — Vector Activation, Grounded Fast Path & Latency Hardening

This checkpoint is based strictly on v8.8.223 and preserves the source-aware
router, adaptive chunking, evidence/no-match gate, HR permissions, deterministic
HR rules, and existing Ollama fallback behavior.

The Qdrant vector path is now fully installable instead of silently optional:
`sentence-transformers` is included in `requirements.txt` for the configured
`intfloat/multilingual-e5-small` local embedding model. Qdrant diagnostics now
report a safe `FILE VECTOR STATUS` and `CHUNK VECTOR STATUS` in each request log
so missing packages/model-load/query failures cannot masquerade as an ordinary
zero-result semantic search. Authorized snapshot signatures are order-stable,
persisted Qdrant snapshots can be reused after an application restart, document
embedding uses bounded batches, and Qdrant upserts use bounded batches.

For direct, high-confidence policy/document fact shapes (list, procedure,
amount, duration/count, date/time, eligibility), the assistant now has a
**grounded extractive fast path**. After the existing evidence gate accepts the
retrieved company evidence, the fast path selects complete source sentences or
rows verbatim and skips Qwen. It does not paraphrase or invent company rules,
and it preserves source qualifiers such as role/scope/conditions. YES/NO,
follow-up, comparison, ambiguous, and synthesis-heavy requests continue to use
Qwen. This removes the local 7B generation cost from straightforward policy QA
while strengthening faithfulness.

New default tuning:

```text
SMART_AI_EMBEDDING_BATCH_SIZE=64
SMART_AI_QDRANT_UPSERT_BATCH_SIZE=128
SMART_AI_GROUNDED_EXTRACTIVE_FAST_PATH_ENABLED=true
SMART_AI_GROUNDED_EXTRACTIVE_MIN_ANCHOR_COVERAGE=0.60
SMART_AI_GROUNDED_EXTRACTIVE_MAX_ITEMS=6
SMART_AI_GROUNDED_EXTRACTIVE_MAX_CHARS=1800
```

After upgrading an existing virtual environment, run `python -m pip install -r
requirements.txt` so the local embedding runtime is installed. The configured
embedding model may need to be downloaded/cached once before fully offline
semantic retrieval is available on a clean machine.

## v8.8.225 — Universal source routing and answer compatibility

- Shared grammatical query-shape analyzer handles responsibility and conditional-request clauses without hard-coded company policy/benefit content.
- Both Admin and Employee portals retain their existing structured HR handlers and authorization; generic policy/procedure questions are no longer stolen by hierarchy or disciplinary record lookups.
- Every `never-enhance` intent is checked at the shared assistant boundary. A detected output-shape conflict recovers only into company/role-authorized, evidence-gated retrieval, never into an unverified employee list.
- Direct actor/action policy facts can use evidence-only fast extraction when the existing relevance guard accepts matching document evidence; complicated or uncertain questions stay on the regular grounded Qwen path.
- Logs include `UNIVERSAL ANSWER COMPATIBILITY GUARD` for recovered conflicts. Qdrant, local embeddings, BM25, reranker and current LLM architecture otherwise unchanged.


## v8.8.226 — Unified per-conversation Chat Assistant QA session logs

Based only on the **v8.8.225 local-Qdrant/local-Qwen branch**. No HR rule,
RAG, LLM, attendance, leave, or portal display changes.

- When both `SMART_AI_TERMINAL_DEBUG_ENABLED=true` and
  `SMART_AI_TERMINAL_DEBUG_LOG_ENABLED=true`, Admin and Employee Chat Assistants
  produce **one forensic `.log` file per chat/QA conversation**, not one file
  per question. Each submission retains its own Trace ID, numbered question,
  all authorized retrieval stages, final answer, runtime status and timing.
- **New Admin Conversation** / **New HR Conversation** starts a **new** log
  session. Different browser tabs/Streamlit sessions receive different opaque
  session IDs. Authenticated company, user, and portal scopes have separate
  filesystem directories; raw user/company identifiers are excluded from
  filenames. Each question is committed as one complete, lock-protected append
  to avoid mixed blocks during concurrent use.
- Existing direct code/test users that do not provide a chat session ID retain
  legacy per-request `chat_trace_*.log` files.
- A connection-preflight failure is captured as another question in the same
  session log, without including secrets or stack traces.

**Finding the one file to send for a QA session (Windows PowerShell):**

```powershell
Get-ChildItem -Path .\logs\chat_assistant -Filter 'QA_Session_*.log' -Recurse |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 FullName, LastWriteTime
```

Check the `Session ID`, `Portal`, and question list in the file before sharing;
the latest file may belong to another user when multiple users test together.
You may instead use the exact `Full Log` path printed in the server terminal
at the end of your most recent Chat Assistant request. Send just that `.log`.

Configuration:

```text
SMART_AI_TERMINAL_DEBUG_ENABLED=true
SMART_AI_TERMINAL_DEBUG_LOG_ENABLED=true
SMART_AI_TERMINAL_DEBUG_SESSION_LOGGING_ENABLED=true
SMART_AI_TERMINAL_DEBUG_LOG_DIR=logs/chat_assistant
```

Set `SMART_AI_TERMINAL_DEBUG_SESSION_LOGGING_ENABLED=false` to restore legacy
per-question files. **Production:** raw questions, HR records and document
excerpts may appear in QA/debug logs. Set `SMART_AI_TERMINAL_DEBUG_LOG_ENABLED=false`
(and normally `SMART_AI_TERMINAL_DEBUG_ENABLED=false`) when forensic logs are
not needed; restrict filesystem access and apply local log retention policy.
The path hashes are organizational labels, **not encryption or access control**.
Completed questions are durably appended; an abruptly terminated **in-flight**
request may not have its complete trace because each request is buffered until
completion to prevent interleaving. No extra Streamlit widgets are introduced.


## v8.8.227 — Universal Answer-Target & Condition Fidelity + Stage Timings

Based strictly on v8.8.226 (unified Admin/Employee QA session logs). All company/role
isolation, HR deterministic calculations, Qdrant, BM25, adaptive chunking, Qwen
configuration, and session logging remain unchanged.

- For document-grounded **who is responsible / who informs / what is requested**
  requests, the extractive fast path must cover the action predicate, not merely
  the subject keywords. Predicate families are language-level (notify, payment,
  request, provide, approve, submit), never hard-coded company benefit/policy facts.
- A user request for the **first/default step** excludes unrelated fallback-only
  conditions. Context from the immediately preceding *same-source* section is
  used for ranking only, while final output remains verbatim authorized evidence.
  If the requested predicate has no supporting extracted unit, the fast path
  declines and the existing evidence-gated Qwen path handles the request.
- Existing `VERIFIED ROUTER/EXTRACTIVE ANSWER` instructions clarify that an
  answer must cover the requested target, primary/default vs exceptional branch,
  and all supported parts; no unsupported inference is permitted.
- Terminal and unified-session traces now contain `KNOWLEDGE BUILD TIMING`,
  `FILE SEARCH TIMING`, `CHUNK SEARCH TIMING`, `RERANK TIMING`,
  `RETRIEVAL TIMING`, and `EXTRACTIVE VALIDATION TIMING`. Successful vector
  status lines additionally include model setup, index, query embedding,
  Qdrant query, and total durations (seconds). These timings help separate
  indexing/model initialization from warm request latency; they do not set
  performance guarantees.

Actual Windows/Streamlit/Qdrant/Ollama behavior must still be validated with a
new QA session, including the same five user questions and wider HR modules.

## v8.8.228 — Compound Answer Coverage and Shared Local Embedding Runtime

Based strictly on v8.8.227 on the local Qdrant/Ollama branch. This release
changes only company-knowledge answer selection and local vector runtime
initialization. Deterministic HR services, role/company/user authorization,
Qdrant retrieval-scope filters, adaptive chunking, Admin/Employee UI and
per-conversation QA session logs remain in place.

- **Conjunctive answer fidelity:** for direct who/what action questions that
  explicitly ask about **X and Y**, require separate action-linked supporting
  evidence for both requested objects. The fast path no longer treats an
  unrelated condition (for example, a *lack of* X) as proof of responsibility
  for X. For an anaphoric rule such as “Transportation expenses ... . Those
  expenses are paid by ...”, the extractor may copy the immediately preceding
  sentence together with the payment sentence, from the **same authorized
  source chunk**. If any required component is unsupported, skip extraction
  and retain the existing evidence-gated LLM/abstention route. The language
  checks contain no configured company policy or benefit rules.
- **Process-local embedding model reuse:** file-stage and chunk-stage
  retrievers share one lazily loaded SentenceTransformer instance for the
  configured model name, including across users/queries in one app process.
  Initialization and inference use separate locks to prevent concurrent model
  construction or unsafe calls on the same model. **Only the model object** is
  shared: never cache questions, HR documents, vector search results, or
  permission-scoped embeddings across users. The Qdrant `retrieval_scope`
  filter remains mandatory. Model cache is lost on a process restart, so cold
  start/model downloads may still be slow. Diagnostics now include
  `model_cache=loaded|reused|instance` and model setup timing.

The local Windows/Streamlit runtime and exact production latency have **not**
been measured here. Retest the five original questions in one `QA_Session_*.log`,
then move to the previously retained Excel Focused 50/55 and comprehensive
185-question matrices for all HR modules. For production, disable raw forensic
logs and apply retention and OS access controls.


## v8.8.229 — Separate terminal/runtime log for QA

**Windows:** after activating/installing the existing environment, double-click
`Start_AI_HR_Assistant_With_Terminal_Log.bat` in the project root. Or run:

```powershell
python scripts/run_with_terminal_log.py
```

It starts the usual `python -m streamlit run app.py` command and simultaneously
streams **the entire server terminal stdout and stderr** to the visible console
and to a UTF-8 file at `logs/runtime/Terminal_Session_YYYYMMDDTHHMMSS_*.log`.
This includes Streamlit startup messages, emitted Python warnings, tracebacks,
Ollama timeouts, and any other messages printed by the app. The launcher
records the process exit code and captures startup failures, too.

- **One terminal file per Streamlit server launch** (possibly `_part02.log` if
  output exceeds the default 50 MB). The server-wide terminal file can contain
  output from **all concurrently connected users**; it is **not** per user.
- Existing **one per chat/conversation** `QA_Session_*.log` files remain
  untouched. Send the `QA_Session` log **and** the latest `Terminal_Session` log
  when troubleshooting. Do **not** share whole terminal logs without reviewing
  them for employee/private data, file paths, tokens, or credentials.
- Startup automatically retains the 12 most recent terminal log parts by
  default (best-effort). Optional environment variables:
  `AI_HR_TERMINAL_LOG_RETENTION_FILES` (1–100) and
  `AI_HR_TERMINAL_LOG_MAX_MB` (1–200; default 50). Logs are excluded by
  `.gitignore` and are written under the working project root. Secure directory
  ACLs and retention remain the operator's responsibility.
- **Historical v8.8.229 limitation (resolved in v8.8.232):** At this
  checkpoint, `streamlit run app.py` did not automatically capture application
  output. See the v8.8.232 section for direct-run capture and full startup options.
  Python warnings/errors that a library suppresses or does not print cannot
  be recovered through the terminal capture. This is QA debugging, not
  a production-grade centralized log collection system.
- Answer-selection logic, Qdrant/embeddings, RAG, LLM retries/timeouts, and
  Admin/Employee HR workflows are intentionally **unchanged** in this version.

## v8.8.230 — Document-grounded recipient/expense fidelity & runtime warning cleanup

Continue from v8.8.229; this is the **local Qdrant + Qwen/Ollama** checkpoint,
not the separate Groq/OpenRouter branch.

- **Names/recipients in a question matter:** For a direct question that names
  multiple recipients of a notification ("notify A, B and C"), the extractive
  selector must return a clause that actually mentions all named recipients.
  A relevant sentence naming only A and C is not considered complete.
- **Coordinated facts from one authorized original document:** For "X and Y"
  direct-action questions, separate policy chunks belonging to the *same*
  company-scoped document may jointly support the answer. A generic payment
  sentence can use its immediately preceding sentence/heading as an antecedent
  ("Transportation Expenses ... . Any incurred expenses are shouldered ...").
  An unrelated condition such as "no transportation available" does **not**
  prove who pays for transportation. Never synthesize unrelated sources or
  cross company/role boundaries.
- **Bounded fallback for unresolved short facts:** If the grounded direct-fact
  fast path was attempted but cannot cover the requested facts, one compact,
  standard local-Qwen request is allowed, capped by
  `SMART_AI_GROUNDED_DIRECT_FACT_OLLAMA_TIMEOUT_SECONDS` (default 30, clamped
  to 5–60 seconds). It does **not** execute the old 180s + 90s retry cycle.
  A timeout or model-unavailable condition produces a safe undetermined answer
  rather than a loosely related excerpt. Other kinds of Qwen requests and the
  user's existing models retain their previous configuration.
- **Reduce nonfatal Streamlit/Transformers watcher tracebacks:** When started
  with `Start_AI_HR_Assistant_With_Terminal_Log.bat`, the launcher sets
  `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none` by default. This stops automatic
  hot-reload/code watching **for the launcher only**, reducing the repeated
  optional `torchvision` import-inspection tracebacks seen in the Windows QA
  terminal. Developers may override this environment variable or launch
  Streamlit directly. `torchvision` is not added as an unnecessary dependency.
- **Hugging Face:** An unauthenticated Hub warning is independent of the
  Streamlit watcher and may still appear during the first model initialization.
  Do not force `HF_HUB_OFFLINE=1` unless the required model is fully cached;
  otherwise first-run setup would fail. Shared embedding-model reuse and both
  session/terminal log systems are preserved.

**Windows QA:** stop previous server; use the terminal-log BAT launcher; ask the
**same original five questions in one conversation**, including the overnight
accommodation question omitted from the last session. Send both
`logs/chat_assistant/.../QA_Session_*.log` and
`logs/runtime/Terminal_Session_*.log` after reviewing sensitive content. This
change has static/synthetic tests but has **not** been validated in an actual
Windows/Streamlit/Qdrant runtime on the user's PC. Once these five pass, use
previously retained Excel Focused 50, Focused 55 and Comprehensive 185 + 17 UI
checks. Preserve original Excel questions and prior ZIP checkpoints.


## v8.8.231 — Compound evidence fidelity + local-cache-first embedding warning handling

Continue from **v8.8.230** on the local Qdrant + Ollama branch. Only evidence
selection, local model-loading preference, timeout message accuracy and QA tests
have changed. No HR rules, permissions, Admin/Employee UI, model/provider choice,
Qdrant/BM25, chunker, reranker, shared embedding cache, or logging formats are
removed.

- **Real DOCX paragraph-boundary fix:** The previously failing expense question
  was already supported by Business VISA.docx but came in three source units:
  `4.1 Transportation Expenses` (heading), a transport-request instruction and
  `Any incurred expenses ... shouldered by airline`. The selection guard now
  examines up to two immediately preceding units *inside the same authorized
  chunk* for generic payer references, including a positive action governing
  the requested object. Distinct requested facets can be combined only when
  they come from the same company-scoped original document. A hotel mentioned
  merely as the destination of a transport request does **not** prove hotel
  charges, and an unrelated `no transportation available` condition does not
  count as transportation payment evidence. The answer is verbatim policy text,
  not a generated new company rule. The QA log adds `covered_facets` and
  `required_facets` for an explainable acceptance/rejection decision.
- **HF cache first:** `SMART_AI_EMBEDDING_PREFER_LOCAL_CACHE=true` (default)
  checks for an existing locally cached model snapshot and loads it directly
  when available. This avoids unnecessary Hugging Face metadata requests on
  restart, which were printing unauthenticated Hub warnings even after an
  existing model had been downloaded. On missing or incomplete cached files,
  the existing model-ID/Hugging Face loading behavior still runs; first-time
  downloads may still warn or require internet. We do not require an HF_TOKEN,
  force `HF_HUB_OFFLINE`, or hide warnings/errors. The forensic vector status
  reports `model_cache=loaded-local-cache` if the cache snapshot was used.
- **Accurate timeout wording:** An Ollama timeout no longer incorrectly claims
  a retry was attempted when a direct-fact call has retries disabled. Genuine
  Ollama failures still appear in the terminal and QA logs. The existing
  30-second bounded, no-retry direct-fact fallback is preserved when trusted
  evidence is actually incomplete. The previous Streamlit watcher suppression
  remains active under `Start_AI_HR_Assistant_With_Terminal_Log.bat`; installing
  `torchvision` is not required for this cleanup.

**Windows validation:** Stop the previous app, start with
`Start_AI_HR_Assistant_With_Terminal_Log.bat`, ask the same original **five**
questions (including the overnight hotel question) in one admin conversation,
and send the resulting scoped `QA_Session_*.log` plus process-wide
`Terminal_Session_*.log`. Check the raw logs for sensitive HR data before
sharing. Only Linux/headless automated checks are available for this package;
actual Windows output and timing must be validated on the target machine.
After these pass, continue with the retained Excel 50/55/185 Chat QA matrices and
17 UI checks.


## v8.8.232 — Automatic runtime log on direct VS Code / Streamlit launches

This release changes **logging integration only** on top of v8.8.231. The five
original travel-policy questions were confirmed 5/5 in the actual uploaded
Windows QA log (warm responses 0.52–0.56 seconds, Q3 now 0.53 seconds). The
source routing, HR rules, permissions, Qdrant, local embeddings, Ollama and
extractive answer logic remain unchanged.

**Normal integrated terminal:** With the project root as the working directory,
start the usual command from the selected Python environment:

```powershell
streamlit run app.py
```

The entry point now installs one process-wide stdout/stderr tee on its first
execution, including Python warnings and logging warnings/errors. Subsequent
Streamlit reruns and connected browser sessions reuse the same runtime log. It
remains in `logs/runtime/Terminal_Session_*.log`. It does **not** require the BAT
launcher. `QA_Session_*.log` still belongs to an individual chat conversation.

**VS Code one-click full-terminal capture:** Open the project folder in VS Code,
select the correct project Python interpreter, then use either **Terminal → Run
Task → AI HR Assistant - Run with Full Terminal Log** (also default build task),
or **Run and Debug → AI HR Assistant - Full Terminal Log (Run)**. This runs the
existing child-process logger, recording even early Streamlit startup output and
its exit code. The app detects that its stdout is already being captured and
**does not create a second log**. Debugging breakpoints in the *child* app are
not attached with this wrapper; for Python breakpoints use **Run and Debug → AI
HR Assistant - Debug Streamlit (Native Log)**, which runs the Streamlit process
directly with native capture.

**Important capture boundary:** Plain `streamlit run app.py` starts logging only
when `app.py` first executes; errors emitted *before this point* can only be
captured by the VS Code full-output task/launcher. This is a limitation of
intercepting already-running process output, not a missing log. Output sent via
low-level native OS file descriptors that bypass Python `sys.stdout/stderr` may
not be captured on a direct launch; use the full-output task when diagnosing
those issues. Direct app logging intentionally shows a `DIRECT STREAMLIT` header.

For direct runs, `.streamlit/config.toml` disables the watcher by default to
avoid hundreds of optional Transformers/torchvision inspection tracebacks; use
`--server.fileWatcherType auto` locally if you explicitly want hot reload.
The runtime log contains **all users'** console output and may contain sensitive
company/employee data, tracebacks and other secrets; review/redact before
sharing, restrict log-directory access, and set
`AI_HR_NATIVE_RUNTIME_LOG_ENABLED=false` to disable automatic direct logging
when forensic capture is not appropriate. Rotation and retention follow
`AI_HR_TERMINAL_LOG_MAX_MB` and `AI_HR_TERMINAL_LOG_RETENTION_FILES`.

**Windows validation still required:** Actual VS Code/Streamlit direct-run
logging has not been exercised on the user's PC. Test a normal VS Code terminal
run, ask a question, then verify both the latest QA and Terminal logs. After
checking that, advance to the retained Excel Focused 50/55 and Comprehensive
185+17 UI test matrices.

## v8.8.233 — Additional 45 sample-behavior QA review workflow

This checkpoint adds a **non-production QA review tool**, not new hard-coded AI answers. The 45 user-provided supplementary reference questions and expected answers are stored at `qa/reference/additional_45_sample_behavior.csv`. For exact-question comparisons, execute them in the authorized Admin/Employee chat and run `scripts/qa_reference_review.py` against the resulting unified session log. The command writes reviewable CSV and JSON summaries without accessing other tenants, external services, or the HR database. **Every matched answer requires a human policy-grounded verdict; an automated exact match is never called PASS.**

The previously identified Focused 50/55, Comprehensive 185 and 17 UI checks are unchanged. Their source Excel sheets must be supplied for row-level test execution; this version does not recreate those questions. See `qa/README.md` for examples, restrictions, and data-privacy notes.


## v8.8.236 — Workspace-only loading skeleton correction

- Screenshot-based correction to the v8.8.235 full-screen faded/white overlay: use an opaque skeleton across the **main content workspace only**, with no centered floating loading card.
- Position dynamically to the right of the visible Streamlit sidebar and below the existing pinned company header (derived from their actual rendered DOM geometry); keep both controls visible.
- Preserve previous 220ms delay, 10-second safety hide, ready signals, and reduced-motion support.
- Remove proactive full-workspace loading on ordinary form/chat submit; only sidebar navigation opens this overlay.
- **UI-only fork of v8.8.235 (which was based on v8.8.233)**. No production RAG, retrieval, answer, HR, security, database, or logging changes. First browser paint remains controlled by Streamlit, and actual Windows browser inspection is required.


### v8.8.237 — Additional Streamlit flicker coverage (UI only)

- Base: v8.8.236 (ultimately rollback v8.8.233; excludes v8.8.234 QA answer-routing changes).
- Adds detection for a briefly emptied **main content block**, even if the outer Streamlit app and sidebar remain mounted.
- Covers navigation from sidebar, quick actions, and notification destinations. Other reruns only show skeleton if there is a genuine page-content gap, not on every click or chat submission.
- Controller upgrades safely when an older controller persists in the same browser tab.
- Retains full-workspace skeleton below topbar/right of sidebar, theme stabilization, delayed navigation animation and fail-safe.
- First browser paint and individual widget-internal white repaints before the application runs are still owned by Streamlit; custom JS cannot guarantee a loader for these.
- Production HR, AI/RAG, database, and permissions are unchanged.


### v8.8.238 — Horizontal-tab loading feedback (UI only)

- Based strictly on v8.8.237 (ultimately the v8.8.233 QA rollback baseline).
- Native Streamlit horizontal tabs, including `persistent_tabs`, now get a **panel-scoped** loading skeleton when switching tabs takes longer than 125 ms. The tab buttons remain visible; the loader is positioned below the tab list and inside the main workspace.
- Project-owned horizontal segmented tab controls are also supported, without affecting ordinary segmented form controls or chat submit.
- Automatically releases on populated tab content, normal application ready signal, or a 10-second failsafe. Instant tab transitions can finish without displaying the loader. The full-workspace skeleton and sidebar/header protections from v8.8.237 remain intact.
- Pure browser UI update: no new hard-coded HR questions/answers, RAG behavior, permissions, database, or HR rule changes.
- Automated DOM simulation is not a substitute for Windows/Edge/Streamlit validation.

## v8.8.239 — Grounded evidence cohesion and new 185-case QA reference

- Branched from v8.8.238; **no changes to UI/loading, SQLite, Qdrant, HR rules or permissions**.
- Production: the extractive fast path selects multiple policy clauses only from one authorized original document; a compound query missing an explicit second fact falls through to grounded synthesis. Document RAG prompts no longer portray unsourced portal-help text as verified policy evidence. No reference question, person, date or expected answer is copied into production routing.
- `qa/reference/comprehensive_185_behavior_reference.csv` holds 185 user-supplied *evaluation-only* cases (113 Admin, 38 Employee, 34 shared). These describe seeded QA data; they **do not create or verify** live records. Do not index this CSV as RAG data.
- `scripts/qa_reference_review.py` isolates results by portal, company and employee; tests with an account login require an explicit private login→user-id mapping via `--account-map` (JSON), and results from multiple user scopes must be reviewed separately. It NEVER auto-marks PASS.
- Do not interpret automated unit tests as evidence that 185 live Windows QA questions pass; they require real seeded data and authorized Admin/Employee tests.


## v8.8.240 — company-scoped RAG quality / diagnostics

- **Phase 1:** generic output-to-question topical alignment rejects unrelated deterministic records before the verified policy retriever; stable BM25 and E5 indexing now use real source section headings. No question-specific QA answer rules.
- **Phase 2:** distinct numbered/bulleted policy sections are not micro-merged; focused excerpts keep contiguous list items; conditional reranking uses a single cached local CrossEncoder, safely falls back to hybrid ranking when no model is cached. No surprise downloads by the app.
- **Phase 3:** `scripts/rag_ab_benchmark.py` evaluates the same authorized company document snapshot using isolated temporary Qdrant indexes and external question CSV, optionally comparing already-cached embeddings. It reports *source recall proxy*, not answer correctness.
- Default reranker model `BAAI/bge-reranker-base` is **not downloaded automatically**. To use, cache it yourself after license/review, or set `SMART_AI_RERANKER_MODEL` to an existing local path. The default `intfloat/multilingual-e5-small` remains unchanged.
- The production project never contains the external 45/185 expected answers, and UI loading changes are on hold. A live Windows/Edge/SQLite/Ollama retest is still required; source code unit tests alone do not establish answer accuracy.

Example optional candidate recall diagnostic after placing `Terminal_QA_Test` in the project root:

```powershell
python scripts/rag_ab_benchmark.py --reference Terminal_QA_Test/references/policy_45.csv --limit 45
```

`--models <cached-second-model>` adds an isolated A/B test. Company login is requested. No admin bypass.


## v8.8.242 — Source-route, subsection evidence, and diagnostic QA refinement

This version is a targeted correction built strictly on v8.8.240; it does not change Attendance,
Leave, Overtime, user access rights, any portal layout, Qdrant storage settings, or the default
embedding/LLM model.

- Generic record-entity guard prevents a policy-rule question from being answered by an
  unrelated live disciplinary/violation record. Real case/code and employee lookups remain
  controlled by the original authenticated company/role path.
- Extractive policy answers reject heading-only preambles, unsupported requested time/numeric
  properties, and obviously incomplete answer-shape evidence instead of inventing a complete rule.
- A bounded same-file subsection recovery pass can try other already-authorized policy chunks
  before concluding that a source-bearing question has no evidence. Recovery never opens other
  companies, roles, or unrelated policy files.
- Binary answers with negative conclusions and explicitly affirmative/exempting explanations
  abstain rather than confidently presenting both claims.
- Verified policy metadata from retrieved policy chunks is available for source display even
  when the deterministic answer originally contained no policy citation; only actual policy IDs
  qualify, not general portal help text.
- Terminal traces now record per-candidate body-vs-heading relevance diagnostics.
- `scripts/rag_ab_benchmark.py` supports `--reranker compare` (default), `--reranker off/on`,
  optional external `--source-map` to correct reference filename labels, and `--passage-map`
  with `id,evidence_quote` to measure exact supporting-passage recall. Without externally
  verified verbatim supporting snippets the report prints `UNSPECIFIED` for true passage recall;
  the body-overlap coverage remains a lexical *proxy*, not an answer-accuracy grade.
- Benchmark remains account/company-scoped and isolates experimental embedding collections
  in temporary directories. Cached local CrossEncoder required; no implicit downloads.

**Windows QA commands (from project root):**

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin
python scripts/rag_ab_benchmark.py --reference Terminal_QA_Test/references/policy_45.csv --limit 45 --reranker compare
```

The external `Terminal_QA_Test` folder is retained separately and is NOT included in this
production project ZIP. The newer script can compare reranker modes only when the configured
CrossEncoder is present in the local model cache; otherwise `SKIPPED` is an expected diagnostic.
The model/embedding benchmark is not a substitute for checking final 45-question answers.

**Validation:** static/code regression only. Actual 45-question Windows/Ollama accuracy and
latency results remain unknown until the new version is run on the user's live environment.
No QA question or ground-truth answer is hard-coded into production answer routing or prompts.

For the user-provided 45-question reference with the four Office-related file-label
mismatches, the **test-only** source map is `qa/reference/office_policy_source_label_corrections.csv`.
This file contains only QA IDs and corrected source filenames—not questions, answers,
or production routing rules. To use it during evaluation:

```powershell
python scripts/rag_ab_benchmark.py --reference Terminal_QA_Test/references/policy_45.csv --source-map qa/reference/office_policy_source_label_corrections.csv --limit 45 --reranker compare
```

For verified passage recall, supply a separate externally reviewed CSV with columns
`id,evidence_quote`, using **verbatim authorized policy quotations**, then add
`--passage-map path/to/quotes.csv`. Without such quotes only a lexical body-overlap
proxy can be calculated, and it is NOT a semantic correctness measure.


## v8.8.242 — Groq / Local / Hybrid switch (no UI)

You can keep the current v8.8.241 running while testing this separate release.
Provider selection changes **only generation requests that reach the optional LLM**; it does not replace the deterministic HR answers, local Qdrant, embeddings, CrossEncoder, policy scope, company/role access, or the extractive fast path. Consequently, questions answered entirely by existing grounded/deterministic paths do not need to call either model.

Edit your **existing private `.env`** in the project root (do not overwrite it with the sample):

```dotenv
# Change this ONE value to select behavior: local / groq / hybrid
SMART_AI_LLM_MODE=local

# Groq only if cloud use is approved by your company
SMART_AI_GROQ_API_KEY=replace_with_your_actual_key
SMART_AI_GROQ_MODEL=qwen/qwen3.8-27b
SMART_AI_GROQ_TIMEOUT_SECONDS=25

# Existing local Ollama model/settings remain unchanged
SMART_AI_OLLAMA_BASE_URL=http://localhost:11434
SMART_AI_OLLAMA_MODEL=qwen2.5:7b
```

| `SMART_AI_LLM_MODE` | Behavior |
| --- | --- |
| `local` (**default**) | Ollama only; does not contact Groq, even if Groq API key is present. |
| `groq` | Groq only; never calls Ollama, even if Groq is unavailable. The system keeps only any supported deterministic answer. |
| `hybrid` | Groq is attempted first; on missing key, timeout, HTTP error, network error, or empty answer it falls back to the existing local Ollama generation path. Does **not** run both in parallel. |

`GROQ_API_KEY=` (without prefix) is accepted as an alternative to `SMART_AI_GROQ_API_KEY=`, but prefer the prefixed setting. API key is loaded as a secret; it is neither displayed in settings `repr` nor written to provider traces. Restart the Streamlit process (and restart the Terminal QA runner) after changing `.env`, since application settings are cached in each Python process. Only change `.env` for version v8.8.242, not v8.8.241.

**Cloud privacy notice:** Groq-only and Hybrid transmit the question and **authorized company evidence included in the grounded prompt** to an external provider for inference. Confirm the company's HR data handling/contractual requirements before opting into cloud use. This option does not alter local data indexing, but the generated cloud requests do leave the local PC. Do not place your real Groq API key in screenshots or logs shared publicly.

**Model availability:** `qwen/qwen3.8-27b` is listed as a Groq Preview model in October 2026. Check account model permissions, rate limits and pricing. If unavailable, change `SMART_AI_GROQ_MODEL=` to an active model ID accessible to your account. No SDK installation is required; the integration uses Python's standard-library HTTPS client.

**Quick offline smoke tests (no cloud key needed):**

```powershell
python -m pytest -q tests/test_v88242_llm_mode_switch.py
```

**Real QA tests:** Configure your local `.env`, then run the existing independent suite as before:

```powershell
python Terminal_QA_Test/run_terminal_qa.py --suite 45 --portal admin --limit 5
```

Full `.txt` case logs remain in `Terminal_QA_Test/results`; provider attempts and fallback details remain in the existing per-session trace logs under `logs/chat_assistant` (or `Terminal_QA_Test/results/engine_traces` if redirected by the runner). For clean comparisons, run 45 questions separately under `local`, `groq`, and `hybrid` and keep the three result files. The 185-question account-specific suite remains on hold. Cloud provider integration has not been validated against a real Groq account/API key in this release; mocks validate protocol and failover, and Windows installation must be checked on your PC.


## v8.8.243 — Local grounded answer integrity (QA track)

- Based on v8.8.242; LLM mode selection (local/groq/hybrid) retained. For the active QA cycle use `SMART_AI_LLM_MODE=local`. No new Groq network access in local mode.
- Contradictory YES/NO-prefixed local model responses may trigger **one** bounded local evidence-only retry (`SMART_AI_BINARY_REPAIR_ENABLED`, `SMART_AI_BINARY_REPAIR_TIMEOUT_SECONDS`); timeout/error/uncertainty still abstains.
- For direct company policy consequence/eligibility/procedure questions, preserves one second directly supported, already authorized policy source if a high-volume file dominates the final evidence. Not forced when no direct evidence or company/role does not match.
- See `QA_45_Retest_Guide_v8.8.243.md` and evaluation-only `qa/reference/V88243_45_Question_Retest_Matrix.csv` for full 45-question regression plan. The removable Terminal_QA_Test runner is deliberately not bundled in production.
- No source-model answer keys or QA expected results in production logic; no changes to SQLite schema, Qdrant index definitions, local embeddings, reranker, UI, HR rules, or permissions.
- Unit/regression tests do **not** certify runtime Ollama accuracy. Actual 45-question Windows QA is still necessary.

## v8.8.248 — Answer quality hardening (2026-10-15)

This release improves generic RAG answer-cue validation, complete eligibility extraction, source attribution and bounded direct-fact prompt context. `SMART_AI_OLLAMA_TIMEOUT_SECONDS` remains at its existing 180-second default; the special direct-fact budget remains 30 seconds by default. See `RELEASE_NOTES_v8.8.248.md` and `QA_Focused_Retest_v8.8.248.md`. The 45-question Windows accuracy benchmark has **not** yet been rerun on this build.
