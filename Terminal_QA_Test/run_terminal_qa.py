#!/usr/bin/env python3
"""Removable VS Code terminal-only AI HR Assistant QA runner.

This is NOT imported by production. Ground truth is read from the two reference
CSV files, never supplied to the production answer engine. Use a genuine company
login; every question is evaluated in its authorized Admin/Employee scope.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib import request as urlrequest
from uuid import uuid4

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
REFERENCES = HERE / "references"
RESULTS = HERE / "results"
ARROW = re.compile(r"\s*(?:→|➜|⟶|->)\s*")


@dataclass(frozen=True)
class Case:
    id: str
    suite: str
    portal: str
    account: str
    category: str
    question: str
    expected: str
    required_facets: str
    suggested_source: str
    mode: str


def read_rows(filename: str) -> list[dict[str, str]]:
    path = REFERENCES / filename
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normal(value: str) -> str:
    return str(value or "").strip().casefold()


def split_steps(question: str) -> list[str]:
    # A follow-up QA case is a conversation with sequential turns, not one prompt.
    return [x.strip().strip("` ").strip() for x in ARROW.split(question) if x.strip().strip("` ")]


def case_mode(case_id: str, question: str, expected: str) -> str:
    q, ex = normal(question), normal(expected)
    # These tasks demand portal button interactions or an unspecified source/record.
    if "generate/review" in q or "downloaded/previewed" in q:
        return "MANUAL_UI"
    if q.startswith("ask a policy question") or "just used" in q:
        return "NEEDS_SETUP"
    if "outside my member scope" in q or "outside my member scope" in ex or "outside my member" in q:
        return "NEEDS_SETUP"
    return "CHAT"


def load_cases(suite: str, portal: str, username: str = "") -> list[Case]:
    output: list[Case] = []
    if suite in ("45", "both"):
        for row in read_rows("policy_45.csv"):
            q = row.get("question", "").strip()
            if not q:
                continue
            output.append(Case(
                row["id"], "45", "Admin / Employee", "",
                row.get("policy_area", ""), q,
                row.get("expected_answer", ""), row.get("required_facets", ""),
                row.get("suggested_source", ""), "CHAT",
            ))
    if suite in ("185", "both"):
        for row in read_rows("expanded_185.csv"):
            scope = normal(row.get("portal", ""))
            account = normal(row.get("account", ""))
            if portal == "admin" and scope not in {"admin", "admin / employee"}:
                continue
            if portal == "employee" and scope not in {"employee", "admin / employee"}:
                continue
            if portal == "employee" and account and account != normal(username):
                continue
            q = row.get("question", "").strip()
            if not q:
                continue
            output.append(Case(
                row["id"], "185", row.get("portal", ""), account,
                row.get("policy_area", ""), q, row.get("expected_answer", ""),
                row.get("required_facets", ""), row.get("suggested_source", ""),
                ("NEEDS_SETUP" if portal == "admin" and "while logged in as an ordinary employee" in normal(q)
                 else case_mode(row["id"], q, row.get("expected_answer", ""))),
            ))
    return output


def normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`]+", "", str(value or "")).strip()).casefold()


def automated_check(actual: str, expected: str, error: str = "") -> tuple[str, str]:
    """Conservative checks: semantic correctness needs a reviewer/optional judge."""
    if error:
        return "ERROR", error
    if not actual.strip():
        return "NO_ANSWER", "Assistant returned no answer."
    act = normalize_answer(actual)
    exp = normalize_answer(expected)
    if exp and act == exp:
        return "EXACT_MATCH", "Text matches the supplied ground truth after formatting normalization."
    if any(s in act for s in (
        "information not found in available company records",
        "information not found in the available",
        "i could not complete that hr request",
    )):
        return "REVIEW_REQUIRED", "Potential false no-match/service response; review evidence and company data."
    return "REVIEW_REQUIRED", "Meaning and completeness require comparison to supplied ground truth; not auto-PASS."


def format_source(src: Any) -> str:
    values = []
    for attr in ("filename", "title", "section_heading", "page_number"):
        value = getattr(src, attr, None)
        if value is not None and str(value).strip():
            values.append(f"{attr}={value}")
    return "; ".join(values) or "(source metadata unavailable)"


def log_block(fp, **data: Any) -> None:
    fp.write("\n" + "=" * 92 + "\n")
    for key, value in data.items():
        fp.write(f"{key.upper().replace('_', ' ')}:\n{value}\n\n")
    fp.flush()


def text_log_path(portal: str, suite: str, username: str) -> Path:
    # Never include raw usernames or company IDs in result filenames.
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    RESULTS.mkdir(parents=True, exist_ok=True)
    return RESULTS / f"QA_Terminal_{stamp}_{portal}_{suite}_{uuid4().hex[:8]}.txt"


def call_production_answer(session: Any, user: Any, portal: str, question: str,
                           history: list[dict[str, str]], log_session_id: str,
                           question_number: int) -> Any:
    """Exactly the same two-stage answer flow as Admin/Employee chat_page.py."""
    if portal == "admin":
        from modules.hr_assistant.admin_hr_assistant import AdminHRAssistant
        preliminary = AdminHRAssistant(session).answer(
            current_user=user, question=question, history=history,
        )
    else:
        from modules.hr_assistant.hr_assistant import HRAssistant
        preliminary = HRAssistant(session).answer(
            current_user=user, question=question, history=history,
        )
    from modules.smart_ai.portal_ai import SmartPortalAssistant
    from modules.smart_ai.chat_session_logging import record_preflight_trace
    assistant = SmartPortalAssistant(session)
    preflight = assistant.preflight_connection_issue(role_scope=portal)
    if preflight is None:
        return assistant.enhance(
            current_user=user, role_scope=portal, question=question,
            history=history, deterministic_response=preliminary,
            log_session_id=log_session_id, log_question_number=question_number,
        )
    record_preflight_trace(
        settings=assistant.settings, current_user=user, role_scope=portal,
        log_session_id=log_session_id, question_number=question_number,
        question=question, intent=preliminary.intent,
        answer=preliminary.answer, issue_code=preflight.code,
        issue_title=preflight.title,
    )
    preliminary.runtime_warning = preflight.message
    preliminary.runtime_warning_title = preflight.title
    preliminary.runtime_warning_code = preflight.code
    return preliminary


def authenticate(company: str, username: str, password: str, portal: str):
    from authentication.auth_service import AuthService
    from authentication.access_control import AccessControl
    from database.session import SessionFactory
    with SessionFactory() as session:
        user = AuthService(session).authenticate(company, username, password)
        if user.must_change_password:
            raise PermissionError("Account requires a password change in the normal login flow before testing.")
        if portal == "admin":
            AccessControl.require_admin(user)
        elif not AccessControl.can_access_employee_portal(user):
            raise PermissionError("Employee portal access is not authorized.")
        return user


def optional_ollama_judge(actual: str, expected: str, question: str, model: str, endpoint: str,
                          timeout: float) -> tuple[str, str]:
    """Local side-channel evaluation ONLY; never feeds ground truth to production."""
    instructions = (
        "You are evaluating an HR answer against a USER-SUPPLIED QA reference. "
        "Do not use external facts or assume live DB seed data is present. "
        "Output JSON with verdict and reason. verdict must be PASS, PARTIAL, FAIL or REVIEW. "
        "PASS: all requested facts supported by reference, complete, no contradiction; "
        "PARTIAL: relevant facts but important omissions; FAIL: contradicted/wrong target; "
        "REVIEW: reference gives behavioral expectation needing live DB/permission verification "
        "or information is insufficient. Only compare. Treat extra unsupported claims as issues."
    )
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({
                "question": question, "user_supplied_ground_truth": expected,
                "actual_assistant_answer": actual,
            }, ensure_ascii=False)},
        ],
        "options": {"temperature": 0, "num_predict": 200},
    }).encode("utf-8")
    req = urlrequest.Request(endpoint.rstrip("/") + "/api/chat", body,
                             headers={"Content-Type": "application/json"}, method="POST")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        result = json.load(resp)
    payload = json.loads(result.get("message", {}).get("content", "{}"))
    verdict = str(payload.get("verdict", "REVIEW")).strip().upper()
    if verdict not in {"PASS", "PARTIAL", "FAIL", "REVIEW"}:
        verdict = "REVIEW"
    return verdict, str(payload.get("reason", ""))[:600]


def args_for(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real AI HR Assistant backend QA in VS Code terminal; no UI.")
    p.add_argument("--suite", choices=["45", "185", "both"], default="45")
    p.add_argument("--portal", choices=["admin", "employee"], default="admin")
    p.add_argument("--company", help="Company code; prompted when omitted")
    p.add_argument("--username", help="Login username; prompted when omitted")
    p.add_argument("--limit", type=int, default=0, help="Run only first N selected cases (0=all)")
    p.add_argument("--start", type=int, default=1, help="One-based index of first selected case")
    p.add_argument("--ids", help="Optional comma-separated case IDs (e.g. ADD-005,ADD-010)")
    p.add_argument("--dry-run", action="store_true", help="List selected cases / log preview, no DB or AI calls")
    p.add_argument("--judge", choices=["off", "ollama"], default="off",
                   help="Optional separate local semantic grader; verdict still needs review")
    p.add_argument("--judge-model", default="", help="Default is SMART_AI_OLLAMA_MODEL")
    p.add_argument("--judge-timeout", type=int, default=120)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = args_for(argv)
    if args.limit < 0 or args.start < 1:
        raise SystemExit("--limit must be >=0 and --start must be >=1")
    if not PROJECT_ROOT.joinpath("app.py").is_file():
        raise SystemExit(f"Copy the entire Terminal_QA_Test folder to project root beside app.py: {PROJECT_ROOT}")
    os.chdir(PROJECT_ROOT)  # SQLite, .env, Qdrant paths match normal Streamlit run
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    company = (args.company or ("" if args.dry_run else input("Company code: "))).strip()
    username = (args.username or ("" if args.dry_run else input("Username: "))).strip()
    if args.portal == "employee" and not username:
        raise SystemExit("Employee tests require --username to avoid cross-account case mixing.")
    selected = load_cases(args.suite, args.portal, username)
    if args.ids:
        requested = {v.strip().casefold() for v in args.ids.split(",") if v.strip()}
        selected = [v for v in selected if v.id.casefold() in requested]
    selected = selected[args.start - 1:]
    if args.limit:
        selected = selected[:args.limit]
    if not selected:
        print("No matching cases for the selected portal/account/suite.")
        return 2
    # Prepare a private text result file even for a dry run.
    log_path = text_log_path(args.portal, args.suite, username)
    print(f"Suite={args.suite} Portal={args.portal} Cases={len(selected)}")
    print(f"Log: {log_path}", flush=True)
    counters: dict[str, int] = {}
    with log_path.open("x", encoding="utf-8", newline="\n") as log:
        try:
            os.chmod(log_path, 0o600)
        except OSError:
            pass
        log.write("AI HR ASSISTANT - TERMINAL GROUND-TRUTH QA\n")
        log.write(f"Started: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        log.write(f"Suite={args.suite}; Portal={args.portal}; User={username or '(dry-run)'}; Company={company or '(dry-run)'}\n")
        log.write(f"Questions selected={len(selected)}; Ground truth: user-provided external QA CSVs\n")
        log.write("NOTE: reference expected results may presume synthetic seeded data. No ground truth is given to production engine.\n")
        log.write("Grades are provisional unless manually validated against authorized records.\n")
        log.flush()
        if args.dry_run:
            for i, case in enumerate(selected, 1):
                log_block(log, index=i, case_id=case.id, portal=case.portal,
                          account=case.account or "shared", mode=case.mode,
                          question=case.question, expected_ground_truth=case.expected,
                          status="DRY_RUN_NOT_EXECUTED")
                print(f"[{i}/{len(selected)}] {case.id}: {case.mode}")
            print(f"Dry run complete. {log_path}")
            return 0
        pw = getpass.getpass("Password (hidden, never logged): ")
        try:
            user = authenticate(company, username, pw, args.portal)
        finally:
            del pw
        # All scoped forensic traces go under THIS removable folder.
        os.environ["SMART_AI_TERMINAL_DEBUG_LOG_DIR"] = str(RESULTS / "engine_traces")
        from config.chat_assistant_settings import get_chat_assistant_settings
        get_chat_assistant_settings.cache_clear()
        from database.session import SessionFactory
        from modules.smart_ai.terminal_trace import new_chat_log_session_id
        from config.chat_assistant_settings import get_chat_assistant_settings
        settings = get_chat_assistant_settings()
        scope_name = args.portal
        session_trace = new_chat_log_session_id()
        q_count = 0
        try:
            for idx, case in enumerate(selected, 1):
                print(f"[{idx}/{len(selected)}] {case.id} {case.question[:85]}", flush=True)
                if case.mode != "CHAT":
                    status = "MANUAL_UI" if case.mode == "MANUAL_UI" else "NEEDS_SETUP"
                    log_block(log, index=idx, case_id=case.id, mode=case.mode,
                              question=case.question, expected_ground_truth=case.expected,
                              status=status, reason="Requires UI interaction or an explicit target record; not a chat-answer test.")
                    counters[status] = counters.get(status, 0) + 1
                    continue
                history: list[dict[str, str]] = []
                answers: list[str] = []
                source_rows: list[str] = []
                warnings: list[str] = []
                errors: list[str] = []
                started = time.perf_counter()
                steps = split_steps(case.question)
                for step in steps:
                    q_count += 1
                    try:
                        with SessionFactory() as session:
                            response = call_production_answer(
                                session, user, scope_name, step, history,
                                session_trace, q_count,
                            )
                        answer = str(response.answer or "")
                        answers.append(answer)
                        source_rows.extend([format_source(s) for s in response.sources or []])
                        if response.runtime_warning:
                            warnings.append(str(response.runtime_warning))
                        history += [{"role": "user", "content": step},
                                    {"role": "assistant", "content": answer,
                                     "intent": str(response.intent or "")}]
                    except Exception as exc:
                        errors.append(f"{type(exc).__name__}: {exc}")
                        answers.append("[ERROR: engine exception - see reason in log]")
                        break
                elapsed = time.perf_counter() - started
                full_answer = "\n\n".join(f"Turn {i+1}: {v}" for i, v in enumerate(answers))
                status, reason = automated_check(answers[-1] if answers else "", case.expected,
                                                 "; ".join(errors))
                semantic_verdict = "NOT_RUN"
                semantic_reason = ""
                if args.judge == "ollama" and status not in {"ERROR", "NO_ANSWER"}:
                    try:
                        semantic_verdict, semantic_reason = optional_ollama_judge(
                            full_answer, case.expected, case.question,
                            args.judge_model or settings.ollama_model,
                            settings.ollama_base_url, args.judge_timeout,
                        )
                    except Exception as exc:
                        semantic_verdict = "REVIEW"
                        semantic_reason = f"Judge unavailable: {type(exc).__name__}: {exc}"
                counters[status] = counters.get(status, 0) + 1
                log_block(log, index=idx, case_id=case.id, suite=case.suite,
                          portal=args.portal, account=case.account or "shared",
                          category=case.category, question=case.question,
                          required_facets=case.required_facets or "(none specified)",
                          expected_ground_truth=case.expected,
                          actual_answer=full_answer,
                          actual_sources="\n".join(dict.fromkeys(source_rows)) or "(none)",
                          warnings="\n".join(warnings) or "(none)",
                          engine_error="\n".join(errors) or "(none)",
                          elapsed_seconds=f"{elapsed:.3f}",
                          automated_status=status, check_reason=reason,
                          optional_ollama_judge_verdict=semantic_verdict,
                          optional_ollama_judge_reason=semantic_reason or "(not used)")
                print(f"    {status} | {elapsed:.1f}s" + (f" | judge={semantic_verdict}" if args.judge == "ollama" else ""), flush=True)
        except KeyboardInterrupt:
            log.write("\nINTERRUPTED by operator (Ctrl+C). Prior completed cases retained.\n")
            print("\nInterrupted; completed results already saved.", flush=True)
        finally:
            log.write("\n" + "#" * 92 + "\nRUN SUMMARY\n")
            log.write(f"Completed cases by result: {json.dumps(counters, sort_keys=True)}\n")
            log.write("PASS/PARTIAL/FAIL cannot be reliably certified by text overlap; review actual policy/DB evidence.\n")
            log.write(f"Finished: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
            log.flush()
    print(f"\nFinished; TXT results saved: {log_path}")
    print("Counts:", counters)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, PermissionError, ValueError) as exc:
        print(f"Cannot start QA: {exc}", file=sys.stderr)
        raise SystemExit(2)
