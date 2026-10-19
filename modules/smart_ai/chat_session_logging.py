"""Best-effort preflight diagnostics for unified QA session logs.

The regular trace runs within enhance(); connection preflight can skip that
call. Capture that question with the same identity-scoped session trace.
"""
from __future__ import annotations

from modules.smart_ai.terminal_trace import TerminalChatTrace


def record_preflight_trace(
    *, settings, current_user, role_scope: str, log_session_id: str | None,
    question_number: int, question: str, intent: str, answer: str,
    issue_code: str = "", issue_title: str = "",
) -> None:
    trace = TerminalChatTrace.create(
        settings, session_id=log_session_id,
        company_id=getattr(current_user, "company_id", None),
        user_id=getattr(current_user, "user_id", None),
        role_scope=role_scope, question_number=question_number,
    )
    trace.start(role_scope=role_scope, intent=intent, question=question)
    trace.line(
        "AI PATH — PREFLIGHT",
        "Enhancement skipped because a required runtime connection was unavailable.",
    )
    trace.runtime_issue(
        code=issue_code, title=issue_title,
        message="Preflight connection unavailable",
    )
    trace.answer_selection(selected="deterministic/router", reason="preflight-unavailable")
    trace.answer("FINAL CHAT ANSWER", answer)
    trace.finish("preflight-unavailable")
