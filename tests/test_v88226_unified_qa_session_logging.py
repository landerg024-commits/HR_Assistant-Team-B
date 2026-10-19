"""Regression tests for v8.8.226 multi-user, per-conversation QA logs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import warnings

from modules.smart_ai.chat_session_logging import record_preflight_trace
from modules.smart_ai.terminal_trace import TerminalChatTrace, new_chat_log_session_id


def _settings(tmp_path: Path, **extra):
    return SimpleNamespace(
        terminal_debug_enabled=True,
        terminal_debug_log_enabled=True,
        terminal_debug_session_logging_enabled=True,
        terminal_debug_log_dir=str(tmp_path),
        **extra,
    )


def _write_question(settings, session_id, company_id, user_id, role_scope, number, text):
    trace = TerminalChatTrace.create(
        settings,
        session_id=session_id,
        company_id=company_id,
        user_id=user_id,
        role_scope=role_scope,
        question_number=number,
    )
    trace.start(role_scope=role_scope, intent="policy_fallback", question=text)
    trace.line("CHUNK STAGE — BM25", f"evidence for {text}")
    trace.answer("FINAL CHAT ANSWER", f"ANSWER FOR {text}")
    trace.finish("grounded-extractive-answer")
    return trace


def test_session_appends_three_complete_question_blocks_to_one_file(tmp_path):
    settings = _settings(tmp_path)
    key = new_chat_log_session_id()
    traces = [
        _write_question(settings, key, 1, 11, "admin", n, f"question-{n}")
        for n in range(1, 4)
    ]
    assert len({trace.log_path for trace in traces}) == 1
    path = Path(traces[0].log_path)
    assert list(tmp_path.rglob("*.log")) == [path]
    body = path.read_text(encoding="utf-8")
    assert body.count("AI HR ASSISTANT — UNIFIED QA SESSION LOG") == 1
    assert body.count("AI HR ASSISTANT — RETRIEVAL DEBUG") == 3
    assert body.count("[1] QUESTION") == 3
    assert body.count("FINAL CHAT ANSWER") == 3
    assert body.count("SESSION CHECKPOINT") == 3
    for n, trace in enumerate(traces, 1):
        assert f"SESSION QUESTION #{n}" in body
        assert f"question-{n}" in body
        assert f"trace={trace.trace_id}" in body
    assert body.index("question-1") < body.index("question-2") < body.index("question-3")
    assert "company_1" not in str(path)
    assert "user_11" not in str(path)


def test_company_user_portal_and_new_session_are_isolated(tmp_path):
    settings = _settings(tmp_path)
    key = new_chat_log_session_id()
    base = _write_question(settings, key, 1, 1, "admin", 1, "admin-one")
    others = [
        _write_question(settings, key, 2, 1, "admin", 1, "company-two"),
        _write_question(settings, key, 1, 2, "admin", 1, "user-two"),
        _write_question(settings, key, 1, 1, "employee", 1, "employee-portal"),
        _write_question(settings, new_chat_log_session_id(), 1, 1, "admin", 1, "new-chat"),
    ]
    paths = [Path(t.log_path) for t in [base, *others]]
    assert len(set(paths)) == 5
    assert all(path.exists() for path in paths)
    for path, expected in zip(paths, ["admin-one", "company-two", "user-two", "employee-portal", "new-chat"]):
        body = path.read_text(encoding="utf-8")
        assert expected in body
        assert all(other not in body for other in ["admin-one", "company-two", "user-two", "employee-portal", "new-chat"] if other != expected)


def test_concurrent_same_session_appends_do_not_mix_trace_blocks(tmp_path):
    settings = _settings(tmp_path)
    key = new_chat_log_session_id()
    with ThreadPoolExecutor(max_workers=12) as pool:
        traces = list(pool.map(
            lambda n: _write_question(settings, key, 1, 1, "employee", n, f"unique_question_{n:02}"),
            range(1, 31),
        ))
    assert len({trace.log_path for trace in traces}) == 1
    body = Path(traces[0].log_path).read_text(encoding="utf-8")
    assert body.count("AI HR ASSISTANT — RETRIEVAL DEBUG") == 30
    assert body.count("SESSION CHECKPOINT") == 30
    assert body.count("AI HR ASSISTANT — UNIFIED QA SESSION LOG") == 1
    for n in range(1, 31):
        assert body.count(f"SESSION QUESTION #{n} ") == 1
        assert body.count(f"ANSWER FOR unique_question_{n:02}") == 1
        assert body.count(f"trace={traces[n-1].trace_id}") == 1
    # A complete trace ends with its checkpoint before another starts.
    chunks = body.split("AI HR ASSISTANT — RETRIEVAL DEBUG")[1:]
    assert all("SESSION CHECKPOINT" in chunk for chunk in chunks)


def test_preflight_is_logged_in_same_session_without_sensitive_message(tmp_path):
    settings = _settings(tmp_path)
    key = new_chat_log_session_id()
    first = _write_question(settings, key, 4, 15, "admin", 1, "first normal question")
    record_preflight_trace(
        settings=settings,
        current_user=SimpleNamespace(company_id=4, user_id=15),
        role_scope="admin", log_session_id=key, question_number=2,
        question="second question", intent="not_found",
        answer="Connection unavailable", issue_code="NETWORK", issue_title="Offline",
    )
    body = Path(first.log_path).read_text(encoding="utf-8")
    assert body.count("SESSION CHECKPOINT") == 2
    assert "first normal question" in body and "second question" in body
    assert "PRELIGHT" not in body
    assert "AI PATH — PREFLIGHT" in body
    assert "preflight-unavailable" in body


def test_legacy_trace_still_writes_one_file_per_request(tmp_path):
    settings = _settings(tmp_path)
    a = TerminalChatTrace.create(settings)
    b = TerminalChatTrace.create(settings)
    assert a.log_path != b.log_path
    for trace in [a, b]:
        trace.start(role_scope="admin", intent="policy", question="test")
        trace.finish("complete")
    assert len(list(tmp_path.glob("chat_trace_*.log"))) == 2


def test_disabled_logging_does_not_create_files(tmp_path):
    settings = SimpleNamespace(
        terminal_debug_enabled=False,
        terminal_debug_log_enabled=True,
        terminal_debug_session_logging_enabled=True,
        terminal_debug_log_dir=str(tmp_path),
    )
    trace = _write_question(settings, new_chat_log_session_id(), 1, 2, "admin", 1, "silent")
    assert trace.log_path is None
    assert not list(tmp_path.rglob("*.log"))


def test_code_wires_same_session_into_both_portals():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "ui/pages/admin/chat_page.py", root / "ui/pages/user/chat_page.py"):
        page = path.read_text(encoding="utf-8")
        assert 'log_session_id=log_session_id' in page
        assert 'record_preflight_trace(' in page
        assert 'st.session_state[log_session_key] = new_chat_log_session_id()' in page
        assert 'log_question_number=' in page


def test_smart_portal_assistant_enhance_appends_across_real_call_boundary(tmp_path):
    from modules.hr_assistant.hr_assistant import HRAssistantResponse
    from modules.smart_ai.portal_ai import SmartPortalAssistant

    assistant = SmartPortalAssistant(None)
    assistant.settings = _settings(tmp_path)
    assistant.settings.enabled = False  # no network/model/DB needed
    key = new_chat_log_session_id()
    current_user = SimpleNamespace(company_id=9, user_id=17)
    for n in (1, 2):
        response = assistant.enhance(
            current_user=current_user,
            role_scope="admin",
            question=f"Example HR query {n}",
            history=[],
            deterministic_response=HRAssistantResponse(
                answer="Information not found in company knowledge base.",
                intent="not_found",
            ),
            log_session_id=key,
            log_question_number=n,
        )
        assert response.answer
    logs = list(tmp_path.rglob("QA_Session_*.log"))
    assert len(logs) == 1
    body = logs[0].read_text(encoding="utf-8")
    assert "Example HR query 1" in body
    assert "Example HR query 2" in body
    assert body.count("SESSION CHECKPOINT") == 2
