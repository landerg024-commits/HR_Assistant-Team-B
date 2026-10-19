"""Local, company-scoped AI enhancement for both portal chat assistants.

Architecture:
- Existing deterministic assistants remain authoritative for live HR records.
- Published policy sections and portal help text are retrieved through hybrid
  BM25 + optional Qdrant vector search.
- Optional CrossEncoder reranking improves the final candidate order.
- Configurable Groq/Ollama generation performs only grounded answer synthesis.
- Every dependency is lazy-loaded so the portal keeps working when the local
  AI runtime or index dependencies are not installed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import re
import socket
import threading
import time
import uuid
from typing import Iterable
from urllib import request, error
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from authentication.current_user import AuthenticatedUser
from config.chat_assistant_settings import get_chat_assistant_settings
from config.settings import get_settings
from modules.smart_ai.groq_llm import GroqClient
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.hr_assistant.query_semantics import (
    analyze_query_semantics,
    validate_deterministic_answer_shape,
)
from modules.smart_ai.terminal_trace import TerminalChatTrace
from modules.smart_ai.prompts.hr_assistant_prompt import (
    NOT_FOUND_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    UNDETERMINED_ANSWER,
    build_hr_assistant_prompt,
)
from models.announcement import Announcement
from models.attendance_record import AttendanceRecord
from models.company import Company
from models.company_form import CompanyForm
from models.company_form_submission import CompanyFormSubmission
from models.employee import Employee
from models.employee_training import EmployeeTraining
from models.event_reminder import EventReminder
from models.leave_balance import LeaveBalance
from models.leave_request import LeaveRequest
from models.onboarding import CompanyBenefit
from models.overtime_request import OvertimeRequest
from models.user import User
from repositories.policy_section_repository import PolicySectionRepository
from repositories.policy_repository import PolicyRepository
from services.policy_violation_service import PolicyViolationService
from services.policy_service import PolicySource
from services.company_form_knowledge_service import CompanyFormKnowledgeExtractor
from services.runtime_connection_service import (
    RuntimeServiceModelUnavailableError,
    RuntimeServiceResponseError,
    RuntimeServiceTimeoutError,
    RuntimeServiceUnavailableError,
    classify_runtime_connection_issue,
    log_runtime_connection_issue,
)



@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """One role-safe portal or policy knowledge unit."""

    document_id: str
    text: str
    title: str
    source_type: str
    company_id: int
    role_scope: str
    metadata: dict[str, str | int | None]


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    """One hybrid-search result."""

    document: KnowledgeDocument
    score: float


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    """One structure-aware file chunk plus forensic chunking metadata."""

    section: str
    text: str
    page_number: int | None
    word_count: int
    overlap_words: int
    boundary_reason: str
    section_chunk_index: int
    section_chunk_total: int
    continuation_before: bool
    continuation_after: bool


_PORTAL_GUIDES = {
    "shared": [
        ("Navigation and privacy", "The HR Assistant answers only from the authenticated company portal. It cannot use outside knowledge, expose another company, or reveal passwords, reset tokens, secret keys, SMTP credentials, or private authentication data."),
        ("Company policies and violations", "Published company policies are available in Company Policies. Active company violation/offense rules and their disciplinary actions are available in Violations & Disciplinary Actions. Answers must use only published/effective policy files and active/effective violation rules from the authenticated company. Administrators manage policy upload/versions/Bin and the separate violation master list."),
        ("Announcements and reminders", "Announcements show published company notices. Independent event reminders are planning records for future events and activities. Reminder notifications are sent to administrators at one month, two weeks, and one week before an event."),
        ("Leave workflow", "Employees may file Whole Day, AM Only, or PM Only leave in Leave Management using a coded standard reason and an Others explanation only when 0 - OTHERS is selected. Overlapping active leave for the same owner is blocked. Leaders and Managers may file for direct reports, but approval always follows the leave owner hierarchy and filing is never automatic approval. Paid credits are reserved after final approval and used on approved dates."),
        ("Attendance and DTR", "Attendance supports multiple non-overlapping WFO and WFH work sessions per day. Mixed locations become Hybrid. Actual punches remain in audit history while payroll Time In rounds up and Time Out rounds down to 15-minute boundaries. Approved AM/PM leave supplies four leave hours on an eight-hour day and only the remaining work portion is checked for undertime; leave, gaps, and lunch never become overtime."),
        ("Overtime requests", "The employee Attendance/DTR page contains one collapsible Overtime Request section combining DTR-prefilled filing and My Overtime Requests. Employee ID, name, and the original DTR reference are read-only. Date Rendered, OT Start/End, and Estimated Hours are prefilled but editable. The employee selects OT Type and enters Purpose, optional Travel Fare and required Route, and Dinner Break. Company OT rules can deduct dinner-break hours from payable OT, pair qualifying smaller OT blocks within one cut-off as Shifting Credits, and grant additional Vacation Leave for a qualifying single long OT request. Shifting-credit eligibility uses the company exclusion list rather than guessing a senior-position hierarchy. Approved requests populate the full OT report row; a DTR-only row leaves unsupported fields blank."),
        ("Company forms and documents", "Company Form/Documents contains company templates. Administrators upload and manage templates and review employee submissions. Employees may view, download, fill, and submit forms when the selected template permits employee submission."),
        ("App-wide answer boundary", "The assistant may answer from authorized live HR records, published company policies, company announcements, configured leave rules, and actual workflows available in this HR application. If the information is not present in those company or application sources, it must say that the information was not found and must not use outside knowledge."),
    ],
    "employee": [
        ("Employee portal scope", "The employee assistant may show the signed-in employee's own profile, leave credits, personal leave requests, published company policies, active company violation and disciplinary-action rules, the signed-in employee's own issued disciplinary records when portal visibility is enabled, announcements, reminders visible to employees, and instructions for available employee portal pages. It must never disclose another employee's disciplinary history or private record."),
        ("Employee records", "Employees can ask for their employee number, department, manager, leader, job title, work email, employment status, hire date, and other fields stored in their own employee profile."),
        ("Employee documents", "Company Form/Documents contains available company forms and documents. Its My Documents tab contains only the signed-in employee's own completed form submissions, review status, administrator notes, previews, and downloads. The assistant must not invent a document that is not present."),
        ("Employee navigation", "Dashboard contains the employee's Time In/Time Out and Announcements workspaces. Attendance Hub contains the employee's monthly DTR, attendance editor, and overtime request workflow. Reports generates one employee-scoped Excel workbook containing DTR Logs, Overtime File, and Leave File. Leave Management contains leave overview, filing, My Requests, and authorized leader or manager views. Company Form/Documents contains View, Download, Fill / Submit, and My Documents. Onboarding contains Overview, Checklist, and the permanent Benefits workspace. Company Policies, HR Contacts, and FAQ retain their corresponding approved or default information."),
    ],
    "admin": [
        ("Administrator portal scope", "The administrator assistant may summarize authorized company-wide employees, departments, user accounts, leave requests, leave credits, policies, announcements, reminders, integrations, and company settings. Results must remain restricted to the authenticated company."),
        ("Employee management", "Administrators manage employee records, account linkage, departments, manager and leader assignments, job titles, employment status, hire date, demographics, training checklist, account information, onboarding progress, onboarding checklist setup, and company benefits in Employees."),
        ("Security restrictions", "Passwords, password hashes, reset tokens, cookie secrets, SMTP passwords, and equivalent credentials can never be displayed by the assistant. The assistant may explain where settings are managed without exposing secret values."),
        ("Administrator navigation", "Admin Dashboard contains company metrics and Attendance/DTR/OT. Employees contains employee list, add, edit, and Violations / Disciplinary Records workspaces for actual employee cases. Policies contains library, upload, management, Violations & Disciplinary Actions, and Bin; the violation workspace is the single source of truth for master offense definitions and penalty guidance. Leave Management contains overview, employee leave accounts, leave requests, and rules. Announcements contains overview, create, manage, reminders, and archive. Company Form/Documents contains overview, upload, management, employee submissions, and Bin. Reports includes disciplinary reporting alongside existing reports, and Integrations contains the implemented integration workspaces."),
    ],
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean_model_answer(value: str) -> str:
    """Normalize model output without destroying Markdown list structure.

    Prompt/history normalization intentionally collapses whitespace, but final
    assistant output must preserve line breaks so bullets and numbered steps
    remain readable in Streamlit Markdown.
    """

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    previous_blank = False

    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()

    answer = "\n".join(cleaned_lines).strip()
    answer = re.sub(
        r"^(?:final answer|answer|response)\s*:\s*",
        "",
        answer,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return answer


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (value or "").casefold())


def _organize_answer(value: str) -> str:
    """Keep simple answers concise and normalize multi-item responses."""

    text = (value or "").strip()
    if not text:
        return text
    lines = [line.rstrip() for line in text.splitlines()]
    meaningful = [line for line in lines if line.strip()]
    if len(meaningful) <= 2:
        return "\n".join(meaningful)

    # Preserve existing Markdown lists and numbered procedures.
    if any(re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line) for line in meaningful):
        return "\n".join(lines).strip()

    # Convert short, label-like multi-line answers into readable bullets.
    if all(len(line.strip()) <= 180 for line in meaningful[1:]):
        return meaningful[0] + "\n\n" + "\n".join(
            f"- {line.strip()}" for line in meaningful[1:]
        )
    return "\n".join(lines).strip()


_DOCUMENT_CHUNK_SOURCE_TYPES = frozenset({"policy", "company_form_content"})


def _word_count(value: str) -> int:
    """Return a stable local chunk-sizing unit without external tokenizers."""

    return len(re.findall(r"\S+", value or ""))


def _sentence_units(value: str) -> list[str]:
    """Split text on paragraph/sentence boundaries while preserving rows/lists."""

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    units: list[str] = []
    for raw_block in re.split(r"\n\s*\n+", text):
        block = re.sub(r"[ \t]+", " ", raw_block).strip()
        if not block:
            continue
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        for line in lines:
            # Table/list rows are logical units and should not be broken mid-row.
            if " | " in line or re.match(r"^(?:[-*•]|\d+[.)])\s+", line):
                units.append(line)
                continue
            sentences = [
                item.strip()
                for item in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line)
                if item.strip()
            ]
            units.extend(sentences or [line])
    return units


_EVIDENCE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "i", "if", "in", "is", "it", "may", "me",
    "my", "of", "on", "or", "should", "that", "the", "their", "this",
    "to", "was", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your",
}


def _meaningful_evidence_tokens(value: str) -> list[str]:
    """Return stable lexical terms used only for local evidence ranking."""

    return [
        token
        for token in _tokenize(value)
        if len(token) >= 2 and token not in _EVIDENCE_STOPWORDS
    ]


def _normalized_phrase_text(value: str) -> str:
    """Normalize punctuation/hyphens so policy wording variants still match."""

    return " ".join(_tokenize(value))


def _question_evidence_profile(question: str) -> str:
    """Classify the evidence shape needed by a user question."""

    clean = _clean_text(question).casefold()
    semantics = analyze_query_semantics(question)
    if re.search(r"\b(compare|comparison|difference|versus|vs\.?)\b", clean):
        return "comparison"
    if semantics.request_shape in {"responsibility", "requested_action"}:
        return "direct_fact"
    if re.search(r"^\s*what\s+(?:benefits|requirements|reasons|documents|conditions|options)\b", clean):
        return "list"
    if re.search(r"^\s*how\s+much\b|\b(amount|cost|price|allowance|reimbursement|cash award)\b", clean):
        return "amount"
    if re.search(r"^\s*how\s+(?:many|long)\b", clean):
        return "duration_or_count"
    if re.search(r"^\s*when\b|\bwhat time\b|\bwhat date\b", clean):
        return "date_or_time"
    if re.search(r"\bwhat happens\b|\bpenalt(?:y|ies)\b|\bconsequence\b|\bdisciplin", clean):
        return "consequence"
    if re.search(r"\b(eligible|eligibility|qualify|qualified|entitled|covered|allowed|prohibited)\b", clean):
        return "eligibility"
    if _scoped_workflow_question(question) is not None:
        return "procedure"
    if re.search(r"^\s*(?:what should|how (?:do|does|can|should|to)|what do)\b|\bprocedure\b|\bprocess\b", clean):
        return "procedure"
    if re.search(r"^\s*(?:list|show|give me|what are|which are)\b", clean):
        return "list"
    if re.search(r"^\s*(?:can|could|may|should|will|do|does|is|are|has|have)\b", clean):
        return "yes_no"
    return "standard"


def _answerability_cue_bonus(question: str, text: str) -> float:
    """Boost evidence that contains the kind of fact the question asks for."""

    profile = _question_evidence_profile(question)
    clean = _normalized_phrase_text(text)
    raw = str(text or "").casefold()

    if profile == "amount":
        if re.search(
            r"(?:₱|\$|¥|€|\b(?:php|p)\s*)\d[\d,]*(?:\.\d+)?|"
            r"\b\d[\d,]*(?:\.\d+)?\s*(?:peso|pesos|php|yen|dollar|dollars)\b",
            raw,
            re.I,
        ):
            return 1.0
        if re.search(r"\b(amount|allowance|reimbursement|cash|pay|rate|cost|award)\b", clean):
            return 0.55
    elif profile == "duration_or_count":
        # Many company handbooks write numbers as 'five (5) minutes' or
        # 'eight (8) hours'. The previous cue matcher missed both, causing
        # false no-match even when the complete answer was present.
        amount = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty)"
        units = r"(?:days?|weeks?|months?|years?|hours?|minutes?|persons?|dependents?|credits?)"
        if re.search(rf"\b{amount}\s*(?:\(\s*\d+\s*\))?\s+{units}\b", raw, re.I):
            return 1.0
    elif profile == "date_or_time":
        if re.search(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", raw):
            return 1.0
        # Relative deadlines are genuine temporal answers. 'Award is given
        # after the results are announced' has no numeric time or month.
        if re.search(r"\b(?:after|before|upon|once|within|following|not later than)\b.{0,90}\b(?:result|announc|approv|complet|receipt|event|publish|release|issu|work|day|week|month|year|notice)\w*\b", clean):
            return 0.9
        # A schedule can be anchored to an event rather than a calendar date:
        # e.g. 'awards are presented during afternoon briefings'.
        if re.search(r"\b(?:during|at|on)\s+(?:the\s+)?(?:[a-z]+\s+){0,3}(?:briefings?|ceremon(?:y|ies)|meetings?|events?|part(?:y|ies)|occasions?|celebrations?|gatherings?)\b", clean):
            return 0.9
        if re.search(r"\b(?:before|after|within|effective|date|time|month|year|day)\b", clean):
            return 0.5
    elif profile == "consequence":
        if re.search(r"\b(?:disqualif|absent|penalt|sanction|suspend|dismiss|forfeit|deduct|warning|violation|terminate|termination|awol|misconduct)\w*\b", clean):
            return 1.0
        if re.search(r"\b(?:subject\s+to\s+disciplinary|deemed\s+absent|considered\s+absent|treated\s+as\s+absent)\b", clean):
            return 1.0
        if re.search(r"\b(?:shall|will|must|required)\b", clean):
            return 0.45
    elif profile in {"eligibility", "yes_no"}:
        if re.search(r"\b(?:eligible|qualif|entitled|covered|allowed|prohibit|required|shall|may|must|not)\w*\b", clean):
            return 0.8
    elif profile == "procedure":
        if re.search(r"\b(?:submit|notify|inform|request|approval|approve|form|report|contact|must|shall|within|before|after)\w*\b", clean):
            return 0.75
    elif profile == "direct_fact":
        # Generic action/actor evidence, not a company-specific rule. Avoid
        # accepting a source only because it mentions the subject or role.
        if re.search(r"\b(?:responsib|accountab|shoulder|pay|paid|charg|request|inform|notif|contact|"
                     r"provid|arrang|requir|must|shall|advis|instruct)\w*\b", clean):
            return 0.8
    elif profile in {"comparison", "list"}:
        if " | " in text or re.search(r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+", text):
            return 0.65
    return 0.0


def _document_search_text(document: KnowledgeDocument) -> str:
    """Use real source headings in retrieval; no QA keywords or question templates.

    The body stays verbatim. Source title/section labels are stored in the
    authorized document metadata, not inferred from the user's question.
    """
    metadata = document.metadata or {}
    title = str(metadata.get("title") or document.title or "").strip()
    section = str(metadata.get("section") or "").strip()
    return "\n".join(part for part in (title, section, document.text) if part)


def _record_answer_relevance(question: str, answer: str) -> bool:
    """Reject unrelated live-record outputs without deciding any policy facts.

    A recognizable subject in a full question must match at least one content
    term in the record answer. Short/pronominal requests remain the caller's
    existing trusted live path. Ignore generic HR nouns when finding the subject.
    """
    generic = {"employee", "employees", "company", "office", "person", "people", "record", "records",
               "detail", "details", "information", "show", "list", "what", "when", "where", "who",
               "which", "about", "their", "have", "need", "policy", "requirement", "requirements",
               "case", "cases", "work", "working", "time", "during", "system", "current"}
    terms = {x for x in _meaningful_evidence_tokens(question) if x not in generic and len(x) >= 4}
    if not terms:
        return True
    response_terms = set(_meaningful_evidence_tokens(answer))
    # A fabricated or unrelated record can share 'employee' or 'company' only;
    # positive subject overlap is required to return record data directly.
    return bool(terms & response_terms)


def _record_intent_matches_request(question: str, intent: str) -> bool:
    """Require a record *entity* request before using a live-record handler.

    Rules inspect generic entity types, not QA phrases, tenant records, or
    expected policy answers. A question about consequences of a rule isn't a
    request to list the disciplinary case database.
    """
    clean = _normalized_phrase_text(question)
    if intent == "policy_violation":
        return bool(
            re.search(r"\b(?:violation|offense|misconduct)\s+(?:code|id|category|severity|level|record|list)\b", clean)
            or re.search(r"\b(?:list|show|find|count|which|what are|how many)\b.{0,65}\b(?:violation|offense|misconduct)\s*(?:codes|records|categories|types|levels|rules|definitions|s)?\b", clean)
            or re.search(r"\b(?:qa\s*v\d+|violation\s*#?\d+|offense\s*#?\d+)\b", clean)
            or re.search(r"\b(?:minor|moderate|major|grave)\b.{0,50}\b(?:violation|offense|misconduct)\b", clean)
            or re.search(r"\b(?:violation|offense|misconduct)\b.{0,35}\b(?:minor|moderate|major|grave)\b", clean)
        )
    if intent == "disciplinary_records":
        return bool(re.search(
            r"\b(?:disciplinary\s+(?:cases?|records?|history|report)|"
            r"(?:issued|closed|cancelled|pending|active)\s+(?:disciplinary\s+)?case|"
            r"(?:list|show|find|count|how many)\b.{0,55}\b(?:cases|disciplinary\s+records)|"
            r"case\s+(?:id|number|status)|(?:offense|violation)\s+record)\b", clean))
    if intent in {"employee_lookup", "employee_profile"}:
        # Eligibility for a program is not a request for an employee's DB
        # profile even when it contains the word 'employee' or 'who'.
        if re.search(r"\b(?:eligib|qualif|criteria|award|program|requirements|purpose)\w*\b", clean):
            return False
    return True


def _passage_diagnostic(query: str, document: KnowledgeDocument) -> dict[str, object]:
    """Explain why a passage ranks; no expected answers or learned QA labels."""
    tokens = set(_meaningful_evidence_tokens(query))
    body = set(_meaningful_evidence_tokens(document.text))
    heading = set(_meaningful_evidence_tokens(str((document.metadata or {}).get("section") or "")))
    subject_tokens = tokens - {"employee", "employees", "company", "policy", "work", "required"}
    return {
        "body_overlap": len(subject_tokens & body),
        "body_coverage": round(len(subject_tokens & body) / max(1, len(subject_tokens)), 3),
        "heading_overlap": len(subject_tokens & heading),
        "answer_cue": round(_answerability_cue_bonus(query, document.text), 3),
        "section": str((document.metadata or {}).get("section") or "-"),
    }


def _evidence_fit_bonus(question: str, document: KnowledgeDocument) -> float:
    """Return a bounded relevance bonus on top of BM25/vector RRF ranking."""

    query_terms = _meaningful_evidence_tokens(question)
    if not query_terms:
        return 0.0

    evidence_text = _document_search_text(document)
    evidence_tokens = _meaningful_evidence_tokens(evidence_text)
    if not evidence_tokens:
        return 0.0

    query_unique = set(query_terms)
    evidence_unique = set(evidence_tokens)
    overlap = query_unique.intersection(evidence_unique)
    coverage = len(overlap) / max(1, len(query_unique))

    # Reward a concise passage that covers the question terms without allowing
    # a very long policy to win simply because the same words occur many times.
    density = min(1.0, len(overlap) / max(1.0, math.sqrt(len(evidence_unique))))

    normalized_evidence = _normalized_phrase_text(evidence_text)
    phrase_hits = 0
    for size in (3, 2):
        for index in range(0, max(0, len(query_terms) - size + 1)):
            phrase = " ".join(query_terms[index:index + size])
            if phrase and phrase in normalized_evidence:
                phrase_hits += 1
    phrase_bonus = min(1.0, phrase_hits / 3.0)

    title_terms = set(_meaningful_evidence_tokens(document.title))
    title_overlap = len(query_unique.intersection(title_terms)) / max(1, len(query_unique))
    cue_bonus = _answerability_cue_bonus(question, evidence_text)

    return (
        (coverage * 0.48)
        + (density * 0.12)
        + (phrase_bonus * 0.18)
        + (title_overlap * 0.10)
        + (cue_bonus * 0.12)
    )


def _focused_evidence_excerpt(query: str, text: str, max_chars: int) -> str:
    """Keep the most question-relevant sentence/row plus nearby context."""

    clean = str(text or "").strip()
    limit = max(320, int(max_chars))
    if len(clean) <= limit:
        return clean

    units = _sentence_units(clean)
    if not units:
        return clean[:limit].rstrip()

    query_terms = set(_meaningful_evidence_tokens(query))
    normalized_query = _normalized_phrase_text(query)

    def unit_score(unit: str) -> float:
        unit_terms = set(_meaningful_evidence_tokens(unit))
        lexical = len(query_terms.intersection(unit_terms))
        cue = _answerability_cue_bonus(query, unit)
        phrase = 0.0
        normalized_unit = _normalized_phrase_text(unit)
        if normalized_query and len(normalized_query) <= 120 and normalized_query in normalized_unit:
            phrase = 2.0
        information = 0.0
        if re.search(r"(?:₱|\$|¥|€)\s*\d|\b\d+(?:[.,]\d+)?\b", unit):
            information += 0.55
        if re.search(
            r"\b(?:shall|must|required|eligible|entitled|allowance|reimbursement|"
            r"disqualif|absent|penalt|sanction|deadline|within|before|after)\w*\b",
            normalized_unit,
        ):
            information += 0.35
        return (lexical * 2.0) + cue + phrase + information

    best_index = max(range(len(units)), key=lambda index: unit_score(units[index]))
    chosen: list[int] = [best_index]
    if re.match(r"^(?:[-*•]|\d+[.)])\s+", units[best_index]):
        list_indexes = [best_index]
        for step in (-1, 1):
            index = best_index + step
            while 0 <= index < len(units) and re.match(r"^(?:[-*•]|\d+[.)])\s+", units[index]):
                prospective = sorted(set(list_indexes + [index]))
                if len(" ".join(units[i] for i in prospective)) > limit:
                    break
                list_indexes.append(index)
                index += step
        chosen = sorted(set(list_indexes))
    radius = 1
    while radius < len(units):
        added = False
        for candidate in (best_index - radius, best_index + radius):
            if candidate < 0 or candidate >= len(units) or candidate in chosen:
                continue
            prospective = sorted(chosen + [candidate])
            rendered = " ".join(units[index] for index in prospective)
            if len(rendered) > limit:
                continue
            chosen.append(candidate)
            added = True
        if not added and len(" ".join(units[index] for index in sorted(chosen))) >= int(limit * 0.72):
            break
        radius += 1

    excerpt = " ".join(units[index] for index in sorted(chosen)).strip()
    if not excerpt:
        excerpt = units[best_index].strip()
    return excerpt[:limit].rstrip()


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20",
}


def _explicit_year_values(value: str) -> set[str]:
    """Return explicit service/year quantities without interpreting policy rules."""

    clean = _normalized_phrase_text(value)
    values = set(re.findall(r"\b(\d+)\s*(?:year|years)\b", clean))
    for word, number in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\s+(?:year|years)\b", clean):
            values.add(number)
    return values


def _document_body_text(document: KnowledgeDocument) -> str:
    """Strip the synthetic retrieval header while preserving source wording."""

    text = str(document.text or "").strip()
    metadata = document.metadata or {}
    if document.source_type == "policy":
        prefix = (
            f"Policy: {metadata.get('title')}. Version: {metadata.get('version')}. "
            f"Section: {metadata.get('section')}. "
        )
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    return text


def _verbatim_published_policy_overview(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    company_id: int,
    role_scope: str,
    max_chars: int = 1800,
) -> tuple[str, dict[str, object]]:
    """Return a whole, short editor-published policy when its title is requested.

    This is *source selection*, not a policy answer key. Source authorization,
    company, role, publication, and effective-date filtering happened in the
    knowledge builder and retriever. A general question that names one whole
    policy may be answered verbatim without letting an LLM discard its evidence.

    Never shorten a source, join separate policies/chunks, resolve conflicting
    versions, answer scenarios, or treat a document's mention of a policy as
    authority to provide a whole-policy overview. Those remain RAG questions.
    """
    query = _normalized_phrase_text(question)
    if not re.match(
        r"^(?:what is|what s|what are|list|outline|describe|explain|"
        r"summarize|tell me about|give me an overview of)\b",
        query,
    ):
        return "", {"decision": "not-overview-request"}

    # Disallow additional conditions/people/actions beyond the policy title.
    # These are question-framing words, never policy facts or expected answers.
    framing_terms = {
        "company", "overview", "summary", "please", "describe", "explain",
        "summarize", "tell", "about", "give", "our", "your", "their", "full",
        "complete", "policy", "policies", "rules", "guidelines", "s",
    }
    request_terms = set(_meaningful_evidence_tokens(question))
    candidates: list[tuple[str, str, str]] = []
    for item in retrieved[:8]:
        doc = item.document
        metadata = doc.metadata or {}
        key = str(metadata.get("file_key") or "")
        if (
            doc.source_type != "policy"
            or doc.company_id != company_id
            or doc.role_scope not in {"shared", role_scope}
            or not key.startswith("policy:")
            or not key.endswith(":record")
            or not metadata.get("policy_id")
            or int(metadata.get("total_chunks") or 0) != 1
        ):
            continue
        title = str(metadata.get("title") or "").strip()
        title_phrase = _normalized_phrase_text(title)
        if not title_phrase or len(title_phrase.split()) < 2:
            continue
        # A request may use a generic descriptor ("rules", "guidelines")
        # instead of the trailing word "Policy". It must still name the
        # distinctive policy title in order, not merely overlap its topic.
        title_core = re.sub(r"\s+(?:policy|policies)$", "", title_phrase).strip()
        if not title_core or not re.search(
            rf"\b{re.escape(title_core)}\b", query
        ):
            continue
        title_terms = set(_meaningful_evidence_tokens(title))
        if request_terms - title_terms - framing_terms:
            continue
        body = _document_body_text(doc).strip()
        # No truncation: source length must fit the display budget in full.
        if not 35 <= len(body) <= max(35, int(max_chars)):
            continue
        candidates.append((str(metadata["policy_id"]), title, body))

    if len(candidates) != 1:
        return "", {"decision": "none-or-ambiguous-policy", "matches": len(candidates)}
    policy_id, title, body = candidates[0]
    return body, {
        "decision": "accepted", "source": title, "policy_id": policy_id,
        "items": len(_sentence_units(body)), "source_type": "published-policy-record",
    }



def _verbatim_complete_document_policy_overview(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    company_id: int,
    role_scope: str,
    max_chars: int = 4800,
    max_chunks: int = 8,
) -> tuple[str, dict[str, object]]:
    """Copy a whole *retrieved* uploaded policy when the question asks for it.

    This is not semantic policy summarization and contains no seeded HR facts:
    it requires an unqualified whole-policy question, one uniquely named and
    authorized uploaded document, and every numbered chunk of that document.
    Refuse partial documents, missing or overlapping chunks, and competing
    sources instead of manufacturing a summary from an incomplete retrieval.
    """
    query = _normalized_phrase_text(question)
    match = re.fullmatch(
        r"(?:what is|what s|what are|describe|outline|summarize|explain|"
        r"tell me about|give me an overview of)\s+"
        r"(?:(?:the|our|your|company s|company)\s+)*"
        r"(?P<subject>[a-z0-9 ]+?)\s+"
        r"(?:policy|rules|guidelines)",
        query,
    )
    if not match:
        return "", {"decision": "not-whole-document-overview"}
    subject = match.group('subject').strip()
    if not subject or any(word in subject.split() for word in (
        'for', 'with', 'without', 'if', 'when', 'during', 'before', 'after',
        'compared', 'versus', 'today', 'currently', 'now', 'exceptions',
        'requirements', 'eligibility', 'amount', 'payment', 'penalty',
    )):
        return "", {"decision": "qualified-or-ambiguous-question"}

    groups: dict[str, list[RetrievedDocument]] = defaultdict(list)
    for item in retrieved:
        doc = item.document
        metadata = doc.metadata or {}
        key = str(metadata.get('file_key') or '')
        if (doc.source_type != 'policy'
            or doc.company_id != company_id
            or doc.role_scope not in {'shared', role_scope}
            or not re.fullmatch(r'policy:[0-9]+:document:[0-9]+', key)
            or not metadata.get('policy_document_id')
            or not metadata.get('policy_id')):
            continue
        groups[key].append(item)

    matches: list[tuple[str, str, list[KnowledgeDocument]]] = []
    for key, items in groups.items():
        documents = [item.document for item in items]
        metadata = documents[0].metadata or {}
        title = str(metadata.get('title') or '').strip()
        core = re.sub(
            r'\s+(?:policy|policies)$', '', _normalized_phrase_text(title)
        ).strip()
        if len(core.split()) < 2:
            continue
        if subject != core:
            # A document may use the full name (e.g. 'X Award') in its
            # actual text while the editor title is only 'X'. The additional
            # descriptor must be *in the same literal name phrase* inside
            # the policy, not an assumed synonym or separate keyword match.
            if not subject.startswith(core + ' ') or len(subject.split()) > len(core.split()) + 2:
                continue
            all_content = ' '.join(_normalized_phrase_text(_document_body_text(doc))
                                   for doc in documents)
            if not re.search(rf'\b{re.escape(subject)}\b', all_content):
                continue

        try:
            total = int(metadata.get('total_chunks') or 0)
            indexes = [int((doc.metadata or {}).get('chunk_index') or 0)
                       for doc in documents]
        except (TypeError, ValueError):
            continue
        if not (2 <= total <= min(8, int(max_chunks))
                and len(indexes) == total
                and sorted(indexes) == list(range(1, total + 1))):
            continue
        if any(
            str((doc.metadata or {}).get('file_key')) != key
            or (doc.metadata or {}).get('title') != title
            or (doc.metadata or {}).get('version') != metadata.get('version')
            or int((doc.metadata or {}).get('total_chunks') or 0) != total
            or int((doc.metadata or {}).get('chunk_overlap_words') or 0) > 0
            or not _document_body_text(doc).strip()
            for doc in documents
        ):
            continue
        ordered = sorted(documents, key=lambda d: int(d.metadata['chunk_index']))
        full_text = '\n\n'.join(_document_body_text(doc).strip() for doc in ordered)
        if not 120 <= len(full_text) <= max(300, int(max_chars)):
            continue
        matches.append((key, title, ordered))

    if len(matches) != 1:
        return "", {"decision": "no-single-complete-document", "matches": len(matches)}
    key, title, docs = matches[0]
    meta = docs[0].metadata or {}
    filename = str(meta.get('filename') or title).strip()
    version = str(meta.get('version') or 'not specified')
    body = '\n\n'.join(_document_body_text(doc).strip() for doc in docs)
    # Do not rewrite example years or imply illustrative payout values are
    # current benefits. Explicitly label the response as source reproduction.
    answer = (
        f"**Documented policy: {title}**\n"
        f"Source: {filename} (version {version}). "
        "Text below is reproduced from the policy document; dated examples, "
        "if present, do not establish current award amounts.\n\n"
        f"{body}"
    )
    return answer, {
        'decision': 'accepted', 'source': filename,
        'file_key': key, 'chunks': len(docs), 'source_type': 'complete-uploaded-policy',
    }


# These predicates describe generic language actions, not company-specific HR
# decisions. An exact action match is more useful than subject word overlap when
# extracting *who*, *what to request*, or the first required action.
_DIRECT_ACTION_FAMILIES = {
    "notify": re.compile(r"\b(?:inform|informs|informed|informing|notif\w*|contact\w*|report(?:s|ed|ing)?\s+to|call(?:s|ed|ing)?)\b", re.I),
    "payment": re.compile(r"\b(?:shoulder\w*|pay|pays|paid|paying|charg\w*|bear(?:s|ing)?|borne|responsib\w*\s+for\s+(?:(?:\w+\s+){0,5})?(?:cost|costs|expense|expenses|payment|payments))\b", re.I),
    "request": re.compile(r"\b(?:request\w*|ask(?:s|ed|ing)?\s+for|obtain\w*|seek|seeking)\b", re.I),
    "provide": re.compile(r"\b(?:provid\w*|suppl\w*|furnish\w*|deliver\w*)\b", re.I),
    "approve": re.compile(r"\b(?:approv\w*|authoriz\w*|permit\w*)\b", re.I),
    "submit": re.compile(r"\b(?:submit\w*|fil\w*|send|sent|deliver\w*)\b", re.I),
}


def _direct_action_target(question: str) -> str | None:
    """Extract a requested predicate from an ordinary who/what question.

    Only generic grammatical question forms are examined; no HR concepts,
    department names, or specific policy vocabulary are used for routing.
    """
    clean = _normalized_phrase_text(question)
    tail = None
    # Permit initial context, e.g. "In case of an incident, who should ...".
    match = re.search(r"\bwho\s+(?:should|must|will|is|are)\b(.+)$", clean)
    if match:
        tail = match.group(1)
    else:
        match = re.search(r"\bwhat\s+should\b(.+)$", clean)
        if match:
            tail = match.group(1)
    if not tail:
        return None
    hits = [
        (match.start(), family)
        for family, regexp in _DIRECT_ACTION_FAMILIES.items()
        if (match := regexp.search(tail)) is not None
    ]
    if hits:
        return min(hits, key=lambda item: item[0])[1]
    # "responsible for notifying" is handled by notify; "responsible for
    # expenses" itself expresses the payment actor.
    if re.search(r"\bresponsib\w*\s+for\s+(?:the\s+)?(?:cost|expense|payment)", tail):
        return "payment"
    return None


def _exception_only_sentence(unit: str) -> bool:
    """Identify fallback-only facts that cannot answer a default first step."""
    text = _normalized_phrase_text(unit)
    if re.search(r"\b(?:otherwise|alternatively|instead|unless|except)\b", text):
        return True
    match = re.search(r"\bif\b(.{0,180})", text)
    if not match:
        return False
    condition = re.split(r"[,;:]|\bthen\b", match.group(1), maxsplit=1)[0]
    return bool(re.search(r"\b(?:not|cannot|could not|unavailable|unable|fails?|failure|absent|missing)\b", condition))


def _explicit_notification_recipients(question: str, *, target: str) -> tuple[str, ...]:
    """Names enumerated as direct recipients, not people inferred by the AI.

    An explicit list after 'notify/inform/contact X, Y and Z' is a stricter
    answer constraint than the generic presence of an action like 'informing'.
    This is intentionally syntactic and contains no company or HR name list.
    """
    if target != "notify":
        return ()
    value = _clean_text(question).casefold()
    match = re.search(
        r"\b(?:notif\w*|inform\w*|contact\w*|report\w*\s+to)\s+"
        r"(?:the\s+)?(.+?)(?:\s+about\b|\s+regarding\b|\s+concerning\b|[?.!]|$)",
        value,
    )
    if not match:
        return ()
    raw = match.group(1).strip()
    # The clause is a direct-object enumeration, not an arbitrary 'and' in
    # the user's broader scenario, e.g. an airport in the Philippines or Japan.
    if not re.search(r",|\s+and\s+", raw):
        return ()
    parts = [
        re.sub(r"^(?:the\s+)", "", part).strip(" ,")
        for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", raw)
    ]
    phrases = tuple(_normalized_phrase_text(part) for part in parts if part)
    if len(phrases) < 2 or any(len(phrase) < 2 or len(phrase) > 100 for phrase in phrases):
        return ()
    return phrases


def _document_answer_group(document: KnowledgeDocument) -> tuple[object, ...]:
    """Only join chunks belonging to the same authorized original document."""
    meta = document.metadata or {}
    identity = meta.get("file_key") or meta.get("filename") or document.document_id
    return (document.company_id, document.source_type, str(identity), str(meta.get("version") or ""))


def _compound_direct_fact_evidence(
    query: str,
    retrieved: list[RetrievedDocument],
    candidates: list[tuple[float, int, int, str, str, bool]],
    *,
    target: str,
    max_items: int,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Prefer complete verbatim source evidence instead of a 7B rewrite.

    For named recipient lists, require exact requested phrases in the same
    action clause. For coordinated expense/object facets, require an action
    related to each facet; only a nearby sentence *within the same chunk* may
    supply a generic 'these expenses' antecedent. Distinct chunks may be
    combined only within the same authorized original document.
    """
    recipients = _explicit_notification_recipients(query, target=target)
    if recipients:
        for score, doc_rank, _, unit, source, matched in candidates:
            if not matched:
                continue
            clean_unit = _normalized_phrase_text(unit)
            if all(re.search(rf"\b{re.escape(phrase)}\b", clean_unit) for phrase in recipients):
                return unit, {
                    "profile": "direct_fact", "items": 1, "sources": [source],
                    "target": target, "decision": "accepted-explicit-recipient-coverage",
                    "covered_recipients": list(recipients),
                }
        return "", {
            "profile": "direct_fact", "items": 0, "sources": [],
            "target": target, "decision": "explicit-recipients-incomplete",
            "required_recipients": list(recipients),
        }

    facets = re.findall(
        r"\b([a-z][a-z0-9-]{3,})\s+and\s+([a-z][a-z0-9-]{3,})\b",
        _normalized_phrase_text(query),
    )
    if not facets:
        return None
    required = {word for pair in facets for word in pair}
    action_pattern = _DIRECT_ACTION_FAMILIES[target]
    expense_nouns = re.compile(r"\b(?:expense|expenses|cost|costs|fee|fees|charge|charges|payment|payments)\b", re.I)
    units_by_doc = {
        rank: _sentence_units(_document_body_text(result.document))
        for rank, result in enumerate(retrieved[:8])
    }
    matching: dict[tuple[object, ...], list[tuple[float, set[str], int, int, str, str]]] = defaultdict(list)
    for score, doc_rank, unit_index, unit, source, target_match in candidates:
        if not target_match:
            continue
        units = units_by_doc[doc_rank]
        action_matches = list(action_pattern.finditer(unit))
        if not action_matches:
            continue
        found: set[str] = set()
        lower = unit.casefold()
        for facet in required:
            for match in re.finditer(rf"\b{re.escape(facet)}\b", lower):
                before = lower[max(0, match.start() - 34):match.start()]
                after = lower[match.end():match.end() + 35]
                if re.search(r"\b(?:no|without|lack of|absence of)\s*$", before) or re.match(
                    r"\s+(?:is|are|was|were|be)?\s*(?:not\s+)?(?:available|unavailable|missing)\b", after,
                ):
                    continue
                distance = min(
                    min(abs(match.end() - action.start()), abs(match.start() - action.end()))
                    for action in action_matches
                )
                if distance <= 100:
                    found.add(facet)
                    break

        rendered = unit
        # Many actual DOCX policies put "4.1 Transportation Expenses" on a
        # *separate line*, followed by a transport-request instruction, and
        # only THEN an anaphoric payer clause ("Any incurred expenses ...").
        # Sentence splitting preserves these as three separate units. The old
        # immediate-predecessor + three-word noun check erroneously rejected
        # the already-retrieved payer rule and caused an Ollama timeout.
        #
        # Use at most two preceding units from this *same authorized chunk*.
        # Do not infer payment from a negative condition like "no transport
        # available" alone, or from an example about unrelated expense types.
        generic_payer = bool(re.search(
            r"\b(?:any|such|these|those|the)\s+(?:incurred\s+)?(?:expenses?|costs?|charges?)\b",
            lower,
        )) and not re.search(r"\b(?:such as|e\.g\.|for example)\b|\b(?:expenses?|costs?)\s*\(", lower)
        if target == "payment" and unit_index > 0 and generic_payer and expense_nouns.search(unit):
            prior = units[max(0, unit_index - 2):unit_index]
            for facet in required - found:
                # A section header states the subject; a nearby procedure can
                # identify it through an action even without "expense".
                # We do not cross a different numbered section heading.
                relevant: list[str] = []
                for previous in reversed(prior):
                    if re.match(r"^\s*\d+(?:\.\d+)+\s+", previous) and not re.search(
                        rf"\b{re.escape(facet)}\b", previous, re.I,
                    ):
                        break
                    if re.search(rf"\b{re.escape(facet)}\b", previous, re.I):
                        named_cost = bool(re.search(
                            rf"\b{re.escape(facet)}\b\W+(?:\w+\W+){{0,3}}(?:expenses?|costs?|charges?)\b",
                            previous, re.I,
                        ))
                        # The action must actually govern THIS object. A
                        # sentence saying "provide transportation ... to the
                        # location of a hotel" does not mean anyone paid for
                        # hotel accommodation. Link the antecedent only when
                        # it is near the *named* action, with no different
                        # requested facet between them.
                        action_hits = list(re.finditer(
                            r"\b(?:request\w*|provid\w*|arrang\w*|suppl\w*|reimburs\w*)\b",
                            previous, re.I,
                        ))
                        obj_hits = list(re.finditer(rf"\b{re.escape(facet)}\b", previous, re.I))
                        near_action = any(
                            0 <= obj.start() - verb.end() <= 43
                            and not any(re.search(rf"\b{re.escape(other)}\b", previous[verb.end():obj.start()], re.I)
                                        for other in required - {facet})
                            for obj in obj_hits for verb in action_hits
                        )
                        destination_only = bool(re.search(
                            rf"\b(?:location|destination|route|directions?)\s+of\s+(?:the\s+)?{re.escape(facet)}\b",
                            previous, re.I,
                        )) and not named_cost
                        negative_only = bool(re.search(
                            rf"\b(?:no|without|lack of)\s+{re.escape(facet)}\b", previous, re.I,
                        )) and not near_action and not named_cost
                        if (named_cost or near_action) and not negative_only and not destination_only:
                            relevant.insert(0, previous.strip())
                            found.add(facet)
                            break
                if relevant:
                    rendered = " ".join(relevant + [unit])

        if found:
            group = _document_answer_group(retrieved[doc_rank].document)
            matching[group].append((score, found, doc_rank, unit_index, rendered, source))

    # The ranks remain retrieval relevance order, but allow two sections from
    # the same original file to answer different coordinated objects.
    for group, available in sorted(matching.items(), key=lambda p: -max(x[0] for x in p[1])):
        remaining = set(required)
        chosen: list[tuple[float, set[str], int, int, str, str]] = []
        pool = available[:]
        while remaining and pool and len(chosen) < max(1, min(int(max_items), 6)):
            best = max(pool, key=lambda item: (len(item[1] & remaining), item[0]))
            if not best[1].intersection(remaining):
                break
            chosen.append(best)
            remaining -= best[1]
            pool.remove(best)
        if remaining:
            continue
        chosen.sort(key=lambda item: (item[2], item[3]))
        answer_parts = list(dict.fromkeys(item[4] for item in chosen))
        answer = "\n".join(f"- {part}" for part in answer_parts) if len(answer_parts) > 1 else answer_parts[0]
        if len(answer) > max(420, int(max_chars)):
            continue
        return answer, {
            "profile": "direct_fact", "items": len(answer_parts),
            "sources": sorted({item[5] for item in chosen}),
            "target": target, "decision": "accepted-compound-action-coverage",
            "covered_facets": sorted(required),
        }
    return "", {
        "profile": "direct_fact", "items": 0, "sources": [],
        "target": target, "decision": "compound-action-coverage-incomplete",
        "required_facets": sorted(required),
    }


def _coordinated_verbatim_facts(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Answer only *locally co-occurring*, explicit multi-part source facts.

    A single policy chunk sometimes states both an actor and a duration in
    adjacent sentences. A generic top-sentence extractor may discard one of
    them and unnecessarily invoke the LLM. This conservative proof requires
    both pieces in the SAME authorized chunk, a close sentence window, and
    question-topic overlap. It does not infer either fact or borrow evidence
    from a different rule or document.

    Other coordinated queries deliberately keep normal retrieval/synthesis.
    """
    q = _clean_text(question)
    # Independent interrogatives only: do NOT split titles such as
    # 'Personality Development and Professional Attitude Seminar'.
    parts = re.split(
        r",\s*and\s+(?=(?:who|what|when|where|how|which)\b)",
        q, maxsplit=2, flags=re.I,
    )
    if len(parts) != 2:
        return None
    first, second = (part.strip(" ?.!") for part in parts)
    interrogatives = (first.casefold(), second.casefold())
    actor_requested = any(re.match(r"^who\b", part) for part in interrogatives)
    duration_requested = any(re.match(r"^how\s+long\b", part) for part in interrogatives)
    if not (actor_requested and duration_requested):
        return None
    actor_re = re.compile(
        r"\b(?:employees?|staff|workers?|engineers?|associates?|"
        r"officers?|supervisors?|managers?|members?|participants?)\b"
        r".{0,170}\b(?:must|shall|required|attend|undergo|eligible|qualify)\b",
        re.I,
    )
    duration_re = re.compile(
        r"\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|"
        r"nine|ten|half)\s*(?:\(\s*\d+\s*\))?\s+"
        r"(?:hours?|days?|weeks?|months?|minutes?)\b",
        re.I,
    )
    topic_terms = {
        token for token in _meaningful_evidence_tokens(first)
        if token not in {"who", "must", "attend", "employees", "employee", "staff"}
    }
    choices: list[tuple[float, str, str]] = []
    for rank, item in enumerate(retrieved[:8]):
        doc = item.document
        if doc.source_type != "policy":
            continue
        metadata = doc.metadata or {}
        units = _sentence_units(_document_body_text(doc))
        actor_positions = [i for i, unit in enumerate(units) if actor_re.search(unit)]
        duration_positions = [i for i, unit in enumerate(units) if duration_re.search(unit)]
        if not actor_positions or not duration_positions:
            continue
        for a in actor_positions:
            for d in duration_positions:
                if abs(a - d) > 2:
                    continue
                # The duration sentence itself must refer to the named topic;
                # adjacency alone could confuse an unrelated 8-minute break
                # with the duration of a training program.
                duration_terms = set(_meaningful_evidence_tokens(units[d]))
                if topic_terms and not topic_terms.intersection(duration_terms):
                    continue
                combined = " ".join(units[i].strip() for i in sorted({a, d}))
                if len(combined) > min(max(280, int(max_chars)), 950):
                    continue
                # Require subject overlap with this specific subsection, not
                # an unrelated duration elsewhere in an extensive handbook.
                context = " ".join((
                    str(metadata.get("section") or ""),
                    " ".join(units[max(0, min(a,d)-1):max(a,d)+1]),
                ))
                support = set(_meaningful_evidence_tokens(context))
                shared = len(topic_terms.intersection(support))
                if topic_terms and shared < min(2, len(topic_terms)):
                    continue
                source = str(metadata.get("filename") or metadata.get("title") or doc.title)
                # Close evidence and stronger question-topic overlap win;
                # no generation or answers from evaluation keys.
                score = shared * 2 + _evidence_fit_bonus(question, doc) - abs(a-d) * .2 - rank * .02
                choices.append((score, combined, source))
    if not choices:
        return None
    choices.sort(key=lambda row: row[0], reverse=True)
    _, answer, source = choices[0]
    return answer, {
        "profile": "coordinated_fact", "items": 2,
        "sources": [source], "decision": "accepted-same-chunk-coordinated-facts",
        "covered_facets": ["actor", "duration"],
        "required_facets": ["actor", "duration"],
    }


def _evidence_token_roots(value: str) -> set[str]:
    """Match common grammatical plurals without changing source wording."""
    roots = set(_meaningful_evidence_tokens(value))
    for token in list(roots):
        if token.endswith("ies") and len(token) > 5:
            roots.add(token[:-3] + "y")
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            roots.add(token[:-1])
    return roots


def _explicit_question_contract_shape(question: str) -> str | None:
    """Identify questions whose requested facts cannot be represented by one
    merely topical sentence. This is syntax-based; no QA keys or policy facts.
    """
    q = _clean_text(question)
    if re.match(r"^if\b.+?,\s*(?:can|could|may|does|do|is|are|will|would)\b", q, re.I):
        return "conditional_yes_no"
    if re.search(r"\bwhen\s+and\s+where\b|\bwhere\s+and\s+when\b", q, re.I):
        return "event_time_place"
    if len(re.findall(r"\bwhen\s+(?:is|are|does|do|will)\b", q, re.I)) >= 2:
        return "parallel_dates"
    return None


def _explicit_question_contract_answer(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Return a verbatim, same-document proof of every explicitly requested part.

    An unproven contract returns None. The caller refuses generic extractive
    acceptance in that case, leaving authorized RAG/LLM synthesis to decide.
    Neither source rank, a matching title nor an unrelated date is sufficient.
    """
    shape = _explicit_question_contract_shape(question)
    if not shape:
        return None
    q = _clean_text(question)
    qtokens = _evidence_token_roots(q)
    named_sources: list[tuple[int, RetrievedDocument, str]] = []
    for rank, entry in enumerate(retrieved[:12]):
        doc = entry.document
        if doc.source_type != "policy":
            continue
        meta = doc.metadata or {}
        name = str(meta.get("filename") or meta.get("title") or doc.title)
        stem = re.sub(r"\.(?:docx?|pdf|txt)$", "", name, flags=re.I)
        title_terms = {
            (t[:-3] + "y") if t.endswith("ies") and len(t) > 5
            else t[:-1] if t.endswith("s") and not t.endswith("ss") and len(t) > 4
            else t
            for t in _meaningful_evidence_tokens(stem)
        } - {"policy", "document", "company", "system"}
        if len(title_terms) >= 2 and title_terms.issubset(qtokens):
            named_sources.append((rank, entry, name))

    if shape == "conditional_yes_no":
        match = re.match(
            r"^if\s+(.+?),\s*(?:can|could|may|does|do|is|are|will|would)\b",
            q, re.I,
        )
        if not match:
            return None
        premise = match.group(1)
        # Negative claims require proof of negation, not inference from a
        # positive membership rule. Do not guess a yes/no for false premises.
        if re.search(r"\b(?:not|never|without|no|fails?\s+to|doesn.t)\b", premise, re.I):
            return None
        premise_terms = set(_meaningful_evidence_tokens(premise)) - {
            "employee", "employees", "company", "person", "persons",
            "staff", "worker", "workers", "the", "a", "an",
        }
        if len(premise_terms) < 2:
            return None
        for _, entry, name in named_sources:
            units = _sentence_units(_document_body_text(entry.document))
            scope_text = " ".join(units)
            if not re.search(
                r"\b(?:implemented\s+to\s+the\s+following|"
                r"applies?\s+to\s+the\s+following|"
                r"eligible\s+(?:employees?|persons?)|"
                r"qualif(?:y|ies|ied)\s+(?:for|under))\b",
                scope_text, re.I,
            ):
                continue
            members = [u for u in units if re.search(
                r"\b(?:employees?|persons?|staff|participants?|members?)\s+"
                r"(?:who|that|receiving)|\bemployees?\s+(?:are|given)\s+", u, re.I,
            )]
            for candidate in units:
                normalized = _evidence_token_roots(candidate)
                overlap = premise_terms & normalized
                if len(overlap) < 2 or len(overlap) / len(premise_terms) < .65:
                    continue
                if re.search(r"\b(?:not|never|without|no)\b", candidate, re.I):
                    continue
                best_member = max(
                    members,
                    key=lambda member: len(
                        _evidence_token_roots(member) & normalized
                    ), default="",
                )
                if not best_member:
                    continue
                # At least two shared subject terms must connect the named
                # condition to a member of this very coverage enumeration.
                if len(_evidence_token_roots(best_member) & normalized) < 2:
                    continue
                answer = "Yes. The policy states:\n- " + best_member.strip() + "\n- " + candidate.strip()
                if len(answer) <= max_chars:
                    return answer, {
                        "profile": "yes_no", "items": 2, "sources": [name],
                        "decision": "accepted-conditional-coverage-proof",
                        "covered_facets": ["membership", "condition"],
                        "required_facets": ["membership", "condition"],
                    }

    if shape == "event_time_place":
        event_re = re.compile(
            r"\b(?:during|at|in|on)\s+(?:the\s+)?"
            r"(?:[a-z-]+\s+){0,4}"
            r"(?:briefings?|meetings?|ceremon(?:y|ies)|part(?:y|ies)|"
            r"events?|venues?|hall|office|room|location|auditorium|"
            r"gatherings?|celebrations?|sessions?)\b",
            re.I,
        )
        for _, entry, name in named_sources:
            units = _sentence_units(_document_body_text(entry.document))
            event_units = [(index, u) for index, u in enumerate(units)
                           if event_re.search(u)]
            if not event_units:
                continue
            # The location phrase must govern presentation/conduct/award of
            # the *asked activity*, not attendance at an unrelated celebration.
            action_re = re.compile(
                r"\b(?:present\w*|giv(?:en|ing)|award(?:ed|ing)?|"
                r"conduct\w*|held|schedul\w*|acknowledg\w*|announc\w*)\b",
                re.I,
            )
            qsubject = _evidence_token_roots(question) - {
                "when", "where", "employee", "employees", "company",
                "given", "held", "presented", "award", "awards",
            }
            primary = [
                (index, unit) for index, unit in event_units
                if action_re.search(unit)
                and (qsubject & _evidence_token_roots(unit)
                     or re.search(r"\b(?:awarding|awarded|presented)\b", unit, re.I))
            ]
            if not primary:
                continue
            # Supplementary event acknowledgements must be physically nearby
            # in the same source chunk and refer to an additional classification
            # or follow-up announcement, rather than an unrelated event.
            primary_index = primary[0][0]
            connected = [unit for index, unit in event_units
                         if index == primary_index or (
                             0 < index - primary_index <= 3
                             and action_re.search(unit)
                             and re.search(
                                 r"\b(?:also|further|additional(?:ly)?|"
                                 r"classifications?|levels?|tiers?|"
                                 r"acknowledg\w*|announc\w*)\b",
                                 unit, re.I,
                             )
                         )]
            answer_units = list(dict.fromkeys(connected))[:4]
            answer = "\n".join(answer_units)
            if len(answer) <= max_chars:
                return answer, {
                    "profile": "date_or_time", "items": len(answer_units),
                    "sources": [name],
                    "decision": "accepted-explicit-event-time-place",
                    "covered_facets": ["when", "where"],
                    "required_facets": ["when", "where"],
                }

    if shape == "parallel_dates":
        pair = re.search(
            r"\bwhen\s+(?:is|are)\s+(?:the\s+)?(.+?)\s+"
            r"(?:paid|given|released|distributed)\s*,?\s+and\s+"
            r"when\s+(?:is|are)\s+(?:the\s+)?(.+?)\s+"
            r"(?:paid|given|released|distributed)\b",
            q, re.I,
        )
        if not pair:
            return None
        topics = ["".join(_tokenize(part)) for part in pair.groups()]
        if any(len(topic) < 7 for topic in topics) or topics[0] == topics[1]:
            return None
        groups: dict[tuple[object, ...], list[RetrievedDocument]] = defaultdict(list)
        for item in retrieved[:12]:
            if item.document.source_type == "policy":
                groups[_document_answer_group(item.document)].append(item)
        date_re = re.compile(
            r"\b(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            re.I,
        )
        paid_re = re.compile(r"\b(?:paid|given|released|distributed|provided)\b", re.I)
        deadline_re = re.compile(r"\b(?:not\s+later\s+than|no\s+later\s+than|by|on|before|until)\b", re.I)
        for group_items in groups.values():
            proofs: list[tuple[str, str]] = []
            for topic in topics:
                found = []
                for item in group_items:
                    doc = item.document
                    section = str((doc.metadata or {}).get("section") or "")
                    units = _sentence_units(_document_body_text(doc))
                    for unit in units:
                        context = "".join(_tokenize(section + " " + unit))
                        if topic not in context:
                            continue
                        if paid_re.search(unit) and deadline_re.search(unit) and date_re.search(unit):
                            found.append((unit.strip(), str((doc.metadata or {}).get("filename") or doc.title)))
                if not found:
                    break
                # The deadline must be in a sentence attached to THIS topic,
                # not only in a neighboring document's unrelated date range.
                proofs.append(found[0])
            if len(proofs) == len(topics):
                answer = "\n".join("- " + text for text, _ in proofs)
                if len(answer) <= max_chars:
                    return answer, {
                        "profile": "date_or_time", "items": len(proofs),
                        "sources": sorted({name for _, name in proofs}),
                        "decision": "accepted-parallel-topic-deadlines",
                        "covered_facets": ["first_deadline", "second_deadline"],
                        "required_facets": ["first_deadline", "second_deadline"],
                    }
    return None


def _structurally_complete_policy_evidence(
    query: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Use intact *authorized* policy clauses when extraction would lose siblings.

    No policy names, benefit thresholds, answer keys, or real QA case IDs are
    embedded. The three narrow structures are: explicit coverage enumeration,
    chronological ``after -> then`` policy steps, and a paired duration and
    approval requirement within one original chunk. They fail closed when a
    source is ambiguous, split across companies, or incomplete.
    """
    question = _clean_text(query)
    question_tokens = set(_meaningful_evidence_tokens(question))
    profile = _question_evidence_profile(question)
    eligible_ask = bool(re.search(
        r"\bwho\s+(?:is|are|can|may)\s+(?:eligible|qualified|entitled)\b|"
        r"\bwho\s+qualifies\b|\brequirements?\s+to\s+qualify\b",
        question, re.I,
    ))
    time_ask = bool(re.match(r"^\s*when\b", question, re.I)) and not re.search(
        r"\band\s+where\b", question, re.I,
    )
    paired_ask = bool(re.search(r"^\s*how\s+long\b", question, re.I)) and bool(
        re.search(r",\s*and\s+what\s+(?:is|are)\s+required\s+for\b", question, re.I)
    )
    if not (eligible_ask or time_ask or paired_ask):
        return None

    # 'Best search rank' is insufficient when the top source is a generic
    # handbook. Prefer a source explicitly *named* in the question, but never
    # import text outside the already authorized retrieved list.
    entries = []
    for rank, result in enumerate(retrieved[:12]):
        doc = result.document
        if doc.source_type != "policy":
            continue
        meta = doc.metadata or {}
        filename = str(meta.get("filename") or meta.get("title") or doc.title)
        stem = re.sub(r"\.(?:docx?|pdf|txt)$", "", filename, flags=re.I)
        source_terms = {t for t in _meaningful_evidence_tokens(stem)
                        if t not in {"policy", "document", "system", "company"}}
        title_match = len(source_terms) >= 2 and source_terms.issubset(question_tokens)
        entries.append((rank, result, filename, title_match))

    if eligible_ask:
        # A complete policy 'Coverage' article followed by a classification
        # table is a stronger answer than 2-3 high-scoring isolated sentences.
        # Require a named source and an explicit enumeration; retain related
        # table rows only from that SAME original document and company.
        for rank, result, filename, title_match in entries:
            if not title_match:
                continue
            body = _document_body_text(result.document)
            if not re.search(r"\bcoverage\b", body, re.I):
                continue
            if not re.search(r"\b(?:appl(?:y|ies)|eligible|qualif\w*|implemented to|cover\w*)\b", body, re.I):
                continue
            units = _sentence_units(body)
            members = [u for u in units if re.match(r"^\s*\d+[.)]\s+", u)
                       and re.search(r"\b(?:employees?|staff|persons?|participants?|members?)\b", u, re.I)]
            if len(members) < 2:
                continue
            # Keep all of the coverage article (including the conditions
            # attached to numbered items), not a disconnected subset.
            coverage_text = body.strip()
            if len(coverage_text) > max_chars:
                continue
            group = _document_answer_group(result.document)
            siblings = []
            for _, other, _, _ in entries:
                if _document_answer_group(other.document) != group or other is result:
                    continue
                other_body = _document_body_text(other.document)
                if not re.search(r"\b(?:classification|level|category|type)\b", other_body, re.I):
                    continue
                for unit in _sentence_units(other_body):
                    if re.search(r"\b(?:employees?|persons?|participants?|staff)\s+who\b", unit, re.I):
                        # Preserve the qualifying condition, not any price or
                        # incentive column adjacent to it in a table.
                        columns = [part.strip() for part in unit.split(" | ")]
                        clause = next((part for part in columns if re.search(
                            r"\b(?:employees?|persons?|participants?|staff)\s+who\b",
                            part, re.I,
                        )), "")
                        # The same membership can be restated in a nearby
                        # classification table with slightly different spacing.
                        # Avoid duplicating a rule already in the coverage list.
                        normalized_coverage = " ".join(_tokenize(coverage_text))
                        clause_tokens = _tokenize(clause)
                        duplicated = len(clause_tokens) >= 7 and (
                            " ".join(clause_tokens[:7]) in normalized_coverage
                        )
                        if clause and not duplicated and len(clause) <= 280:
                            siblings.append(clause)
            siblings = list(dict.fromkeys(siblings))[:4]
            if not siblings and len(members) < 3:
                # Two coverage conditions plus an unproven classification
                # row is insufficient to claim complete source evidence.
                continue
            answer = coverage_text + "\n" + "\n".join(siblings)
            if len(answer) > max_chars:
                continue
            return answer, {
                "profile": "eligibility", "items": len(members) + len(siblings),
                "sources": [filename], "decision": "accepted-authorized-coverage-and-classification",
            }

    if time_ask:
        for _, result, filename, title_match in entries:
            if not title_match:
                continue
            units = _sentence_units(_document_body_text(result.document))
            for index, unit in enumerate(units):
                # A temporal trigger grounded in a named policy; the next
                # action must literally signal chronological continuation.
                if not re.search(r"\bafter\b.{0,140}\b(?:announc\w*|notif\w*|inform\w*|approv\w*|receiv\w*|complet\w*)", unit, re.I):
                    continue
                topic = set(_meaningful_evidence_tokens(unit)) & question_tokens
                topic -= {"employee", "employees", "given", "awarded", "announced", "results"}
                if not topic:
                    continue
                for following in units[index + 1:index + 4]:
                    if re.match(r"^\s*Article\s+\w+", following, re.I):
                        break
                    if re.match(r"^\s*Section\s+\w+[.:]?\s*$", following, re.I):
                        continue
                    if re.search(r"\b(?:shall|will|must)\s+then\b|^\s*then\b", following, re.I):
                        answer = unit.strip() + "\n" + following.strip()
                        if len(answer) <= max_chars:
                            return answer, {
                                "profile": "date_or_time", "items": 2,
                                "sources": [filename], "decision": "accepted-linked-after-then-procedure",
                            }
                    break

    if paired_ask:
        amount = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty)"
        measure = re.compile(rf"\b{amount}\s*(?:\(\s*\d+\s*\))?\s+(?:minutes?|hours?|days?|weeks?|months?)\b", re.I)
        for _, result, filename, _ in entries:
            body = _document_body_text(result.document)
            units = _sentence_units(body)
            context = str((result.document.metadata or {}).get("section") or "")
            context_terms = set(_meaningful_evidence_tokens(context))
            for pos, duration in enumerate(units):
                if not measure.search(duration):
                    continue
                # No joining text that crosses a new numbered policy section.
                window = []
                for candidate in units[pos:pos + 5]:
                    if window and re.match(r"^\s*(?:Section|Article)\s+\w+[.:]?", candidate, re.I):
                        break
                    window.append(candidate)
                    seen = " ".join(window)
                    if (re.search(r"\b(?:required|must|shall|need)\b", seen, re.I)
                            and re.search(r"\b(?:approv\w*|authoriz\w*|permission)\b", seen, re.I)):
                        break
                fact_text = " ".join(window)
                if not (re.search(r"\b(?:required|must|shall|need)\b", fact_text, re.I)
                        and re.search(r"\b(?:approv\w*|authoriz\w*|permission)\b", fact_text, re.I)):
                    continue
                overlap = question_tokens & (
                    context_terms | set(_meaningful_evidence_tokens(fact_text))
                )
                if len(overlap) < 3:
                    continue
                rendered_units = [x.strip() for x in window if not re.fullmatch(
                    r"[a-zA-Z][.)]", x.strip(), re.I,
                )]
                answer = "\n".join(rendered_units)
                if len(answer) <= max_chars:
                    return answer, {
                        "profile": "duration_or_count", "items": len(rendered_units),
                        "sources": [filename], "decision": "accepted-coherent-duration-and-requirement",
                    }
    return None


# Structural workflow extraction is deliberately limited to an explicit,
# named subject and at least two requested procedure verbs. Unlike lexical
# sentence ranking, it cannot mix neighboring (a)/(b) procedures.
_WORKFLOW_ACTIONS: dict[str, re.Pattern[str]] = {
    "organize": re.compile(r"\b(?:organiz|organis|arrang|coordinat|conduct|plan)\w*", re.I),
    "approve": re.compile(r"\b(?:approv|authoriz|authoris|sanction)\w*", re.I),
    "review": re.compile(r"\b(?:review|check|verif|inspect)\w*", re.I),
    "process": re.compile(r"\b(?:process|handl|administer)\w*", re.I),
    "prepare": re.compile(r"\b(?:prepar|draft|creat)\w*", re.I),
    "schedule": re.compile(r"\b(?:schedul|timetabl|calendar)\w*", re.I),
    "evaluate": re.compile(r"\b(?:evaluat|assess|apprais)\w*", re.I),
    "report": re.compile(r"\b(?:report|notif|inform|escalat)\w*", re.I),
    "submit": re.compile(r"\b(?:submit|file|forward)\w*", re.I),
    "implement": re.compile(r"\b(?:implement|execut|carry\s+out)\w*", re.I),
    "manage": re.compile(r"\b(?:manag|oversee|supervis)\w*", re.I),
}
_WORKFLOW_VERB = (
    r"organiz(?:ed|e)|organis(?:ed|e)|arrang(?:ed|e)|approv(?:ed|e)|"
    r"review(?:ed)?|check(?:ed)?|process(?:ed)?|handl(?:ed|e)|"
    r"prepar(?:ed|e)|schedul(?:ed|e)|evaluat(?:ed|e)|"
    r"report(?:ed)?|submit(?:ted)?|implement(?:ed)?|manag(?:ed|e)|conduct(?:ed)?"
)
_WORKFLOW_BOUNDARY = re.compile(
    r"^\s*(?:\([a-z]\)\s+\S|(?:section|article)\s+\d+[.\s:]|"
    r"\d+(?:\.\d+)+\s+\D)", re.I,
)
_WORKFLOW_NAMED_SUBSECTION = re.compile(r"^\s*\([a-z]\)\s+(.+)$", re.I)
_WORKFLOW_STEP = re.compile(r"^\s*(\d{1,2})[.)]\s+\S")


def _scoped_workflow_question(question: str) -> tuple[str, tuple[str, ...]] | None:
    """Derive a passive workflow subject and distinct requested actions.

    This is a grammatical contract only; no company titles, expected answers,
    or evaluation cases are used for classification or retrieval.
    """
    q = _clean_text(question).strip().rstrip("?. ")
    match = re.match(
        rf"^how\s+(?:is|are|was|were)\s+(.{{6,140}}?)\s+"
        rf"({_WORKFLOW_VERB})(?:\s+and\s+({_WORKFLOW_VERB}))+?$",
        q, re.I,
    )
    if not match:
        return None
    subject = match.group(1).strip()
    suffix = q[match.start(2):]
    # Suffix comes from the first action through the final coordinating action.
    requested = tuple(
        family for family, pattern in _WORKFLOW_ACTIONS.items()
        if pattern.search(suffix)
    )
    if len(requested) < 2:
        return None
    return subject, requested


def _scoped_workflow_evidence(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Return a whole named, numbered procedure from one authorized chunk.

    An adjacent procedure (non-technical vs technical, new vs renewal, etc.)
    must not provide the requested actors or approvals. The existing retrieval
    has already enforced company and role permissions; this function never
    imports text from outside those returned policy chunks.
    """
    parsed = _scoped_workflow_question(question)
    if parsed is None:
        return None
    subject, required_actions = parsed
    # Normalize singular/plural variants to *one* topic key each, otherwise
    # two generic words can outweigh a missing named subject ('satellite').
    topic_stopwords = {"policy", "procedure", "process", "system",
                       "company", "employee", "employees"}

    def topic_terms(value: str) -> set[str]:
        terms = set()
        for token in _meaningful_evidence_tokens(value):
            if token in topic_stopwords:
                continue
            if token.endswith("ies") and len(token) > 5:
                token = token[:-3] + "y"
            elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
                token = token[:-1]
            terms.add(token)
        return terms

    subject_terms = topic_terms(subject)
    if len(subject_terms) < 2:
        return None
    source_negative = bool(re.search(r"\b(?:non[ -]|not\s+)\w+", subject, re.I))
    candidates = []
    for rank, retrieved_item in enumerate(retrieved[:12]):
        doc = retrieved_item.document
        if doc.source_type != "policy":
            continue
        meta = doc.metadata or {}
        lines = [line.strip() for line in _document_body_text(doc).splitlines() if line.strip()]
        for i, line in enumerate(lines):
            match = _WORKFLOW_NAMED_SUBSECTION.match(line)
            if not match:
                continue
            heading = match.group(1).strip()
            heading_terms = topic_terms(heading)
            shared_terms = subject_terms & heading_terms
            if len(shared_terms) < 2 or not subject_terms.issubset(heading_terms):
                continue
            heading_negative = bool(re.search(r"\b(?:non[ -]|not\s+)\w+", heading, re.I))
            if source_negative != heading_negative:
                continue
            end = next((j for j in range(i + 1, len(lines))
                        if _WORKFLOW_BOUNDARY.match(lines[j])), len(lines))
            # Preserve numbered steps: they are not subsection boundaries.
            # The generic boundary expression recognizes headings, not 1./2.
            subsection = lines[i:end]
            steps = [int(m.group(1)) for row in subsection
                     if (m := _WORKFLOW_STEP.match(row))]
            if len(steps) < 2 or steps != list(range(1, len(steps) + 1)):
                continue
            # A source chunk that continues elsewhere cannot prove all steps
            # unless a *subsequent explicit section header* closed this one.
            if end == len(lines) and bool(int(meta.get("continuation_after") or 0)):
                continue
            body = "\n".join(subsection)
            if any(not _WORKFLOW_ACTIONS[action].search(body)
                   for action in required_actions):
                continue
            if len(body) > max_chars:
                continue  # Never silently truncate mandatory policy steps.
            source = str(meta.get("filename") or meta.get("title") or doc.title)
            candidates.append((len(shared_terms) / len(subject_terms), -rank,
                               body, source, len(steps)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, _, body, source, count = candidates[0]
    return body, {
        "profile": "procedure", "items": count, "sources": [source],
        "decision": "accepted-scoped-numbered-workflow",
        "covered_facets": list(required_actions),
        "required_facets": list(required_actions),
    }


def _bounded_linked_policy_clauses(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Preserve connected facts from one authorized policy chunk, verbatim.

    This is a general *question shape* and *source structure* validator, not a
    policy lookup. It covers paired who/how facts, conditional priority lists,
    and explicit time rules with their adjacent exception. Any missing piece,
    ambiguous topic, mixed source, or oversized source falls back to the
    existing evidence-gated synthesis instead of inventing the missing part.
    """
    q = _clean_text(question)
    if re.match(r"^who\b.+?\band\s+how\b", q, re.I):
        shape = "actor_and_evaluation"
    elif re.match(r"^if\b.+?,\s*who\b", q, re.I):
        shape = "conditional_priority"
    elif re.match(r"^when\s+(?:should|must|is|are)\b", q, re.I):
        shape = "time_with_exception"
    elif re.match(r"^how\s+does\s+.+?\b(?:policy|scheme|program|system)\s+work\b", q, re.I):
        shape = "named_policy_with_example"
    else:
        return None

    q_terms = _evidence_token_roots(q) - {
        "employee", "employees", "company", "should", "would", "required",
        "who", "what", "where", "when", "how", "which", "their", "during",
        "work", "working", "time", "used", "use", "responsible", "last",
    }
    candidates: list[tuple[float, int, str, str, int]] = []
    for rank, item in enumerate(retrieved[:12]):
        doc = item.document
        if doc.source_type != "policy":
            continue
        body = _document_body_text(doc)
        meta = doc.metadata or {}
        source = str(meta.get("filename") or meta.get("title") or doc.title)
        section = str(meta.get("section") or "")
        if not body or len(body) > 18000:
            continue
        # The matched facts must live inside a single original chunk. Never
        # concatenate policy versions, tenants, or sections to claim coverage.
        if shape == "actor_and_evaluation":
            if not re.search(r"\b(?:evaluat|assess|apprais|review)\w*", q, re.I):
                continue
            chunks = re.split(r"(?=\([a-z]\)\s+)", body, flags=re.I)
            pairs = [(left, right) for left, right in zip(chunks, chunks[1:])
                     if re.match(r"^\([a-z]\)\s+", left, re.I)
                     and re.match(r"^\([a-z]\)\s+", right, re.I)]
            requested_subject = re.split(r",?\s+and\s+how\b", q, maxsplit=1, flags=re.I)[0]
            topic = re.search(
                r"\b(?:attend|undergo|participate\s+in|enroll\s+in|join)\s+(.+)$",
                requested_subject, re.I,
            )
            if not topic:
                continue
            subject_terms = _evidence_token_roots(topic.group(1))
            if len(subject_terms) < 2:
                continue
            for first, second in pairs:
                # The specific named subject must occur in the *actor* clause.
                # Matching the general section label or two generic keywords
                # could otherwise import the evaluation for a sibling course.
                if not subject_terms.issubset(_evidence_token_roots(first)):
                    continue
                if re.search(r"(?m)^\s*(?:Section|Article)\s+\d+", first + "\n" + second, re.I):
                    continue
                if not re.search(r"\b(?:required|must|shall)\b.{0,100}\b(?:attend|undergo|participat|enroll|join)\w*", first, re.I | re.S):
                    continue
                if not re.search(r"\b(?:evaluat|assess|apprais|review)\w*", second, re.I):
                    continue
                # Each clause must have a different, requested function.
                if not re.search(r"\b(?:employees?|staff|personnel|trainees?|participants?|officers?|managers?|workers?|members?|technicians?|engineers?)\b", first, re.I):
                    continue
                context_terms = _evidence_token_roots(section + " " + first + " " + second)
                overlap = len(q_terms & context_terms)
                if overlap < 2:
                    continue
                answer = first.strip() + "\n" + second.strip()
                if len(answer) <= max_chars:
                    candidates.append((overlap, -rank, answer, source, 2))

        elif shape == "conditional_priority":
            # A condition introducing a numbered precedence/tie-break list;
            # keep all consecutive branches, not just its highest-ranked line.
            intro = re.search(
                r"\([a-z]\)\s+If\b.{15,290}?\b(?:guidelines?|rules?|priorit(?:y|ies)|criteria|apply)\b[^:]{0,55}:\s*",
                body, re.I | re.S,
            )
            if not intro:
                continue
            tail = body[intro.end():]
            boundary = re.search(r"\n\s*(?:Article|Section)\s+\w|\([a-z]\)\s+[A-Za-z]", tail, re.I)
            if boundary:
                tail = tail[:boundary.start()]
            matches = list(re.finditer(r"\((\d{1,2})\)\s+", tail))
            if not 2 <= len(matches) <= 8:
                continue
            indexes = [int(m.group(1)) for m in matches]
            if indexes != list(range(1, len(indexes) + 1)):
                continue
            snippet = body[intro.start():intro.end()] + tail
            if not re.search(r"\bif\b", tail, re.I):
                continue
            overlap = len(q_terms & _evidence_token_roots(snippet + " " + section))
            if overlap < 2:
                continue
            if len(snippet) <= max_chars:
                candidates.append((overlap, -rank, snippet.strip(), source, len(matches)))

        elif shape == "named_policy_with_example":
            # A complete worked-example subsection is often the missing half
            # of an explanatory answer. The next explicit Section/Article
            # boundary establishes that no example lines were cut off.
            subject_match = re.match(
                r"^how\s+does\s+(?:the\s+)?(.+?)\s+(?:policy|scheme|program|system)\s+work\b",
                q, re.I,
            )
            if not subject_match:
                continue
            subject_terms = _evidence_token_roots(subject_match.group(1))
            title = re.search(
                r"\bArticle\s+(?:[IVX]+|\d+)\s*[-:.]\s*(.+?)\s+Section\s+1\s*[.:]",
                body, re.I | re.S,
            )
            if not title or not subject_terms or not subject_terms.issubset(
                _evidence_token_roots(title.group(1))
            ):
                continue
            remaining = body[title.end():]
            boundary = re.search(r"\b(?:Section\s+2\s*[.:]|Article\s+(?:[IVX]+|\d+)\s*[-:.])", remaining, re.I)
            if not boundary:
                continue
            clause = body[title.start():title.end()] + remaining[:boundary.start()]
            if not re.search(r"\bexamples?\s*[:.]", clause, re.I):
                continue
            if not re.search(r"\b(?:allow|shall|must|scheme|may|schedule|work|start|end)\w*\b", clause, re.I):
                continue
            if len(re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}:\d{2}\b", clause, re.I)) < 2:
                continue
            if len(clause) <= max_chars:
                candidates.append((len(subject_terms) + 3, -rank, clause.strip(), source, 2))

        else:  # time_with_exception
            units = _sentence_units(body)
            clock = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}:\d{2}\b", re.I)
            for index, first in enumerate(units[:-1]):
                second = units[index + 1]
                if not clock.search(first) or not re.search(r"\bunless\b", second, re.I):
                    continue
                if re.match(r"^\s*(?:Section|Article)\s+\w", second, re.I):
                    continue
                overlap = len(q_terms & _evidence_token_roots(first + " " + section))
                if overlap < 2:
                    continue
                snippet = first.strip() + "\n" + second.strip()
                if len(snippet) <= max_chars:
                    candidates.append((overlap, -rank, snippet, source, 2))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    overlap, _, text, source, count = candidates[0]
    # If distinct documents tie as plausible sources for a clause, do not
    # silently choose one potentially conflicting rule.
    competitors = {(entry[3], entry[2]) for entry in candidates
                   if entry[0] == overlap}
    if len({name for name, _ in competitors}) > 1:
        return None
    return text, {
        "profile": "linked_policy_clauses", "items": count,
        "sources": [source], "decision": "accepted-bounded-linked-clauses",
        "covered_facets": [shape], "required_facets": [shape],
    }


def _contiguous_conditional_list_answer(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Recover a numbered conditional rule split across adjacent policy chunks.

    Paragraph-extraction may promote an ``If ... guidelines apply:`` preamble
    to a section heading while its numbered rule clauses occupy the following
    source chunk.  Only consecutive fragments of one *already authorized*
    document, version, company and role may be joined.  Structural boundaries
    and a complete ordinal sequence are mandatory; never guess omitted tiers.
    """
    query = _clean_text(question)
    if not re.match(r"^if\b.{8,220}\bwho\b", query, re.I):
        return None

    # A heading can be in either the body or metadata; no company rule strings
    # or QA questions are used as decision keys.
    intro_re = re.compile(
        r"(?:\([a-z]\)\s*)?\bif\b.{8,300}?"
        r"\b(?:following\s+)?(?:rules?|guidelines?|criteria|priorit(?:y|ies))"
        r"\b[^:.]{0,75}:\s*",
        re.I | re.S,
    )
    heading_intro_re = re.compile(
        r"(?:\([a-z]\)\s*)?\bif\b.{8,300}?"
        r"\b(?:following\s+)?(?:rules?|guidelines?|criteria|priorit(?:y|ies))"
        r"\b[^:/]{0,75}\bapply\b\s*:?(?=\s*(?:/|$))", re.I | re.S,
    )
    ordinal_re = re.compile(r"\(\s*(\d{1,2})\s*\)\s+")
    boundary_re = re.compile(r"\b(?:Section\s*\d+\s*[.:]|Article\s+[IVX0-9]+\s*[-:.])", re.I)
    groups: dict[tuple[object, ...], list[tuple[int, RetrievedDocument]]] = defaultdict(list)
    for item in retrieved[:14]:
        doc = item.document
        meta = doc.metadata or {}
        key = str(meta.get("file_key") or "")
        try:
            index = int(meta.get("chunk_index") or 0)
            total = int(meta.get("total_chunks") or 0)
        except (TypeError, ValueError):
            continue
        if (doc.source_type != "policy" or not key.startswith("policy:")
                or not meta.get("policy_id") or not meta.get("policy_document_id")
                or not 1 <= index <= total or total < 2):
            continue
        identity = (
            doc.company_id, doc.role_scope, key,
            str(meta.get("version") or ""),
            str(meta.get("filename") or ""),
            str(meta.get("policy_id")), str(meta.get("policy_document_id")),
        )
        groups[identity].append((index, item))

    plausible: list[tuple[int, str, str, int, str]] = []
    query_roots = _evidence_token_roots(query)
    for identity, indexed in groups.items():
        by_index: dict[int, RetrievedDocument] = {}
        for index, item in indexed:
            # Conflicting replicas of a chunk are not safe to reconcile.
            if index in by_index and _document_body_text(by_index[index].document) != _document_body_text(item.document):
                by_index = {}
                break
            by_index[index] = item
        for index, current in sorted(by_index.items()):
            preceding = _document_body_text(current.document).strip()
            heading = str((current.document.metadata or {}).get("section") or "")
            next_item = by_index.get(index + 1)
            if not next_item:
                continue
            subsequent = _document_body_text(next_item.document).strip()
            next_heading = str((next_item.document.metadata or {}).get("section") or "")
            if not subsequent or not preceding:
                continue
            # Preamble can be a metadata heading, a body clause, or the
            # trailing part of the immediately preceding physical chunk.
            matches = list(intro_re.finditer(preceding))
            if matches:
                anchor = matches[-1].group(0).strip()
                remaining = preceding[matches[-1].end():].strip()
            else:
                matches = list(intro_re.finditer(heading)) or list(heading_intro_re.finditer(heading))
                if not matches:
                    # The parser can make an introductory paragraph the
                    # NEXT chunk's heading, with its numbered body directly
                    # below it. Prove the topic using the previous chunk.
                    matches = list(intro_re.finditer(next_heading)) or list(heading_intro_re.finditer(next_heading))
                if not matches:
                    continue
                anchor = matches[-1].group(0).strip()
                # Section headings are context, not a prefix to the list.
                remaining = ""

            # Never join two unrelated sections merely because they are next
            # to one another. The numbered list must begin immediately after
            # the conditional preamble, possibly at the next chunk start.
            joined = (remaining + "\n" + subsequent).strip()
            if re.search(r"\bSection\s*\d+", joined[:70], re.I):
                continue
            first = ordinal_re.search(joined)
            if not first or first.start() > 65 or int(first.group(1)) != 1:
                continue
            first_boundary = boundary_re.search(joined, first.end())
            if not first_boundary:
                # Without an explicit next section the retrieved tail may be
                # truncated and its unseen final branches cannot be proved.
                continue
            bounded = joined[:first_boundary.start()].strip()
            ordinals = list(ordinal_re.finditer(bounded))
            numbers = [int(m.group(1)) for m in ordinals]
            if not (2 <= len(numbers) <= 8 and numbers == list(range(1, len(numbers) + 1))):
                continue
            if not re.search(r"\b(?:if|when|otherwise|same|equal|tie)\b", bounded[ordinals[1].start():], re.I):
                continue
            if any(
                not bounded[m.end():(ordinals[pos + 1].start() if pos + 1 < len(ordinals) else len(bounded))].strip()
                for pos, m in enumerate(ordinals)
            ):
                continue
            context = " ".join((heading, preceding[-550:], next_heading, anchor, bounded))
            evidence_roots = _evidence_token_roots(context)
            overlap = len(query_roots & evidence_roots)
            if overlap < 3:
                continue
            # Preserve full numbered clauses verbatim. The preamble is copied
            # from the same authorized policy source, not authored by QA.
            answer = anchor + "\n" + bounded
            if len(answer) > max_chars:
                continue
            plausible.append((overlap, identity[4], answer, len(numbers), identity[2]))

    if not plausible:
        return None
    plausible.sort(key=lambda x: (x[0], x[3]), reverse=True)
    best_score = plausible[0][0]
    # Distinct file/version candidates with equal evidence support are
    # ambiguous; do not arbitrarily select a conflicting policy.
    if len({(p[4], p[2]) for p in plausible if p[0] == best_score}) != 1:
        return None
    _, source, answer, steps, file_key = plausible[0]
    return answer, {
        "profile": "linked_policy_clauses", "items": steps,
        "sources": [source], "file_key": file_key,
        "decision": "accepted-contiguous-conditional-list",
        "covered_facets": ["conditional_priority_chain"],
        "required_facets": ["conditional_priority_chain"],
    }


def _verified_source_statement_or_examples(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Verbatim policy statement or definition with an explicit examples list.

    This is source-structure matching, not a map of user questions to policy
    answers. Accept only already-authorized, subject-matched uploaded policy
    chunks. Refuse ambiguous matches and incomplete/truncated source text.
    """
    clean = _normalized_phrase_text(question)
    policy_purpose = bool(
        re.search(r"\b(?:purpose|aims?|objectives?)\b", clean)
        and re.search(r"\bpolicy\b", clean)
    )
    requested_examples = bool(
        re.search(r"\b(?:examples?|activities|behaviou?rs?|conduct|actions)\b", clean)
        and re.search(r"\b(?:violat|breach|prohibit|misconduct)", clean)
    )
    if not (policy_purpose or requested_examples):
        return None
    request_terms = set(_meaningful_evidence_tokens(question))
    generic = {
        "company", "companies", "policy", "policies", "purpose", "aim", "aims",
        "objective", "objectives", "activities", "activity", "behaviors",
        "behaviours", "examples", "example", "considered", "violations",
        "violation", "breach", "breaches", "prohibited", "employee", "employees",
        "during", "regular", "what", "does", "provide", "under", "include",
    }
    subject_terms = request_terms - generic
    options: list[tuple[float, tuple[object, ...], str, str]] = []
    for item in retrieved[:14]:
        doc = item.document
        if doc.source_type != "policy" or not str((doc.metadata or {}).get("file_key") or "").startswith("policy:"):
            continue
        meta = doc.metadata or {}
        body = _document_body_text(doc).strip()
        if not 50 <= len(body) <= max_chars:
            continue
        heading = str(meta.get("section") or "")
        source = str(meta.get("filename") or meta.get("title") or doc.title)
        stem = re.sub(r"\.(?:docx?|pdf|txt)$", "", source, flags=re.I)
        source_terms = set(_meaningful_evidence_tokens(stem)) - {"policy", "statement", "company"}
        body_terms = set(_meaningful_evidence_tokens(heading + " " + body))
        if policy_purpose:
            # A nested procedure's 'Purpose' subsection is not the whole
            # company's policy statement. Require the uniquely named source
            # and the actual top-level Policy Statement chunk.
            if len(source_terms) < 2 or not source_terms.issubset(request_terms):
                continue
            if not re.match(r"^\s*policy statement\b", heading, re.I):
                continue
            if not re.search(r"\b(?:policy|principles?|founded|commitment|aims?|recogniz|values?)\b", body, re.I):
                continue
            if not re.search(r"\b(?:policy statement|basic policy)\b", body, re.I):
                continue
            score = 10.0 + len(source_terms)
        else:
            # An explicit section definition with examples is stronger than
            # isolated topical passages or an unrelated offence schedule.
            if not re.search(r"\b(?:definition|violation|prohibited|misconduct)\b", heading, re.I):
                continue
            if not re.search(r"\b(?:examples?|such as|including|include)\b", body, re.I):
                continue
            distinct = subject_terms - {"violate", "activity", "violations"}
            overlap = len(distinct & body_terms)
            if overlap < 2 or overlap < max(2, int(len(distinct) * .45)):
                continue
            if len(_sentence_units(body)) < 2:
                continue
            score = float(overlap) / max(1, len(distinct))
        options.append((score, _document_answer_group(doc), body, source))
    if not options:
        return None
    options.sort(key=lambda x: x[0], reverse=True)
    winners = [x for x in options if abs(x[0] - options[0][0]) < 1e-6]
    if len({x[1] for x in winners}) != 1:
        return None
    _, _, answer, source = options[0]
    return answer, {
        "profile": "source_statement" if policy_purpose else "source_definition_examples",
        "items": len(_sentence_units(answer)), "sources": [source],
        "decision": "accepted-source-policy-statement" if policy_purpose
                    else "accepted-source-definition-examples",
        "covered_facets": ["policy_intent" if policy_purpose else "examples_and_context"],
        "required_facets": ["policy_intent" if policy_purpose else "examples_and_context"],
    }


def _verified_multi_condition_sanctions(
    question: str,
    retrieved: list[RetrievedDocument],
    *,
    max_chars: int,
) -> tuple[str, dict[str, object]] | None:
    """Return a complete bounded consequence rule for two alternatives.

    The rule must contain both separate conditions and a consecutive penalty
    table within one authorized policy chunk. Never infer omitted penalties,
    mix unrelated sections or join policies merely because words overlap.
    No configured QA case IDs, sample policy values, or answer keys are used.
    """
    query = _normalized_phrase_text(question)
    if not (re.search(r"^what happens if\b", query) and " or " in f" {query} "):
        return None
    # The condition after 'or' is an independent action, not a conjunction
    # in the explanatory part of the same sentence.
    halves = re.split(r"\bor\b", query, maxsplit=1)
    if len(halves) != 2:
        return None
    ignore = {
        "what", "happens", "employee", "employees", "person", "persons",
        "company", "office", "work", "working", "their", "and", "makes",
        "does", "they", "any", "policy", "rules", "violation", "violate",
    }

    def lexical_forms(value: str) -> set[str]:
        tokens = set(_meaningful_evidence_tokens(value)) - ignore
        # A common morphological reduction for 'duplicate/duplication',
        # 'authorize/authorization', etc. used only for evidence ranking.
        return {
            (re.sub(r"(?:ations|ation|tions|tion|ing|ed|es|s|e)$", "", w)
             if len(w) >= 4 and not w.endswith("ss") else w)
            for w in tokens
        }

    first = lexical_forms(halves[0])
    second = lexical_forms(halves[1])
    if not first or not second:
        return None
    options: list[tuple[float, tuple[object, ...], str, str]] = []
    for item in retrieved[:14]:
        doc = item.document
        if doc.source_type != "policy":
            continue
        if not str((doc.metadata or {}).get("file_key") or "").startswith("policy:"):
            continue
        body = _document_body_text(doc).strip()
        if not body:
            continue
        # Keep the bounded section only. Never include the following article
        # with another subject's disciplinary schedule.
        matches = list(re.finditer(r"(?m)^\s*Section\s*(\d+)\s*\.?\s*", body, re.I))
        if len(matches) < 3:
            continue
        segments = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            chunk = body[match.start():end].strip()
            # A new article may follow without an explicit section boundary.
            chunk = re.split(r"(?m)^\s*Article\s+[IVX0-9]+\b", chunk, maxsplit=1, flags=re.I)[0].strip()
            segments.append((int(match.group(1)), chunk))
        for i in range(len(segments) - 2):
            three = segments[i:i+3]
            if [x[0] for x in three] != list(range(three[0][0], three[0][0] + 3)):
                continue
            a, b, c = [x[1] for x in three]
            stems_a, stems_b = lexical_forms(a), lexical_forms(b)
            # At least one independently distinctive condition is required
            # in each clause. At least one shared topic (e.g. a physical
            # object) proves the clauses belong to the same question.
            if len(first & stems_a) < 1 or len(second & stems_b) < 1:
                continue
            if not ((first | second) & stems_a & stems_b):
                continue
            if not re.search(r"\b(?:penalt|disciplin|sanction|offen[cs])", a + b + c, re.I):
                continue
            # Require a real numbered progressive penalty sequence. A naked
            # 'Disciplinary Action' header cannot prove specific penalties.
            penalties = re.findall(r"(?mi)^\s*(\d{1,2})(?:st|nd|rd|th)\s+offen[cs]e\b", c)
            sequence = [int(x) for x in penalties]
            if len(sequence) < 2 or sequence != list(range(1, len(sequence) + 1)):
                continue
            # Penalized clause must actually specify the sanctions, not just
            # list numbers without meaningful action.
            if not re.search(r"\b(?:warning|suspension|penalt|fine|termination|reprimand)\b", c, re.I):
                continue
            answer = "\n".join(part for part in (a, b, c) if part)
            if len(answer) > max_chars or len(answer) < 100:
                continue
            score = len(first & stems_a) + len(second & stems_b)
            source = str((doc.metadata or {}).get("filename") or (doc.metadata or {}).get("title") or doc.title)
            options.append((float(score), _document_answer_group(doc), answer, source))
    if not options:
        return None
    options.sort(key=lambda x: x[0], reverse=True)
    best = [x for x in options if x[0] == options[0][0]]
    if len({x[1] for x in best}) != 1:
        return None
    score, _, answer, source = options[0]
    return answer, {
        "profile": "multi_condition_consequence", "items": 3,
        "sources": [source], "decision": "accepted-complete-source-sanctions",
        "required_facets": ["condition_one", "condition_two", "complete_sanctions"],
        "covered_facets": ["condition_one", "condition_two", "complete_sanctions"],
    }


def _fast_answer_covers_coordinated_when(question: str, answer: str) -> bool:
    """A who-and-when answer must prove both facets, not any random date.

    The date/time must be attached to a temporal trigger. Unrelated service
    tenure (one year) or another benefit's cutoff cannot satisfy 'when'.
    """
    clean = _normalized_phrase_text(question)
    # Narrowly enforce this on effective-date questions. Other 'who and
    # when' workflows may legitimately specify an event instead of a date.
    if not (re.search(r"^who\b.{0,190}\band when\b", clean)
            and re.search(r"\b(?:take effect|effective|effectivity|starts?|begins?)\b", clean)):
        return True
    value = str(answer or "")
    has_recipient = bool(re.search(r"\b(?:employees?|staff|workers?|members?|persons?|managers?|officers?|personnel)\b", value, re.I))
    dates = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
             r"|\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?"
             r"|\d{1,2}:\d{2}\s*(?:a\.?m\.?|p\.?m\.?)")
    # Require a bounded trigger->date relationship (either order), rather
    # than treating unrelated benefit dates as sufficient proof.
    trigger = r"(?:effectiv\w*|takes? effect|begins?|starts?|implemented|commenc\w*|effective date)"
    has_when = bool(re.search(rf"\b{trigger}\b.{{0,120}}(?:{dates})|(?:{dates}).{{0,120}}\b{trigger}\b", value, re.I | re.S))
    return has_recipient and has_when


def _grounded_extractive_answer(
    query: str,
    retrieved: list[RetrievedDocument],
    *,
    max_items: int,
    max_chars: int,
) -> tuple[str, dict[str, object]]:
    """Build an extractive-only fast answer from complete evidence units.

    This deliberately performs *selection*, not semantic rewriting.  Every
    returned sentence/row comes verbatim from an authorized retrieved source,
    so policy qualifiers and scope conditions cannot be broadened by a model.
    """

    profile = _question_evidence_profile(query)
    contract_shape = _explicit_question_contract_shape(query)
    if contract_shape:
        contract = _explicit_question_contract_answer(
            query, retrieved, max_chars=max_chars,
        )
        if contract is not None:
            return contract
        # A plausible title, keyword, or numeric cue does not prove the
        # conditional premise, both event facets or both independent dates.
        # Synthesize from authorized passages rather than accept wrong fast text.
        return "", {
            "profile": profile, "items": 0, "sources": [],
            "decision": "explicit-question-contract-unproven",
            "required_facets": [contract_shape],
        }
    # Passive multi-action procedures require an intact, subject-specific
    # numbered subsection, never disconnected keyword-matching steps.
    workflow = _scoped_workflow_question(query)
    if workflow is not None:
        scoped = _scoped_workflow_evidence(query, retrieved, max_chars=max_chars)
        if scoped is not None:
            return scoped
        return "", {
            "profile": "procedure", "items": 0, "sources": [],
            "decision": "scoped-workflow-evidence-incomplete",
            "required_facets": list(workflow[1]),
        }
    contiguous = _contiguous_conditional_list_answer(query, retrieved, max_chars=max_chars)
    if contiguous is not None:
        return contiguous
    linked = _bounded_linked_policy_clauses(query, retrieved, max_chars=max_chars)
    if linked is not None:
        return linked
    sanction_proof = _verified_multi_condition_sanctions(
        query, retrieved, max_chars=max_chars,
    )
    if sanction_proof is not None:
        return sanction_proof
    # Prefer an authorized named policy statement or explicitly defined list
    # of violations over costly/possibly off-topic LLM paraphrasing.
    source_proof = _verified_source_statement_or_examples(
        query, retrieved, max_chars=max_chars,
    )
    if source_proof is not None:
        return source_proof
    # Prefer explicit policy structures over disconnected high-score snippets.
    structured = _structurally_complete_policy_evidence(
        query, retrieved, max_chars=max_chars,
    )
    if structured is not None:
        return structured
    # Prefer a locally complete, verbatim two-fact proof when available.
    # Otherwise the original policy-safe answer flow remains unchanged.
    coordinated = _coordinated_verbatim_facts(
        query, retrieved, max_chars=max_chars,
    )
    if coordinated is not None:
        return coordinated
    query_terms = set(_meaningful_evidence_tokens(query))
    query_clean = _normalized_phrase_text(query)
    require_clock = bool(re.search(r"\b(?:what times?|at what time|hours|schedules?|timetable)\b", query_clean))
    require_number = bool(re.search(r"\b(?:how many|how much|what grade|what percentage|what percent|how long|number of|amount)\b", query_clean))
    query_years = _explicit_year_values(query)
    direct_target = _direct_action_target(query) if profile == "direct_fact" else None
    first_step = bool(re.search(r"\b(?:first|initial|unang)\b", query, re.I))
    exception_requested = bool(re.search(
        r"\b(?:unless|except|otherwise|unavailable|cannot|could not|alternative|instead|if not|when not)\b",
        query, re.I,
    ))
    candidates: list[tuple[float, int, int, str, str, bool]] = []

    safe_source_types = {
        "policy", "company_form_content", "live_company_benefit",
        "policy_violation",
    }
    for doc_rank, item in enumerate(retrieved[:8]):
        document = item.document
        if document.source_type not in safe_source_types:
            continue
        body = _document_body_text(document)
        units = _sentence_units(body)
        if not units:
            continue
        source_name = str(
            (document.metadata or {}).get("filename")
            or (document.metadata or {}).get("title")
            or document.title
            or document.document_id
        )
        for unit_index, raw_unit in enumerate(units):
            unit = re.sub(r"\s+", " ", raw_unit).strip()
            if len(unit) < 18:
                continue
            # Headings and list preambles do not prove the requested answer.
            # Keep them as contextual metadata, but never emit as standalone
            # evidence. This is a structural rather than QA-text rule.
            if re.search(r"(?:to the following|as follows|listed below|include the following)\s*:?[.]?$", unit, re.I):
                continue
            if (unit.endswith(":") or unit.casefold().startswith(("article ", "section "))
                ) and not re.search(r"\b(?:shall|must|is|are|may|will|within|after|before)\b", unit, re.I):
                continue

            # When the question names a specific year/service milestone, avoid
            # selecting a sentence that states only a different milestone.
            unit_years = _explicit_year_values(unit)
            if query_years and unit_years and not query_years.intersection(unit_years):
                continue

            unit_terms = set(_meaningful_evidence_tokens(unit))
            overlap = len(query_terms.intersection(unit_terms))
            coverage = overlap / max(1, len(query_terms))
            target_match = bool(
                direct_target and _DIRECT_ACTION_FAMILIES[direct_target].search(unit)
            )
            # A rule's condition is frequently stated in the preceding sentence
            # or section heading while the following step states the actor.
            # Use that local context *only for ranking*; copy the selected rule
            # verbatim. Never attach unrelated evidence from another document.
            context_terms = set(_meaningful_evidence_tokens(
                " ".join(units[max(0, unit_index - 2):unit_index])[-450:]
                + " " + str((document.metadata or {}).get("section") or "")
            ))
            contextual_coverage = len(query_terms.intersection(unit_terms | context_terms)) / max(1, len(query_terms))
            if profile == "direct_fact" and coverage < 0.35:
                # A generic payment rule can use the immediately prior unit's
                # named expense subject. Keep it eligible for the stricter
                # compound-coverage validation instead of dropping it solely
                # because the payer clause omits the subject name.
                antecedent_eligible = bool(
                    direct_target == "payment" and target_match and unit_index > 0
                    and re.search(r"\b(?:any|these|such|those)\b.{0,60}\b(?:expenses?|costs?|charges?)\b", unit, re.I)
                    and re.search(
                        r"\b(?:" + "|".join(re.escape(t) for t in query_terms if len(t) >= 4) + r")\b\W+(?:\w+\W+){0,3}(?:expenses?|costs?|charges?)\b",
                        units[unit_index - 1], re.I,
                    )
                )
                if not (target_match and ((overlap >= 1 and contextual_coverage >= 0.48) or antecedent_eligible)):
                    continue
            exception_only = _exception_only_sentence(unit)
            if exception_only and first_step and not exception_requested:
                # An unasked fallback can never stand in for "who first?".
                continue
            cue = _answerability_cue_bonus(query, unit)
            eligibility_condition = bool(re.search(
                r"\b(?:employees?\s+who|persons?\s+who|staff\s+who|"
                r"participants?\s+who|must\s+(?:have|pass|complete|obtain)|"
                r"(?:qualify|eligible|eligibility)\s+(?:if|when|under)|"
                r"minimum\s+(?:grade|score)|"
                r"(?:passed|topped|obtained|completed|certified)\s+(?:the|an?|at))\b",
                unit, re.I,
            ))
            info = 0.0
            if re.search(r"(?:₱|\$|¥|€)\s*\d|\b\d+(?:[.,]\d+)?\b", unit):
                info += 0.45
            if re.search(
                r"\b(?:shall|must|required|eligible|entitled|inform|notify|contact|"
                r"submit|approve|within|before|after|option|credit|award)\w*\b",
                unit,
                re.I,
            ):
                info += 0.35
            source_fit = _evidence_fit_bonus(query, document)
            rank_bonus = max(0.0, 0.30 - (doc_rank * 0.04))
            score = (coverage * 4.0) + (overlap * 0.22) + (cue * 1.8) + info + source_fit + rank_bonus
            if profile == "eligibility" and eligibility_condition:
                score += 3.2
            if target_match:
                score += 4.0
                score += max(0.0, contextual_coverage - coverage) * 1.8
            elif direct_target:
                score -= 2.0
            if exception_only and not exception_requested:
                score -= 2.5
            candidates.append((score, doc_rank, unit_index, unit, source_name, target_match))

    if not candidates:
        return "", {"profile": profile, "items": 0, "sources": []}

    candidates.sort(key=lambda item: item[0], reverse=True)
    if profile == "direct_fact" and direct_target:
        compound_answer = _compound_direct_fact_evidence(
            query, retrieved, candidates, target=direct_target,
            max_items=max_items, max_chars=max_chars,
        )
        if compound_answer is not None:
            return compound_answer
    if profile in {"procedure", "direct_fact"} and re.search(r"\b(?:first|initial|unang)\b", query, re.I):
        item_limit = 1
    elif profile == "direct_fact":
        item_limit = min(2, max(1, int(max_items)))
    elif profile in {"amount", "duration_or_count", "date_or_time", "eligibility"}:
        item_limit = min(3, max(1, int(max_items)))
    elif profile in {"list", "comparison", "procedure"}:
        item_limit = max(1, int(max_items))
    else:
        item_limit = min(2, max(1, int(max_items)))

    best_score = candidates[0][0]
    # A fast extract cannot safely splice unrelated policy documents into one
    # apparent rule. One complete originating document may have many chunks;
    # independent documents require contextual synthesis and source separation.
    # This is a source-identity guard, not a question/answer lookup.
    primary_group = _document_answer_group(retrieved[candidates[0][1]].document)
    selected: list[tuple[int, int, str, str]] = []
    normalized_selected: list[str] = []
    rendered_chars = 0
    for score, doc_rank, unit_index, unit, source_name, target_match in candidates:
        if len(selected) >= item_limit:
            break
        if _document_answer_group(retrieved[doc_rank].document) != primary_group:
            continue
        # Do not pad the answer with weak nearby text merely to fill a list.
        if selected and score < max(1.0, best_score * 0.30):
            continue
        normalized = _normalized_phrase_text(unit)
        if not normalized:
            continue
        if any(
            normalized == prior
            or (len(normalized) > 80 and normalized in prior)
            or (len(prior) > 80 and prior in normalized)
            for prior in normalized_selected
        ):
            continue
        projected = rendered_chars + len(unit) + 6
        if selected and projected > max(420, int(max_chars)):
            continue
        selected.append((doc_rank, unit_index, unit, source_name))
        normalized_selected.append(normalized)
        rendered_chars = projected

    if not selected:
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "no-selected-evidence"}
    # A verbatim fast answer can still be the *wrong subsection* if it covers
    # just one common topic word. Require question-specific subject coverage,
    # independently of a strong file title or original retrieval rank.
    answer_tokens = set(_meaningful_evidence_tokens(" ".join(x[2] for x in selected)))
    distinctive = {term for term in query_terms if len(term) >= 4 and term not in
                   {"company", "employee", "employees", "policy", "work", "working",
                    "during", "required", "should", "would", "their"}}
    if distinctive and not (distinctive & answer_tokens):
        return "", {"profile": profile, "items": 0, "sources": [],
                    "decision": "source-subsection-target-missing"}
    if direct_target and not any(
        _DIRECT_ACTION_FAMILIES[direct_target].search(item[2]) for item in selected
    ):
        # Relevant subject text is not necessarily the requested answer. Let
        # grounded synthesis attempt the evidence rather than returning noise.
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "answer-target-not-met"}
    # A quick answer must contain the *kind* of fact requested, not only
    # nearby words from the correct policy section. If the fact is absent,
    # let grounded generation use expanded authorized evidence instead.
    selected_text = " ".join(item[2] for item in selected)
    if require_clock and not re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b|\b\d{1,2}:\d{2}\b", selected_text, re.I):
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "missing-requested-time-evidence"}
    if require_number and not re.search(r"\b\d+(?:[.,]\d+)?\b|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty)\b", selected_text, re.I):
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "missing-requested-numeric-evidence"}
    # A question seeking a numeric value of a named property cannot be
    # satisfied by an unrelated number (e.g. a class label or section number).
    # This property/value relation is grammatical and policy-agnostic.
    numeric_property = re.search(r"\bwhat\s+(?:is\s+the\s+)?(grade|percentage|percent|rate|amount|score|threshold|limit)\b", query_clean)
    if numeric_property and not re.search(
        rf"\b{re.escape(numeric_property.group(1))}\b[^.\n]{{0,85}}\b\d+(?:[.,]\d+)?\b|"
        rf"\b\d+(?:[.,]\d+)?\b[^.\n]{{0,50}}\b{re.escape(numeric_property.group(1))}\b",
        selected_text, re.I,
    ):
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "numeric-property-value-not-supported"}
    if profile in {"eligibility", "list"} and not re.search(r"\b(?:qualif|eligib|must|shall|employee|staff|participants?|members?|covered|include|require|award|pass|certificate|level)\w*\b", selected_text, re.I):
        return "", {"profile": profile, "items": 0, "sources": [], "decision": "no-substantive-list-or-criteria"}
    # 'Who qualifies?' cannot be answered by a mission statement or by when
    # winners receive awards. A concrete qualifying condition is required.
    # For enumerated criteria in the same authorized policy chunk, verify that
    # the extraction includes every sibling item; otherwise use grounded LLM
    # synthesis (with that source) instead of an incomplete shortcut.
    asks_eligibility = bool(re.search(
        r"\b(?:who\s+(?:is|are|can|may)\s+(?:eligible|qualified|entitled)|"
        r"who\s+qualifies|requirements?\s+to\s+qualify|"
        r"what\s+are\s+the\s+(?:eligibility|qualification|requirements?))\b",
        query, re.I,
    ))
    if profile == "eligibility" and asks_eligibility:
        if not re.search(
            r"\b(?:employees?\s+who|persons?\s+who|"
            r"must\s+(?:have|pass|complete|obtain)|"
            r"(?:qualif|eligible|entitl)\w*\s+(?:if|when|under)|"
            r"(?:passed|topped|obtained|completed|certified)\s+(?:the|an?|at))\b",
            selected_text, re.I,
        ):
            return "", {"profile": profile, "items": 0, "sources": [],
                        "decision": "eligibility-conditions-not-proven"}
        for doc_rank in sorted({item[0] for item in selected}):
            source_units = _sentence_units(_document_body_text(retrieved[doc_rank].document))
            numbered = [unit for unit in source_units if re.match(r"^\d+[.)]\s+", unit)]
            if len(numbered) >= 2 and re.search(
                r"\b(?:following|criteria|requirements?|eligible|coverage)\b",
                _document_search_text(retrieved[doc_rank].document), re.I,
            ):
                answer_normalized = _normalized_phrase_text(selected_text)
                if any(_normalized_phrase_text(unit) not in answer_normalized for unit in numbered):
                    return "", {"profile": profile, "items": 0, "sources": [],
                                "decision": "enumerated-criteria-incomplete"}

    # A coordinated question requires evidence for both explicitly requested
    # content objects, independently of HR vocabulary or sample question text.
    # If verbatim extraction cannot demonstrate coverage, defer to grounded
    # synthesis instead of returning a plausible but incomplete fast answer.
    compound_facets = re.findall(
        r"\b([a-z][a-z0-9-]{3,})\s+and\s+([a-z][a-z0-9-]{3,})\b",
        _normalized_phrase_text(query),
    )
    if compound_facets:
        answer_words = set(_tokenize(" ".join(item[2] for item in selected)))
        # A grammatical bridge like 'last, and what is required' is NOT a
        # pair of content objects. Keep only independently meaningful pairs.
        grammar = {"what", "when", "where", "who", "which", "how", "last", "required"}
        required_facets = {word for pair in compound_facets
                           if not (set(pair) & grammar) for word in pair}
        if required_facets and not required_facets.issubset(answer_words):
            return "", {"profile": profile, "items": 0, "sources": [],
                        "decision": "compound-target-incomplete",
                        "required_facets": sorted(required_facets),
                        "covered_facets": sorted(required_facets.intersection(answer_words))}

    # A semantically plausible who+when answer without an effective date is
    # incomplete; do not mark it as successful grounded extraction.
    if not _fast_answer_covers_coordinated_when(query, selected_text):
        return "", {
            "profile": profile, "items": 0, "sources": [],
            "decision": "coordinated-who-when-evidence-incomplete",
            "required_facets": ["person_or_group", "effective_date"],
            "covered_facets": ["person_or_group"],
        }

    # Keep source order for procedural coherence when several units from the
    # same chunk were selected; ranking decides inclusion, not sentence order.
    selected.sort(key=lambda item: (item[0], item[1]))
    units = [item[2] for item in selected]
    if len(units) == 1:
        answer = units[0]
    elif profile == "procedure":
        answer = "\n".join(f"{index}. {unit}" for index, unit in enumerate(units, start=1))
    else:
        answer = "\n".join(f"- {unit}" for unit in units)

    return answer[: max(420, int(max_chars))].rstrip(), {
        "profile": profile,
        "items": len(units),
        "sources": sorted({item[3] for item in selected}),
        "target": direct_target or "-",
        "decision": "accepted",
    }


def _split_oversized_unit(value: str, chunk_size: int) -> list[str]:
    """Legacy bounded splitter retained for compatibility callers/tests."""

    words = value.split()
    if len(words) <= chunk_size:
        return [value]
    return [
        " ".join(words[index:index + chunk_size])
        for index in range(0, len(words), chunk_size)
        if words[index:index + chunk_size]
    ]


def _unit_boundary_kind(value: str) -> str:
    clean = str(value or "").strip()
    if " | " in clean:
        return "table_row"
    if re.match(r"^(?:[-*•]|\d+[.)])\s+", clean):
        return "list_item"
    return "sentence_boundary"


def _split_oversized_unit_adaptive(
    value: str,
    *,
    max_words: int,
) -> list[tuple[str, str]]:
    """Split one abnormally long sentence/row before falling back to words.

    Clause boundaries are preferred because they keep policy conditions and
    exceptions more coherent than blind fixed-word windows.  The final word
    fallback is deterministic and guarantees the hard maximum.
    """

    clean = str(value or "").strip()
    if not clean:
        return []
    if _word_count(clean) <= max_words:
        return [(clean, _unit_boundary_kind(clean))]

    clauses = [
        item.strip()
        for item in re.split(
            r"(?<=[;:])\s+|(?<=,)\s+(?=(?:and|or|but|except|unless|provided|when|where|which|who|that)\b)",
            clean,
            flags=re.I,
        )
        if item.strip()
    ]
    if len(clauses) > 1 and all(_word_count(item) <= max_words for item in clauses):
        output: list[tuple[str, str]] = []
        current: list[str] = []
        current_words = 0
        for clause in clauses:
            clause_words = _word_count(clause)
            if current and current_words + clause_words > max_words:
                output.append((" ".join(current).strip(), "clause_boundary"))
                current = []
                current_words = 0
            current.append(clause)
            current_words += clause_words
        if current:
            output.append((" ".join(current).strip(), "clause_boundary"))
        if output:
            return output

    words = clean.split()
    return [
        (" ".join(words[index:index + max_words]), "word_fallback")
        for index in range(0, len(words), max_words)
        if words[index:index + max_words]
    ]


def _adaptive_overlap_words(
    *,
    target_words: int,
    ratio: float,
    minimum: int,
    maximum: int,
) -> int:
    minimum = max(0, int(minimum))
    maximum = max(minimum, int(maximum))
    ratio = min(0.30, max(0.0, float(ratio)))
    return max(minimum, min(maximum, int(round(target_words * ratio))))


def _split_text_adaptive(
    text: str,
    *,
    min_words: int,
    target_words: int,
    max_words: int,
    overlap_words: int,
) -> list[tuple[str, int, str]]:
    """Return adaptive structure-aware chunks as (text, overlap, reason).

    A complete semantic section is never split merely to hit the soft target.
    Sections larger than the hard maximum are split on sentence/row boundaries,
    with bounded adaptive overlap only between fragments of that same section.
    """

    raw = str(text or "").strip()
    if not raw:
        return []

    max_words = max(96, int(max_words))
    target_words = max(80, min(int(target_words), max_words))
    min_words = max(48, min(int(min_words), target_words))
    overlap_words = max(0, min(int(overlap_words), max(0, target_words // 3)))

    total_words = _word_count(raw)
    if total_words <= max_words:
        return [(raw, 0, "semantic_section")]

    units: list[tuple[str, str]] = []
    for unit in _sentence_units(raw):
        units.extend(
            _split_oversized_unit_adaptive(unit, max_words=max_words)
        )
    if not units:
        return []

    chunks: list[tuple[str, int, str]] = []
    current: list[tuple[str, str]] = []
    current_words = 0
    retained_overlap = 0

    def retained_tail(items: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], int]:
        if overlap_words <= 0:
            return [], 0
        tail: list[tuple[str, str]] = []
        words = 0
        for item in reversed(items):
            count = _word_count(item[0])
            if tail and words + count > overlap_words:
                break
            if count > overlap_words and not tail:
                break
            tail.insert(0, item)
            words += count
            if words >= overlap_words:
                break
        return tail, words

    def emit(reason: str) -> None:
        nonlocal current, current_words, retained_overlap
        if not current:
            return
        rendered = " ".join(item[0] for item in current).strip()
        if rendered and (not chunks or rendered != chunks[-1][0]):
            chunks.append((rendered, retained_overlap, reason))
        current, retained_overlap = retained_tail(current)
        current_words = sum(_word_count(item[0]) for item in current)

    for index, (unit, unit_reason) in enumerate(units):
        unit_words = max(1, _word_count(unit))
        has_more = index < len(units) - 1

        if current:
            prospective = current_words + unit_words
            if prospective > max_words:
                emit("hard_max_boundary")
            elif current_words >= min_words and prospective > target_words:
                emit("target_boundary")

        # Retained overlap must never force the next logical unit over the hard
        # ceiling.  Drop overlap before sacrificing the intact sentence/row.
        if current and current_words + unit_words > max_words:
            current = []
            current_words = 0
            retained_overlap = 0

        current.append((unit, unit_reason))
        current_words += unit_words

        # A word/clause fallback fragment was already split because the source
        # unit exceeded the hard maximum. Emit it promptly rather than merging
        # another unrelated sentence into the same fragment.
        if has_more and unit_reason in {"word_fallback", "clause_boundary"} and current_words >= target_words:
            emit(unit_reason)

    if current:
        rendered = " ".join(item[0] for item in current).strip()
        reason = "section_tail" if chunks else "semantic_section"
        if rendered and (not chunks or rendered != chunks[-1][0]):
            chunks.append((rendered, retained_overlap, reason))

    # Defensive hard-bound validation.  This should normally be unnecessary,
    # but fail-safe splitting is preferable to shipping an oversized context.
    bounded: list[tuple[str, int, str]] = []
    for chunk, overlap, reason in chunks:
        if _word_count(chunk) <= max_words:
            bounded.append((chunk, overlap, reason))
            continue
        for fallback, fallback_reason in _split_oversized_unit_adaptive(
            chunk, max_words=max_words
        ):
            bounded.append((fallback, 0, fallback_reason))
    return bounded


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Legacy sentence/row-aware bounded chunks with deterministic overlap."""

    raw = str(text or "").strip()
    if not raw:
        return []
    chunk_size = max(80, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size // 3))

    units: list[str] = []
    for unit in _sentence_units(raw):
        units.extend(_split_oversized_unit(unit, chunk_size))
    if not units:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def emit() -> None:
        nonlocal current, current_words
        if not current:
            return
        chunk = " ".join(current).strip()
        if chunk:
            chunks.append(chunk)
        if not overlap:
            current = []
            current_words = 0
            return
        tail: list[str] = []
        tail_words = 0
        for item in reversed(current):
            count = _word_count(item)
            if tail and tail_words + count > overlap:
                break
            tail.insert(0, item)
            tail_words += count
            if tail_words >= overlap:
                break
        current = tail
        current_words = tail_words

    for unit in units:
        unit_words = max(1, _word_count(unit))
        if current and current_words + unit_words > chunk_size:
            emit()
        if current and current_words + unit_words > chunk_size:
            current = []
            current_words = 0
        current.append(unit)
        current_words += unit_words
    if current:
        chunk = " ".join(current).strip()
        if chunk and (not chunks or chunk != chunks[-1]):
            chunks.append(chunk)
    return chunks

def _document_sections(text: str) -> list[tuple[str, str]]:
    """Return logical sections/pages from one extracted company document."""

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []

    sections: list[tuple[str, str]] = []
    heading = "Document"
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        content = "\n".join(body).strip()
        if content:
            sections.append((heading, content))
        body = []

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            if body and body[-1] != "":
                body.append("")
            continue
        page_match = re.match(r"^Page\s+(\d+)\s*:\s*(.*)$", line, re.I)
        if page_match:
            flush()
            heading = f"Page {page_match.group(1)}"
            remainder = page_match.group(2).strip()
            if remainder:
                body.append(remainder)
            continue
        heading_match = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading_match:
            flush()
            heading = heading_match.group(1).strip() or "Document"
            continue
        if re.match(r"^(?:Sheet\s*:|Table\s+\d+\s*$)", line, re.I):
            flush()
            heading = line
            continue
        body.append(line)
    flush()
    return sections or [("Document", normalized.strip())]


def _prepare_document_chunks_detailed(
    sections: list[tuple[str, str, int | None]],
    *,
    chunk_size: int,
    overlap: int,
    adaptive: bool = False,
    min_words: int | None = None,
    target_words: int | None = None,
    max_words: int | None = None,
    overlap_ratio: float = 0.14,
    overlap_min_words: int = 16,
    overlap_max_words: int = 44,
) -> list[PreparedChunk]:
    """Create bounded file chunks and retain the reason for every boundary.

    The adaptive path is used by the live v8.8.222 knowledge builder.  The
    compatibility path preserves the previous fixed-budget behavior for older
    integrations while sharing the same section-merging implementation.
    """

    normalized: list[tuple[str, str, int | None]] = []
    for label, text, page_number in sections:
        clean = str(text or "").strip()
        if clean:
            normalized.append(
                (
                    str(label or "Document").strip() or "Document",
                    clean,
                    page_number,
                )
            )
    if not normalized:
        return []

    chunk_size = max(80, int(chunk_size))
    overlap = max(0, int(overlap))

    if adaptive:
        target_words = max(80, int(target_words or chunk_size))
        max_words = max(target_words, int(max_words or max(chunk_size, target_words)))
        min_words = max(48, min(int(min_words or max(80, target_words // 2)), target_words))
        adaptive_overlap = _adaptive_overlap_words(
            target_words=target_words,
            ratio=overlap_ratio,
            minimum=overlap_min_words,
            maximum=min(overlap_max_words, max_words // 3),
        )
        merge_ceiling = target_words
        micro_limit = max(48, min(96, min_words // 2 + 24))
    else:
        target_words = chunk_size
        max_words = chunk_size
        min_words = max(48, min(96, chunk_size // 3))
        adaptive_overlap = min(overlap, chunk_size // 3)
        merge_ceiling = chunk_size
        micro_limit = max(48, min(96, chunk_size // 3))

    merged: list[tuple[str, str, int | None]] = []
    pending_label = ""
    pending_text = ""
    pending_page: int | None = None

    def flush_pending() -> None:
        nonlocal pending_label, pending_text, pending_page
        if pending_text.strip():
            merged.append((pending_label or "Document", pending_text.strip(), pending_page))
        pending_label = ""
        pending_text = ""
        pending_page = None

    for label, text, page_number in normalized:
        words = _word_count(text)
        if not pending_text:
            pending_label, pending_text, pending_page = label, text, page_number
            continue

        pending_words = _word_count(pending_text)
        same_page = (
            pending_page == page_number
            or pending_page is None
            or page_number is None
        )
        combined_words = pending_words + words
        # Do not merge separate lists of policy obligations into one tiny
        # heading solely to reduce chunk count. Those lists often answer
        # different questions even if adjacent and short.
        pending_has_list = len(re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", pending_text)) >= 2
        next_has_list = len(re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", text)) >= 2
        should_merge = (
            same_page
            and combined_words <= merge_ceiling
            and (pending_words < micro_limit or words < micro_limit)
            and not (pending_label != label and (pending_has_list or next_has_list))
        )
        if should_merge:
            if label.casefold() not in pending_label.casefold():
                pending_label = f"{pending_label} / {label}"[:250]
            pending_text = f"{pending_text}\n\n{text}".strip()
            if pending_page != page_number:
                pending_page = None
            continue

        flush_pending()
        pending_label, pending_text, pending_page = label, text, page_number

    flush_pending()

    prepared: list[PreparedChunk] = []
    for label, text, page_number in merged:
        if adaptive:
            pieces = _split_text_adaptive(
                text,
                min_words=min_words,
                target_words=target_words,
                max_words=max_words,
                overlap_words=adaptive_overlap,
            )
        else:
            pieces = [
                (chunk, min(adaptive_overlap, _word_count(chunk)), "fixed_budget")
                for chunk in _split_text(text, chunk_size, overlap)
            ]

        section_total = len(pieces)
        for local_index, (chunk, overlap_words, reason) in enumerate(pieces, start=1):
            prepared.append(
                PreparedChunk(
                    section=label,
                    text=chunk,
                    page_number=page_number,
                    word_count=_word_count(chunk),
                    overlap_words=max(0, int(overlap_words)),
                    boundary_reason=reason,
                    section_chunk_index=local_index,
                    section_chunk_total=section_total,
                    continuation_before=local_index > 1,
                    continuation_after=local_index < section_total,
                )
            )
    return prepared


def _prepare_document_chunks(
    sections: list[tuple[str, str, int | None]],
    *,
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, str, int | None]]:
    """Compatibility wrapper returning the historical tuple shape."""

    return [
        (chunk.section, chunk.text, chunk.page_number)
        for chunk in _prepare_document_chunks_detailed(
            sections,
            chunk_size=chunk_size,
            overlap=overlap,
            adaptive=False,
        )
    ]

def _file_key(document: KnowledgeDocument) -> str | None:
    if document.source_type not in _DOCUMENT_CHUNK_SOURCE_TYPES:
        return None
    value = document.metadata.get("file_key")
    return str(value) if value else None


class PortalKnowledgeBuilder:
    """Build role-safe knowledge from published policies and portal workflows."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_chat_assistant_settings()
        self.company_form_extractor = CompanyFormKnowledgeExtractor()
        self._trace: TerminalChatTrace | None = None
        self._chunk_batch_summary: list[dict[str, object]] = []

    @staticmethod
    def _add_document(
        documents: list[KnowledgeDocument],
        *,
        document_id: str,
        text: str,
        title: str,
        source_type: str,
        company_id: int,
        role_scope: str,
        metadata: dict[str, str | int | None] | None = None,
    ) -> None:
        """Append one normalized, role-safe live knowledge record."""

        clean = _clean_text(text)
        if not clean:
            return
        documents.append(KnowledgeDocument(
            document_id=document_id,
            text=clean,
            title=title,
            source_type=source_type,
            company_id=company_id,
            role_scope=role_scope,
            metadata=metadata or {"title": title},
        ))

    def _record_chunk_diagnostics(
        self,
        *,
        source: str,
        filename: str,
        sections: list[tuple[str, str, int | None]],
        chunks: list[PreparedChunk],
        min_words: int,
        target_words: int,
        max_words: int,
    ) -> None:
        trace = self._trace
        if trace is None or not bool(self.settings.chunk_diagnostics_enabled):
            return
        rows = [
            {
                "section": chunk.section,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "word_count": chunk.word_count,
                "overlap_words": chunk.overlap_words,
                "boundary_reason": chunk.boundary_reason,
                "section_chunk_index": chunk.section_chunk_index,
                "section_chunk_total": chunk.section_chunk_total,
            }
            for chunk in chunks
        ]
        trace.chunking_file(
            source=source,
            filename=filename,
            sections=len(sections),
            chunks=rows,
            strategy=(
                "adaptive-structure-aware"
                if self.settings.adaptive_chunking_enabled
                else "legacy-fixed-budget"
            ),
            min_words=min_words,
            target_words=target_words,
            max_words=max_words,
            overlap_ratio=float(self.settings.adaptive_overlap_ratio),
        )
        self._chunk_batch_summary.append(
            {
                "filename": filename,
                "sections": len(sections),
                "chunks": len(chunks),
                "word_fallbacks": sum(
                    1 for chunk in chunks if chunk.boundary_reason == "word_fallback"
                ),
            }
        )

    def _add_company_benefit_records(
        self,
        documents: list[KnowledgeDocument],
        *,
        current_user: AuthenticatedUser,
    ) -> None:
        """Add active company-configured benefits as shared knowledge.

        Benefit names, descriptions, eligibility text, and enrollment guidance
        are ordinary company knowledge already exposed in the employee portal.
        Archived benefits are excluded so obsolete entries cannot ground a
        current answer.
        """

        benefits = self.session.scalars(
            select(CompanyBenefit)
            .where(
                CompanyBenefit.company_id == current_user.company_id,
                CompanyBenefit.is_active.is_(True),
            )
            .order_by(CompanyBenefit.sort_order, CompanyBenefit.name)
            .limit(1000)
        ).all()
        for benefit in benefits:
            self._add_document(
                documents,
                document_id=(
                    f"company:{current_user.company_id}:live:benefit:{benefit.id}"
                ),
                title=f"Company benefit — {benefit.name}",
                source_type="live_company_benefit",
                company_id=current_user.company_id,
                role_scope="shared",
                text=(
                    f"Company benefit: {benefit.name}. "
                    f"Category: {benefit.category or 'General'}. "
                    f"Description: {benefit.description or 'No description'}. "
                    f"Eligibility: {benefit.eligibility or 'Not specified'}. "
                    f"Effective date: "
                    f"{benefit.effective_date.isoformat() if benefit.effective_date else 'Not specified'}. "
                    f"Enrollment instructions: "
                    f"{benefit.enrollment_instructions or 'Not specified'}. "
                    f"Contact person: {benefit.contact_person or 'Not specified'}."
                ),
                metadata={
                    "benefit_id": benefit.id,
                    "title": benefit.name,
                    "category": benefit.category,
                    "effective_date": (
                        benefit.effective_date.isoformat()
                        if benefit.effective_date
                        else None
                    ),
                },
            )

    def _add_live_company_records(
        self,
        documents: list[KnowledgeDocument],
        *,
        current_user: AuthenticatedUser,
        role_scope: str,
    ) -> None:
        """Add authorized live records without authentication secrets.

        Administrators receive company-wide records from their own tenant.
        Employees receive only their own private HR records plus company-wide
        information already available in the employee portal.
        """

        company_id = current_user.company_id
        is_admin = role_scope == "admin"
        employee_id = current_user.employee_id
        live_scope = "admin" if is_admin else "employee"

        self._add_company_benefit_records(
            documents,
            current_user=current_user,
        )

        company = self.session.scalar(
            select(Company).where(Company.id == company_id)
        )
        if company is not None:
            workdays = [
                label
                for label, enabled in (
                    ("Monday", company.work_monday),
                    ("Tuesday", company.work_tuesday),
                    ("Wednesday", company.work_wednesday),
                    ("Thursday", company.work_thursday),
                    ("Friday", company.work_friday),
                    ("Saturday", company.work_saturday),
                    ("Sunday", company.work_sunday),
                )
                if enabled
            ]
            try:
                excluded_positions = json.loads(
                    company.shifting_credit_excluded_positions_json or "[]"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                excluded_positions = []
            if not isinstance(excluded_positions, list):
                excluded_positions = []
            excluded_positions_text = ", ".join(
                str(value) for value in excluded_positions if str(value).strip()
            ) or "None"

            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:company",
                title="Live company profile and attendance schedule",
                source_type="live_company",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Company name: {company.name}. Company code: {company.code}. "
                    f"Company active: {'Yes' if company.is_active else 'No'}. "
                    f"Regular workdays: {', '.join(workdays) or 'None configured'}. "
                    f"Regular hours per workday: {company.attendance_regular_hours}. "
                    f"Lunch break: {company.attendance_lunch_minutes} minutes. "
                    f"OT dinner-break deduction: {company.ot_dinner_break_deduction_hours} hours. "
                    f"Shifting Credits enabled: {'Yes' if company.shifting_credits_enabled else 'No'}. "
                    f"Shifting-credit block: {company.shifting_credit_block_hours} hours; "
                    f"required blocks per cut-off: {company.shifting_credit_required_blocks}; "
                    f"first cut-off end day: {company.shifting_credit_cutoff_day}; "
                    f"availability delay: {company.shifting_credit_availability_cutoffs} completed cut-offs; "
                    f"expiration basis: {company.shifting_credit_expiration_mode}; "
                    f"custom expiration date: {company.shifting_credit_expiration_month}/"
                    f"{company.shifting_credit_expiration_day}. "
                    f"Additional VL qualifying OT: "
                    f"{company.shifting_credit_additional_vl_threshold_hours} hours; "
                    f"additional VL: {company.shifting_credit_additional_vl_days} days; "
                    f"straight-OT VL also remains OT payable: "
                    f"{'Yes' if company.shifting_credit_additional_vl_also_payable else 'No'}. "
                    f"Shifting-credit excluded positions: "
                    f"{excluded_positions_text}."
                ),
            )

        employee_query = select(Employee).where(Employee.company_id == company_id)
        if not is_admin:
            if employee_id is None:
                employee_query = employee_query.where(Employee.id == -1)
            else:
                employee_query = employee_query.where(Employee.id == employee_id)
        employees = self.session.scalars(
            employee_query.order_by(Employee.employee_number).limit(1000)
        ).unique().all()
        for employee in employees:
            department = employee.department.name if employee.department else "Not assigned"
            manager = employee.manager.full_name if employee.manager else "Not assigned"
            leader = employee.leader.full_name if employee.leader else "Not assigned"
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:employee:{employee.id}",
                title=f"Live employee record — {employee.full_name}",
                source_type="live_employee",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Employee: {employee.full_name}. Employee number: {employee.employee_number}. "
                    f"Department: {department}. Job title: {employee.job_title or 'Not specified'}. "
                    f"Manager: {manager}. Leader: {leader}. Work email: {employee.work_email or 'Not specified'}. "
                    f"Employment status: {employee.employment_status}. "
                    f"Hire date: {employee.hire_date.isoformat() if employee.hire_date else 'Not specified'}."
                ),
                metadata={
                    "employee_id": employee.id,
                    "employee_number": employee.employee_number,
                    "title": employee.full_name,
                },
            )

        account_query = select(User).where(User.company_id == company_id)
        if not is_admin:
            account_query = account_query.where(User.id == current_user.user_id)
        accounts = self.session.scalars(
            account_query.order_by(User.username).limit(1000)
        ).unique().all()
        for account in accounts:
            linked_employee = account.employee
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:account:{account.id}",
                title=f"Live user account — {account.username}",
                source_type="live_account",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Username: {account.username}. Account email: {account.email}. "
                    f"Access: {'Admin' if int(account.clearance) == 1 else 'User'}. "
                    f"Account active: {'Yes' if account.is_active else 'No'}. "
                    f"Linked employee: {linked_employee.full_name if linked_employee else 'Not linked'}."
                ),
                metadata={"user_id": account.id, "title": account.username},
            )

        balance_query = select(LeaveBalance).where(LeaveBalance.company_id == company_id)
        if not is_admin:
            balance_query = balance_query.where(LeaveBalance.employee_id == (employee_id or -1))
        balances = self.session.scalars(
            balance_query.order_by(LeaveBalance.year.desc(), LeaveBalance.id.desc()).limit(1000)
        ).unique().all()
        for balance in balances:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:leave-balance:{balance.id}",
                title=f"Live leave credits — {balance.employee.full_name} — {balance.leave_type.name} {balance.year}",
                source_type="live_leave_balance",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Employee: {balance.employee.full_name}. Employee number: {balance.employee.employee_number}. "
                    f"Leave type: {balance.leave_type.name} ({balance.leave_type.code}). Year: {balance.year}. "
                    f"Beginning credit: {balance.beginning_credit_days} days. Credit: {balance.credit_days} days. "
                    f"Adjustment: {balance.adjustment_days} days. Used: {balance.used_days} days. "
                    f"Reserved: {balance.reserved_days} days. Converted to cash: {balance.converted_to_cash_days} days. "
                    f"Available credits: {balance.available_credits} days."
                ),
                metadata={
                    "employee_id": balance.employee_id,
                    "leave_type": balance.leave_type.name,
                    "year": balance.year,
                },
            )

        request_query = select(LeaveRequest).where(LeaveRequest.company_id == company_id)
        if not is_admin:
            request_query = request_query.where(LeaveRequest.employee_id == (employee_id or -1))
        leave_requests = self.session.scalars(
            request_query.order_by(LeaveRequest.submitted_at.desc(), LeaveRequest.id.desc()).limit(500)
        ).unique().all()
        for leave_request in leave_requests:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:leave-request:{leave_request.id}",
                title=f"Live leave request — {leave_request.public_id or leave_request.id}",
                source_type="live_leave_request",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Leave request ID: {leave_request.public_id or leave_request.id}. "
                    f"Employee: {leave_request.employee.full_name}. Leave type: {leave_request.leave_type.name}. "
                    f"Start date: {leave_request.start_date.isoformat()}. End date: {leave_request.end_date.isoformat()}. "
                    f"Requested days: {leave_request.requested_days}. Status: {leave_request.status}. "
                    f"Duration code: {leave_request.duration_code}. Reason code: {leave_request.reason_code}. "
                    f"Reason for Leave Others: {leave_request.reason_other or 'Not applicable'}. "
                    f"Filed by: {leave_request.filed_by_employee.full_name if leave_request.filed_by_employee else leave_request.employee.full_name}. "
                    f"Approval stage: {leave_request.approval_stage}. "
                    f"Cancellation status: {leave_request.cancellation_status}."
                ),
                metadata={
                    "leave_request_id": leave_request.id,
                    "public_id": leave_request.public_id,
                    "employee_id": leave_request.employee_id,
                },
            )

        attendance_query = select(AttendanceRecord).where(AttendanceRecord.company_id == company_id)
        if not is_admin:
            attendance_query = attendance_query.where(AttendanceRecord.employee_id == (employee_id or -1))
        attendance_records = self.session.scalars(
            attendance_query.order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.id.desc()).limit(500)
        ).unique().all()
        for record in attendance_records:
            session_summary = "; ".join(
                f"{item.work_status} actual {item.actual_time_in.isoformat()} to "
                f"{item.actual_time_out.isoformat() if item.actual_time_out else 'OPEN'}, "
                f"rounded {item.rounded_time_in.isoformat()} to "
                f"{item.rounded_time_out.isoformat() if item.rounded_time_out else 'OPEN'}"
                for item in record.sessions
            ) or "No work sessions"
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:attendance:{record.id}",
                title=f"Live attendance — {record.employee.full_name} — {record.attendance_date.isoformat()}",
                source_type="live_attendance",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Employee: {record.employee.full_name}. Attendance date: {record.attendance_date.isoformat()}. "
                    f"Work status: {record.work_status or 'Not set'}. "
                    f"Time In: {record.time_in.isoformat() if record.time_in else 'Not set'}. "
                    f"Time Out: {record.time_out.isoformat() if record.time_out else 'Not set'}. "
                    f"Total hours: {record.total_hours}. Overtime hours: {record.ot_hours}. "
                    f"Leave duration code: {record.leave_duration_code or 'None'}. "
                    f"Leave hours: {record.leave_hours}. Undertime hours: {record.undertime_hours}. "
                    f"Sessions: {session_summary}. "
                    f"Status source: {record.status_source}."
                ),
                metadata={
                    "employee_id": record.employee_id,
                    "attendance_date": record.attendance_date.isoformat(),
                },
            )

        overtime_query = select(OvertimeRequest).where(
            OvertimeRequest.company_id == company_id
        )
        if not is_admin:
            overtime_query = overtime_query.where(
                OvertimeRequest.employee_id == (employee_id or -1)
            )
        overtime_requests = self.session.scalars(
            overtime_query.order_by(
                OvertimeRequest.submitted_at.desc(),
                OvertimeRequest.id.desc(),
            ).limit(500)
        ).unique().all()
        for overtime_request in overtime_requests:
            self._add_document(
                documents,
                document_id=(
                    f"company:{company_id}:live:overtime-request:"
                    f"{overtime_request.id}"
                ),
                title=f"Live overtime request — {overtime_request.public_id}",
                source_type="live_overtime_request",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Overtime request ID: {overtime_request.public_id}. "
                    f"Employee: {overtime_request.employee.full_name}. "
                    f"Date rendered: {overtime_request.date_rendered.isoformat()}. "
                    f"OT type: {overtime_request.ot_type}. Purpose: "
                    f"{overtime_request.ot_purpose}. Submitted estimated hours: "
                    f"{overtime_request.estimated_hours}. DTR detected hours: "
                    f"{overtime_request.dtr_estimated_hours}. DTR mismatch: "
                    f"{'Yes' if overtime_request.has_dtr_mismatch else 'No'}. "
                    f"Travel fare: {overtime_request.travel_fare or 'None'}. "
                    f"Travel route: {overtime_request.travel_route or 'None'}. "
                    f"Dinner break: "
                    f"{'Yes' if overtime_request.dinner_break_flag else 'No'}. "
                    f"Status: {overtime_request.status}. Reviewer comment: "
                    f"{overtime_request.reviewer_comment or 'None'}."
                ),
                metadata={
                    "overtime_request_id": overtime_request.id,
                    "public_id": overtime_request.public_id,
                    "employee_id": overtime_request.employee_id,
                    "date_rendered": overtime_request.date_rendered.isoformat(),
                },
            )

        now = datetime.now(timezone.utc)
        announcement_query = select(Announcement).where(Announcement.company_id == company_id)
        if not is_admin:
            announcement_query = announcement_query.where(
                Announcement.status == "published",
                or_(Announcement.publish_at.is_(None), Announcement.publish_at <= now),
                or_(Announcement.expires_at.is_(None), Announcement.expires_at >= now),
            )
        announcements = self.session.scalars(
            announcement_query.order_by(Announcement.publish_at.desc(), Announcement.id.desc()).limit(250)
        ).all()
        for announcement in announcements:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:announcement:{announcement.id}",
                title=f"Live announcement — {announcement.title}",
                source_type="live_announcement",
                company_id=company_id,
                role_scope="admin" if is_admin else "shared",
                text=(
                    f"Announcement ID: {announcement.public_id or announcement.id}. Title: {announcement.title}. "
                    f"Category: {announcement.category}. Summary: {announcement.summary}. "
                    f"Description: {announcement.content}. Status: {announcement.status}. "
                    f"Publish date: {announcement.publish_at.isoformat() if announcement.publish_at else 'Not specified'}. "
                    f"Expiry: {announcement.expires_at.isoformat() if announcement.expires_at else 'No expiry'}."
                ),
                metadata={"announcement_id": announcement.id, "title": announcement.title},
            )

        form_query = select(CompanyForm).where(CompanyForm.company_id == company_id)
        if not is_admin:
            form_query = form_query.where(
                CompanyForm.status == "active",
                CompanyForm.trashed_at.is_(None),
            )
        forms = self.session.scalars(
            form_query.order_by(CompanyForm.title).limit(250)
        ).all()
        for form in forms:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:company-form:{form.id}",
                title=f"Live company form — {form.title}",
                source_type="live_company_form",
                company_id=company_id,
                role_scope="admin" if is_admin else "shared",
                text=(
                    f"Company form ID: {form.public_id}. Title: {form.title}. Category: {form.category}. "
                    f"Description: {form.description or 'No description'}. Status: {form.status}. "
                    f"Filename: {form.original_filename}. Employee submission allowed: "
                    f"{'Yes' if form.allow_employee_submission else 'No'}."
                ),
                metadata={"company_form_id": form.id, "title": form.title},
            )

            # Active Company Form/Documents files contribute their actual
            # readable content to company knowledge. This lets a natural
            # question search the document body, not only title/filename
            # metadata. Unsupported/old binary formats remain metadata-only.
            if form.status == "active" and form.trashed_at is None:
                extracted_form_text = self.company_form_extractor.extract(form)
                if extracted_form_text:
                    file_key = f"company-form:{form.id}"
                    raw_sections = [
                        (section_label, section_text, None)
                        for section_label, section_text in _document_sections(extracted_form_text)
                    ]
                    prepared_chunks = _prepare_document_chunks_detailed(
                        raw_sections,
                        chunk_size=int(self.settings.company_document_chunk_size),
                        overlap=int(self.settings.company_document_chunk_overlap),
                        adaptive=bool(self.settings.adaptive_chunking_enabled),
                        min_words=int(self.settings.company_document_chunk_min_words),
                        target_words=int(self.settings.company_document_chunk_target_words),
                        max_words=int(self.settings.company_document_chunk_max_words),
                        overlap_ratio=float(self.settings.adaptive_overlap_ratio),
                        overlap_min_words=int(self.settings.adaptive_overlap_min_words),
                        overlap_max_words=int(self.settings.adaptive_overlap_max_words),
                    )
                    self._record_chunk_diagnostics(
                        source="company_form_content",
                        filename=str(form.original_filename or form.title),
                        sections=raw_sections,
                        chunks=prepared_chunks,
                        min_words=int(self.settings.company_document_chunk_min_words),
                        target_words=int(self.settings.company_document_chunk_target_words),
                        max_words=int(self.settings.company_document_chunk_max_words),
                    )
                    total_chunks = len(prepared_chunks)
                    for chunk_index, prepared in enumerate(prepared_chunks, start=1):
                        section_label = prepared.section
                        chunk = prepared.text
                        section_page = prepared.page_number
                        contextual_chunk = (
                            f"Document: {form.title}. File: {form.original_filename}. "
                            f"Section: {section_label}. {chunk}"
                        )
                        self._add_document(
                            documents,
                            document_id=(
                                f"company:{company_id}:company-form-content:"
                                f"{form.id}:{chunk_index}"
                            ),
                            title=f"{form.title} — {section_label}",
                            source_type="company_form_content",
                            company_id=company_id,
                            role_scope="admin" if is_admin else "shared",
                            text=contextual_chunk,
                            metadata={
                                "company_form_id": form.id,
                                "file_key": file_key,
                                "title": form.title,
                                "filename": form.original_filename,
                                "section": section_label,
                                "page_number": (
                                    section_page
                                    if section_page is not None
                                    else (
                                        int(page_match.group(1))
                                        if (
                                            page_match := re.match(
                                                r"^Page\s+(\d+)(?:\s+[—-]\s+.*)?$",
                                                section_label,
                                                re.I,
                                            )
                                        )
                                        else None
                                    )
                                ),
                                "chunk_index": chunk_index,
                                "total_chunks": total_chunks,
                                "chunk_word_count": prepared.word_count,
                                "chunk_overlap_words": prepared.overlap_words,
                                "chunk_boundary_reason": prepared.boundary_reason,
                                "section_chunk_index": prepared.section_chunk_index,
                                "section_chunk_total": prepared.section_chunk_total,
                                "continuation_before": int(prepared.continuation_before),
                                "continuation_after": int(prepared.continuation_after),
                                "chunking_strategy": (
                                    "adaptive-structure-aware"
                                    if self.settings.adaptive_chunking_enabled
                                    else "legacy-fixed-budget"
                                ),
                            },
                        )

        submission_query = select(CompanyFormSubmission).where(
            CompanyFormSubmission.company_id == company_id
        )
        if not is_admin:
            submission_query = submission_query.where(
                CompanyFormSubmission.employee_id == (employee_id or -1)
            )
        submissions = self.session.scalars(
            submission_query.order_by(
                CompanyFormSubmission.created_at.desc(),
                CompanyFormSubmission.id.desc(),
            ).limit(500)
        ).unique().all()
        for submission in submissions:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:form-submission:{submission.id}",
                title=f"Live form submission — {submission.public_id}",
                source_type="live_company_form_submission",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Submission ID: {submission.public_id}. Form: {submission.form.title}. "
                    f"Employee: {submission.employee.full_name}. Status: {submission.status}. "
                    f"Submitted filename: {submission.original_filename}. "
                    f"Employee notes: {submission.notes or 'None'}. "
                    f"Admin note: {submission.admin_note or 'None'}. "
                    f"Reviewed at: {submission.reviewed_at.isoformat() if submission.reviewed_at else 'Not reviewed'}."
                ),
                metadata={
                    "submission_id": submission.id,
                    "employee_id": submission.employee_id,
                    "company_form_id": submission.form_id,
                },
            )

        training_query = select(EmployeeTraining).where(
            EmployeeTraining.company_id == company_id
        )
        if not is_admin:
            training_query = training_query.where(
                EmployeeTraining.employee_id == (employee_id or -1)
            )
        trainings = self.session.scalars(
            training_query.order_by(
                EmployeeTraining.employee_id,
                EmployeeTraining.display_order,
                EmployeeTraining.id,
            ).limit(1000)
        ).unique().all()
        for training in trainings:
            self._add_document(
                documents,
                document_id=f"company:{company_id}:live:training:{training.id}",
                title=f"Live employee training — {training.employee.full_name} — {training.title}",
                source_type="live_employee_training",
                company_id=company_id,
                role_scope=live_scope,
                text=(
                    f"Employee: {training.employee.full_name}. Training: {training.title}. "
                    f"Completed: {'Yes' if training.is_completed else 'No'}."
                ),
                metadata={
                    "employee_id": training.employee_id,
                    "training_id": training.id,
                    "title": training.title,
                },
            )

        if is_admin:
            reminders = self.session.scalars(
                select(EventReminder).where(
                    EventReminder.company_id == company_id
                ).order_by(
                    EventReminder.event_start_at.desc(),
                    EventReminder.id.desc(),
                ).limit(250)
            ).all()
            for reminder in reminders:
                self._add_document(
                    documents,
                    document_id=f"company:{company_id}:live:event-reminder:{reminder.id}",
                    title=f"Live event reminder — {reminder.title}",
                    source_type="live_event_reminder",
                    company_id=company_id,
                    role_scope="admin",
                    text=(
                        f"Reminder ID: {reminder.public_id or reminder.id}. Title: {reminder.title}. "
                        f"Category: {reminder.category}. Notes: {reminder.notes or 'None'}. "
                        f"Event starts: {reminder.event_start_at.isoformat()}. "
                        f"Event ends: {reminder.event_end_at.isoformat() if reminder.event_end_at else 'Not specified'}. "
                        f"Status: {reminder.status}."
                    ),
                    metadata={"reminder_id": reminder.id, "title": reminder.title},
                )

    def build(
        self,
        *,
        current_user: AuthenticatedUser,
        role_scope: str,
        trace: TerminalChatTrace | None = None,
    ) -> list[KnowledgeDocument]:
        company_id = current_user.company_id
        self._trace = trace
        self._chunk_batch_summary = []
        documents: list[KnowledgeDocument] = []
        guide_groups = ["shared", role_scope]
        for group in guide_groups:
            for index, (title, text) in enumerate(_PORTAL_GUIDES[group], start=1):
                documents.append(KnowledgeDocument(
                    document_id=f"company:{company_id}:portal:{group}:{index}",
                    text=text,
                    title=title,
                    source_type="portal_guide",
                    company_id=company_id,
                    role_scope=group,
                    metadata={"title": title, "group": group},
                ))

        self._add_live_company_records(
            documents,
            current_user=current_user,
            role_scope=role_scope,
        )

        violation_service = PolicyViolationService(self.session)
        violation_date = datetime.now(
            ZoneInfo(get_settings().display_timezone)
        ).date()
        for violation in violation_service.list_employee_visible(
            company_id=company_id,
            as_of_date=violation_date,
        ):
            related_policy = violation_service.related_policy_label(
                company_id=company_id,
                violation=violation,
            )
            self._add_document(
                documents,
                document_id=(
                    f"company:{company_id}:policy-violation:{violation.id}"
                ),
                title=(
                    f"{violation.violation_code} — {violation.offense_title}"
                ),
                source_type="policy_violation",
                company_id=company_id,
                role_scope="shared",
                text=(
                    f"Violation code: {violation.violation_code}. "
                    f"Violation / offense: {violation.offense_title}. "
                    f"Category: {violation.category}. Severity: {violation.severity}. "
                    f"Description: {violation.description}. "
                    f"1st offense action: {violation.first_offense_action}. "
                    f"2nd offense action: {violation.second_offense_action}. "
                    f"3rd offense action: {violation.third_offense_action}. "
                    f"Final / maximum action: {violation.final_action}. "
                    f"Related policy: {related_policy}. "
                    f"Effective date: "
                    f"{violation.effective_date.isoformat() if violation.effective_date else 'Immediate'}."
                ),
                metadata={
                    "violation_id": violation.id,
                    "violation_code": violation.violation_code,
                    "severity": violation.severity,
                    "category": violation.category,
                    "related_policy_id": violation.related_policy_id,
                },
            )

        rows = PolicySectionRepository(self.session).list_searchable(
            company_id=company_id,
            as_of_date=datetime.now(
                ZoneInfo(get_settings().display_timezone)
            ).date(),
        )
        policy_files: dict[
            tuple[int, int],
            list[tuple[object, object, object]],
        ] = defaultdict(list)
        for policy, document, section in rows:
            policy_files[(int(policy.id), int(document.id))].append(
                (policy, document, section)
            )

        for grouped_rows in policy_files.values():
            policy = grouped_rows[0][0]
            document = grouped_rows[0][1]
            file_key = f"policy:{policy.id}:document:{document.id}"
            raw_sections = [
                    (
                        str(section.heading or "Policy Details"),
                        str(section.text or ""),
                        section.page_number,
                    )
                    for _policy, _document, section in grouped_rows
                ]
            prepared_chunks = _prepare_document_chunks_detailed(
                raw_sections,
                chunk_size=int(self.settings.policy_chunk_size),
                overlap=int(self.settings.policy_chunk_overlap),
                adaptive=bool(self.settings.adaptive_chunking_enabled),
                min_words=int(self.settings.policy_chunk_min_words),
                target_words=int(self.settings.policy_chunk_target_words),
                max_words=int(self.settings.policy_chunk_max_words),
                overlap_ratio=float(self.settings.adaptive_overlap_ratio),
                overlap_min_words=int(self.settings.adaptive_overlap_min_words),
                overlap_max_words=int(self.settings.adaptive_overlap_max_words),
            )
            self._record_chunk_diagnostics(
                source="policy",
                filename=str(document.original_filename or policy.title),
                sections=raw_sections,
                chunks=prepared_chunks,
                min_words=int(self.settings.policy_chunk_min_words),
                target_words=int(self.settings.policy_chunk_target_words),
                max_words=int(self.settings.policy_chunk_max_words),
            )
            total_chunks = len(prepared_chunks)
            for chunk_index, prepared in enumerate(prepared_chunks, start=1):
                section_label = prepared.section
                chunk = prepared.text
                page_number = prepared.page_number
                contextual_chunk = (
                    f"Policy: {policy.title}. Version: {policy.version}. "
                    f"Section: {section_label}. {chunk}"
                )
                documents.append(KnowledgeDocument(
                    document_id=(
                        f"company:{company_id}:policy:{policy.id}:"
                        f"{document.id}:{chunk_index}"
                    ),
                    text=contextual_chunk,
                    title=f"{policy.title} — {section_label}",
                    source_type="policy",
                    company_id=company_id,
                    role_scope="shared",
                    metadata={
                        "policy_id": policy.id,
                        "policy_document_id": document.id,
                        "file_key": file_key,
                        "title": policy.title,
                        "section": section_label,
                        "version": policy.version,
                        "filename": document.original_filename,
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "chunk_word_count": prepared.word_count,
                        "chunk_overlap_words": prepared.overlap_words,
                        "chunk_boundary_reason": prepared.boundary_reason,
                        "section_chunk_index": prepared.section_chunk_index,
                        "section_chunk_total": prepared.section_chunk_total,
                        "continuation_before": int(prepared.continuation_before),
                        "continuation_after": int(prepared.continuation_after),
                        "chunking_strategy": (
                            "adaptive-structure-aware"
                            if self.settings.adaptive_chunking_enabled
                            else "legacy-fixed-budget"
                        ),
                    },
                ))
        # Published policies created directly in the editor have authoritative
        # text in hr_policies.content but no uploaded-document section rows.
        # A section-only index silently excluded them from *both* BM25 and
        # Qdrant. Include these policy versions using the same source-aware
        # chunker and company/effective-date visibility rules. Never re-add
        # policies already represented by extracted document sections, and
        # never include trashed, draft, future or cross-tenant versions.
        indexed_policy_ids = {policy_id for policy_id, _document_id in policy_files}
        policy_date = datetime.now(
            ZoneInfo(get_settings().display_timezone)
        ).date()
        text_only_count = 0
        for policy in PolicyRepository(self.session).list_published(
            company_id=company_id, as_of_date=policy_date,
        ):
            if policy.id in indexed_policy_ids or not _clean_text(policy.content):
                continue
            file_key = f"policy:{policy.id}:record"
            section_label = "Published Policy Text"
            raw_sections = [(section_label, str(policy.content), None)]
            prepared_chunks = _prepare_document_chunks_detailed(
                raw_sections,
                chunk_size=int(self.settings.policy_chunk_size),
                overlap=int(self.settings.policy_chunk_overlap),
                adaptive=bool(self.settings.adaptive_chunking_enabled),
                min_words=int(self.settings.policy_chunk_min_words),
                target_words=int(self.settings.policy_chunk_target_words),
                max_words=int(self.settings.policy_chunk_max_words),
                overlap_ratio=float(self.settings.adaptive_overlap_ratio),
                overlap_min_words=int(self.settings.adaptive_overlap_min_words),
                overlap_max_words=int(self.settings.adaptive_overlap_max_words),
            )
            self._record_chunk_diagnostics(
                source="policy-record",
                filename=str(policy.title),
                sections=raw_sections,
                chunks=prepared_chunks,
                min_words=int(self.settings.policy_chunk_min_words),
                target_words=int(self.settings.policy_chunk_target_words),
                max_words=int(self.settings.policy_chunk_max_words),
            )
            total_chunks = len(prepared_chunks)
            for chunk_index, prepared in enumerate(prepared_chunks, start=1):
                documents.append(KnowledgeDocument(
                    document_id=(
                        f"company:{company_id}:policy:{policy.id}:record:{chunk_index}"
                    ),
                    text=(
                        f"Policy: {policy.title}. Version: {policy.version}. "
                        f"Section: {prepared.section}. {prepared.text}"
                    ),
                    title=f"{policy.title} — {prepared.section}",
                    source_type="policy",
                    company_id=company_id,
                    role_scope="shared",
                    metadata={
                        "policy_id": policy.id,
                        "file_key": file_key,
                        "title": policy.title,
                        "section": prepared.section,
                        "version": policy.version,
                        # This is a database policy title, not a fabricated
                        # uploaded filename. It remains citable via policy_id.
                        "filename": policy.title,
                        "page_number": None,
                        "chunk_index": chunk_index,
                        "total_chunks": total_chunks,
                        "section_chunk_index": prepared.section_chunk_index,
                        "section_chunk_total": prepared.section_chunk_total,
                        "continuation_before": int(prepared.continuation_before),
                        "continuation_after": int(prepared.continuation_after),
                        "chunk_word_count": prepared.word_count,
                        "chunk_overlap_words": prepared.overlap_words,
                        "chunk_boundary_reason": prepared.boundary_reason,
                        "chunking_strategy": (
                            "adaptive-structure-aware"
                            if self.settings.adaptive_chunking_enabled
                            else "legacy-fixed-budget"
                        ),
                    },
                ))
            text_only_count += 1
        if self._trace is not None:
            self._trace.line(
                "PUBLISHED POLICY INGESTION",
                f"indexed_document_policies={len(indexed_policy_ids)}; "
                f"text_only_policies={text_only_count}; "
                f"company_id={company_id}",
            )
            self._trace.chunking_batch_summary(self._chunk_batch_summary)
        return documents


class BM25Retriever:
    """Small dependency-free BM25 implementation used by every installation."""

    def search(self, query: str, documents: list[KnowledgeDocument], top_k: int) -> list[RetrievedDocument]:
        if not documents:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        tokenized = [_tokenize(_document_search_text(doc)) for doc in documents]
        n = len(tokenized)
        avgdl = sum(len(tokens) for tokens in tokenized) / max(n, 1)
        df: dict[str, int] = {}
        for tokens in tokenized:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        k1, b = 1.5, 0.75
        scored: list[RetrievedDocument] = []
        for doc, tokens in zip(documents, tokenized):
            frequencies: dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            score = 0.0
            dl = len(tokens)
            for term in query_terms:
                tf = frequencies.get(term, 0)
                if not tf:
                    continue
                idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
                score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1))))
            if score > 0:
                scored.append(RetrievedDocument(doc, score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


class QdrantRetriever:
    """Optional local Qdrant + multilingual-e5 vector retrieval.

    Qdrant runs in persistent local mode so the Chat Assistant keeps its
    offline-first deployment behavior and does not require a separate vector
    database service. Each query is restricted to the exact authorized
    document-set signature for the current request, preventing vectors from a
    different company/user/role snapshot from consuming result slots.
    """

    _indexed_signatures: set[str] = set()
    _clients: dict[str, object] = {}
    _client_lock = threading.RLock()
    # Streamlit recreates HybridRetriever for each question. Keep one local
    # embedding model per configured model name for the *Python process*, not
    # one per file/chunk retriever or user. No user queries or embeddings are
    # stored in this cache; Qdrant authorization remains request-scoped.
    _embedding_models: dict[str, object] = {}
    _embedding_load_lock = threading.RLock()
    _embedding_encode_locks: dict[str, threading.RLock] = {}

    def __init__(self, *, collection_suffix: str = "") -> None:
        self.settings = get_chat_assistant_settings()
        self.collection_suffix = collection_suffix
        self._embedding_model = None
        self._model_cache_state = "not-loaded"
        self._last_diagnostic = "not-run"

    @property
    def diagnostic(self) -> str:
        """Return a concise, non-sensitive status for request diagnostics."""

        return self._last_diagnostic

    def _set_diagnostic(self, value: str) -> None:
        self._last_diagnostic = _clean_text(value)[:900] or "unknown"

    @staticmethod
    def _cached_embedding_source(name: str) -> str | None:
        """Use a *complete-enough* existing Hugging Face snapshot locally.

        Local-first avoids unauthenticated HF Hub metadata requests on every
        new Windows process. It is NOT forced offline: a first-run cache miss
        keeps the existing online/model-install behavior. Only model files are
        resolved here; no user data, employee records or query strings enter
        the cache.
        """
        source = Path(name).expanduser()
        if source.is_dir():
            return str(source)
        # Avoid treating absolute/missing paths or unusual names as Hub IDs.
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", name):
            return None
        try:
            from huggingface_hub import snapshot_download
            location = Path(snapshot_download(repo_id=name, local_files_only=True))
        except Exception:  # Optional local cache lookup must never prevent Hub fallback.
            return None
        # SentenceTransformers can wrap an ordinary Transformers model if it
        # has a model config and tokenizer; actual validation is in the model
        # constructor. If a partial snapshot fails there, retry by Hub name.
        if location.is_dir() and (location / "modules.json").is_file():
            return str(location)
        if location.is_dir() and (location / "config.json").is_file() and any(
            (location / item).is_file()
            for item in ("tokenizer.json", "tokenizer_config.json", "vocab.txt", "sentencepiece.bpe.model")
        ):
            return str(location)
        return None

    def _model(self):
        if self._embedding_model is not None:
            self._model_cache_state = "instance"
            return self._embedding_model
        name = str(self.settings.embedding_model)
        with self._embedding_load_lock:
            model = self._embedding_models.get(name)
            if model is None:
                from sentence_transformers import SentenceTransformer
                model_source = (
                    self._cached_embedding_source(name)
                    if bool(getattr(self.settings, "embedding_prefer_local_cache", True))
                    else None
                )
                if model_source and model_source != name:
                    try:
                        model = SentenceTransformer(model_source)
                        self._model_cache_state = "loaded-local-cache"
                    except Exception:  # A partial local snapshot must not block existing loading.
                        # A partially downloaded cache must not break startup.
                        model = SentenceTransformer(name)
                        self._model_cache_state = "loaded-hub-fallback"
                else:
                    model = SentenceTransformer(name)
                    self._model_cache_state = "loaded"
                self._embedding_models[name] = model
                self._embedding_encode_locks[name] = threading.RLock()
            else:
                self._model_cache_state = "reused"
            self._embedding_model = model
        return self._embedding_model

    @staticmethod
    def _signature(documents: list[KnowledgeDocument]) -> str:
        # Keep the same signature when the authorized snapshot is identical but
        # its iteration order changes after a Streamlit/application restart.
        payload = "|".join(
            f"{doc.document_id}:{hashlib.sha1(_document_search_text(doc).encode('utf-8')).hexdigest()}"
            for doc in sorted(documents, key=lambda item: item.document_id)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _encode(self, model, values: list[str]):
        """Encode in bounded batches while supporting older/test model doubles."""

        name = str(self.settings.embedding_model)
        with self._embedding_load_lock:
            shared = self._embedding_models.get(name) is model
            encode_lock = self._embedding_encode_locks.get(name) if shared else None

        def do_encode():
            kwargs = {"normalize_embeddings": True}
            batch_size = max(
                1, int(getattr(self.settings, "embedding_batch_size", 64))
            )
            try:
                return model.encode(values, batch_size=batch_size, **kwargs)
            except TypeError:
                return model.encode(values, **kwargs)

        if encode_lock is not None:
            # A shared transformer model is invoked by concurrent Admin and
            # Employee sessions. Serialize inference on this model instance.
            with encode_lock:
                return do_encode()
        return do_encode()

    def _client(self):
        from qdrant_client import QdrantClient

        path = str(Path(self.settings.qdrant_dir).resolve())
        with self._client_lock:
            client = self._clients.get(path)
            if client is None:
                Path(path).mkdir(parents=True, exist_ok=True)
                client = QdrantClient(
                    path=path,
                    force_disable_check_same_thread=True,
                )
                self._clients[path] = client
            return client

    @staticmethod
    def _point_id(collection_name: str, partition_hash: str, document_id: str) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"ai-hr-assistant:qdrant:{collection_name}:{partition_hash}:{document_id}",
            )
        )

    def search(
        self,
        query: str,
        documents: list[KnowledgeDocument],
        top_k: int,
        *,
        access_partition: str | None = None,
    ) -> list[RetrievedDocument]:
        vector_started = time.monotonic()
        try:
            from qdrant_client import models
        except Exception as exc:
            self._set_diagnostic(
                f"unavailable: qdrant-client import failed ({type(exc).__name__})"
            )
            return []
        if not documents:
            self._set_diagnostic("skipped: no authorized documents")
            return []
        try:
            try:
                model = self._model()
            except ModuleNotFoundError as exc:
                self._set_diagnostic(
                    "unavailable: local embedding runtime is not installed "
                    f"({type(exc).__name__})"
                )
                return []
            except Exception as exc:
                self._set_diagnostic(
                    "unavailable: local embedding model could not be loaded "
                    f"({type(exc).__name__})"
                )
                return []
            client = self._client()
            model_setup_seconds = time.monotonic() - vector_started
            # An alternate embedding model may have different vector dimensions.
            # Never reuse/overwrite a collection trained with another model;
            # isolate each model while retaining existing Qdrant data.
            model_name = str(self.settings.embedding_model)
            model_fingerprint = hashlib.sha1(model_name.encode("utf-8")).hexdigest()[:8]
            collection_name = f"{self.settings.qdrant_collection}{self.collection_suffix}"
            if model_name != "intfloat/multilingual-e5-small":
                # Preserve the original production collection for the default
                # model. Isolate alternatives by model fingerprint so a 768-d
                # test cannot overwrite an existing 384-d E5 collection.
                collection_name += f"_{model_fingerprint}"
            signature = self._signature(documents)
            if access_partition is None:
                company = documents[0].company_id
                roles = ",".join(sorted({doc.role_scope for doc in documents}))
                access_partition = f"company:{company}:roles:{roles}"
            partition_hash = hashlib.sha1(
                access_partition.encode("utf-8")
            ).hexdigest()[:16]
            retrieval_scope = f"{partition_hash}:{signature}"
            vector_ids = [
                self._point_id(collection_name, partition_hash, doc.document_id)
                for doc in documents
            ]
            cache_key = (
                f"{Path(self.settings.qdrant_dir).resolve()}:{collection_name}:"
                f"{retrieval_scope}"
            )

            index_started = time.monotonic()
            with self._client_lock:
                collection_exists = client.collection_exists(collection_name)
                index_required = (
                    not collection_exists or cache_key not in self._indexed_signatures
                )

                # Reuse the persisted authorized snapshot after an app restart.
                # The in-memory signature set is only an optimization; it must
                # not force a full re-embedding on every new Python process.
                if collection_exists and index_required:
                    try:
                        existing = client.count(
                            collection_name=collection_name,
                            count_filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="retrieval_scope",
                                        match=models.MatchValue(value=retrieval_scope),
                                    )
                                ]
                            ),
                            exact=True,
                        )
                        if int(getattr(existing, "count", 0) or 0) >= len(documents):
                            self._indexed_signatures.add(cache_key)
                            index_required = False
                    except Exception:
                        # Older/fake clients may not expose count(); refreshing
                        # the current authorized snapshot remains safe.
                        pass

            if index_required:
                texts = [f"passage: {_document_search_text(doc)}" for doc in documents]
                encoded = self._encode(model, texts)
                embeddings = (
                    encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
                )
                if not embeddings or not embeddings[0]:
                    self._set_diagnostic("error: embedding model returned no vectors")
                    return []

                with self._client_lock:
                    if not client.collection_exists(collection_name):
                        client.create_collection(
                            collection_name=collection_name,
                            vectors_config=models.VectorParams(
                                size=len(embeddings[0]),
                                distance=models.Distance.COSINE,
                            ),
                        )

                    points = [
                        models.PointStruct(
                            id=vector_id,
                            vector=embedding,
                            payload={
                                "document_id": doc.document_id,
                                "company_id": doc.company_id,
                                "role_scope": doc.role_scope,
                                "title": doc.title,
                                "source_type": doc.source_type,
                                "retrieval_signature": signature,
                                "retrieval_scope": retrieval_scope,
                                "payload": json.dumps(doc.metadata, default=str),
                            },
                        )
                        for vector_id, doc, embedding in zip(
                            vector_ids, documents, embeddings
                        )
                    ]
                    upsert_batch = max(
                        1, int(getattr(self.settings, "qdrant_upsert_batch_size", 128))
                    )
                    for batch_start in range(0, len(points), upsert_batch):
                        client.upsert(
                            collection_name=collection_name,
                            points=points[batch_start:batch_start + upsert_batch],
                            wait=True,
                        )
                    self._indexed_signatures.add(cache_key)

            index_seconds = time.monotonic() - index_started
            query_embed_started = time.monotonic()
            encoded_query = self._encode(model, [f"query: {query}"])
            query_vectors = (
                encoded_query.tolist()
                if hasattr(encoded_query, "tolist")
                else list(encoded_query)
            )
            if not query_vectors:
                self._set_diagnostic("error: query embedding was empty")
                return []
            query_embedding = query_vectors[0]
            query_embed_seconds = time.monotonic() - query_embed_started
            qdrant_query_started = time.monotonic()
            with self._client_lock:
                result = client.query_points(
                    collection_name=collection_name,
                    query=query_embedding,
                    query_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="retrieval_scope",
                                match=models.MatchValue(value=retrieval_scope),
                            )
                        ]
                    ),
                    limit=min(max(1, int(top_k)), len(documents)),
                    with_payload=False,
                    with_vectors=False,
                )

            qdrant_query_seconds = time.monotonic() - qdrant_query_started
            lookup = {
                vector_id: doc
                for vector_id, doc in zip(vector_ids, documents)
            }
            output: list[RetrievedDocument] = []
            for point in getattr(result, "points", []) or []:
                doc = lookup.get(str(point.id))
                if doc is not None:
                    output.append(
                        RetrievedDocument(doc, max(0.0, float(point.score)))
                    )
            self._set_diagnostic(
                f"ok: collection={collection_name}; "
                f"index={'rebuilt' if index_required else 'cached'}; "
                f"authorized={len(documents)}; returned={len(output)}; "
                f"model_cache={self._model_cache_state}; "
                f"model_setup_s={model_setup_seconds:.3f}; "
                f"index_s={index_seconds:.3f}; "
                f"query_embed_s={query_embed_seconds:.3f}; "
                f"qdrant_query_s={qdrant_query_seconds:.3f}; "
                f"total_s={time.monotonic() - vector_started:.3f}"
            )
            return output
        except Exception as exc:
            self._set_diagnostic(
                f"error: vector retrieval failed ({type(exc).__name__})"
            )
            return []


class _LocalCrossEncoder:
    """Reuse one local reranker model; never implicitly download weights.

    Re-using the model avoids loading it for each 45-question terminal run.
    If it is missing or unavailable, BM25/Qdrant remains authoritative and
    the trace says explicitly why reranking was skipped.
    """
    _models: dict[str, object] = {}
    _lock = threading.RLock()

    @classmethod
    def get(cls, model_name: str, *, local_only: bool = True):
        with cls._lock:
            if model_name in cls._models:
                return cls._models[model_name]
            source = (QdrantRetriever._cached_embedding_source(model_name)
                      if local_only else None)
            if local_only and not source:
                return None
            from sentence_transformers import CrossEncoder
            model = CrossEncoder(source or model_name)
            cls._models[model_name] = model
            return model


def _rerank_candidates(
    query: str,
    candidates: list[RetrievedDocument],
    model: object,
) -> list[RetrievedDocument]:
    """Merge model relevance and hybrid ranking on a stable 0..1 scale.

    Some cross-encoders return unbounded logits and others probabilities. A
    sigmoid maps both to a comparable bounded number. Preserve a hybrid share
    so lexical evidence still affects close passages.
    """
    if not candidates:
        return []
    import math as _math
    raw = model.predict([(query, _document_search_text(x.document)[:1600]) for x in candidates])
    scores = list(raw)
    if len(scores) != len(candidates):
        raise ValueError("Reranker returned an unexpected score count")
    max_hybrid = max(1e-9, max(float(x.score) for x in candidates))
    output = []
    for item, score in zip(candidates, scores):
        value = max(-40.0, min(40.0, float(score)))
        semantic = 1.0 / (1.0 + _math.exp(-value))
        output.append(RetrievedDocument(item.document,
                                        0.7 * semantic + 0.3 * max(0., float(item.score)/max_hybrid)))
    output.sort(key=lambda item: item.score, reverse=True)
    return output


def _adaptive_subqueries(question: str, *, max_variants: int = 2) -> list[str]:
    """Cheap, bounded multi-query candidates for explicit coordinated asks.

    No model is called, no answers are generated, and no source/role filter is
    modified. Subqueries are only useful after the normal authorized file
    shortlist has been established. Ordinary and exact-policy questions have
    no variants. Separating on the *next interrogative* avoids splitting
    title phrases like 'Research and Development'.
    """
    clean = re.sub(r"\s+", " ", str(question or "")).strip(" ?.!")
    parts = re.split(
        r",\s*and\s+(?=(?:who|what|when|where|how|which)\b)",
        clean, maxsplit=3, flags=re.I,
    )
    if len(parts) < 2:
        return []
    first = parts[0].strip()
    # Extract user-specified subject only for search context. This is neither
    # an HR ontology nor a list of QA reference questions.
    subject_match = re.search(
        r"\b(?:attend|about|for|of|regarding)\s+(.{5,120})$", first, re.I,
    )
    subject = subject_match.group(1).strip() if subject_match else ""
    variants: list[str] = []
    for index, part in enumerate(parts[:max(1, min(int(max_variants), 3))]):
        variant = part.strip(" ?.!")
        if index and subject and not all(
            token in variant.casefold() for token in _meaningful_evidence_tokens(subject)[:2]
        ):
            variant = f"{variant} {subject}"
        if len(_meaningful_evidence_tokens(variant)) < 3:
            continue
        variant = variant[:200].rstrip()
        if variant.casefold() != clean.casefold() and variant not in variants:
            variants.append(variant)
    return variants[:max(0, min(int(max_variants), 3))]


def _merge_adaptive_bm25_candidates(
    question: str,
    base: list[RetrievedDocument],
    variant_hits: list[list[RetrievedDocument]],
    *,
    allowed_document_ids: set[str],
) -> list[RetrievedDocument]:
    """Fuse only authorized follow-up BM25 hits with existing hybrid ranking.

    Primary hybrid ranking remains authoritative. Small supplemental signals
    can surface a missing directly relevant chunk without performing another
    local vector-model search or generating variants with Ollama.
    """
    if not base or not variant_hits:
        return base
    by_id = {item.document.document_id: item for item in base}
    top = base[0].score
    floor = max(min(item.score for item in base), top * .38)
    for hits in variant_hits[:3]:
        for rank, item in enumerate(hits[:6], start=1):
            doc = item.document
            if doc.document_id not in allowed_document_ids:
                continue
            diagnostics = _passage_diagnostic(question, doc)
            if float(diagnostics.get("body_coverage") or 0.0) < .18:
                continue
            fit = _evidence_fit_bonus(question, doc)
            if fit < .25:
                continue
            existing = by_id.get(doc.document_id)
            bonus = .0025 / (1.0 + rank / 4.0)
            if existing is not None:
                by_id[doc.document_id] = RetrievedDocument(doc, existing.score + bonus)
            else:
                by_id[doc.document_id] = RetrievedDocument(
                    doc, min(top * .78, floor + bonus + .002 * min(fit, 1.0))
                )
    return sorted(by_id.values(), key=lambda item: item.score, reverse=True)


class HybridRetriever:
    """Company/role-safe, file-aware hybrid retrieval.

    Long policy and Company Form/Documents content is retrieved hierarchically:
    first rank the most relevant source files, then rank chunks only inside
    those files alongside live structured HR records.  Final seed diversity
    prevents one large file from monopolizing the context, and adjacent chunks
    from the same section can be added when a rule crosses a chunk boundary.
    """

    def __init__(self) -> None:
        self.settings = get_chat_assistant_settings()
        self.bm25 = BM25Retriever()
        self.vector = QdrantRetriever()
        self.file_vector = QdrantRetriever(collection_suffix="_files")

    def _merge_rrf(
        self,
        bm25: list[RetrievedDocument],
        vector: list[RetrievedDocument],
    ) -> list[RetrievedDocument]:
        merged: dict[str, tuple[KnowledgeDocument, float]] = {}
        rrf_k = int(self.settings.reciprocal_rank_constant)
        for rank, item in enumerate(bm25, start=1):
            previous = merged.get(item.document.document_id, (item.document, 0.0))[1]
            merged[item.document.document_id] = (
                item.document,
                previous + 1.0 / (rrf_k + rank),
            )
        for rank, item in enumerate(vector, start=1):
            previous = merged.get(item.document.document_id, (item.document, 0.0))[1]
            merged[item.document.document_id] = (
                item.document,
                previous + 1.0 / (rrf_k + rank),
            )
        output = [RetrievedDocument(doc, score) for doc, score in merged.values()]
        output.sort(key=lambda item: item.score, reverse=True)
        return output

    @staticmethod
    def _rerank_for_answerability(
        query: str,
        candidates: list[RetrievedDocument],
    ) -> list[RetrievedDocument]:
        """Favor concise evidence that can answer the requested fact type.

        RRF remains the primary rank.  This bounded lexical/answer-shape bonus
        only resolves close candidates and is dependency-free, so the same
        behavior is available even when Qdrant/reranker packages are absent.
        """

        adjusted = [
            RetrievedDocument(
                item.document,
                item.score + (0.012 * _evidence_fit_bonus(query, item.document)),
            )
            for item in candidates
        ]
        adjusted.sort(key=lambda item: item.score, reverse=True)
        return adjusted

    def _selected_file_representatives(
        self,
        query: str,
        selected_chunks: list[KnowledgeDocument],
    ) -> list[RetrievedDocument]:
        """Keep a small number of strong representatives from selected files.

        The second-stage global BM25 list can be monopolized by a long file that
        repeats the user's terms many times.  File-stage selection may still have
        correctly identified another concise policy, but without a representative
        from that file none of its evidence can reach the final diversification
        step.  Preserve only the strongest answer-shaped chunk from the best few
        selected files; this is intentionally small so weak files do not crowd out
        the main evidence.
        """

        limit = max(0, int(self.settings.evidence_file_representatives))
        if limit <= 0 or not selected_chunks:
            return []

        grouped: dict[str, list[KnowledgeDocument]] = defaultdict(list)
        for document in selected_chunks:
            key = _file_key(document)
            if key:
                grouped[key].append(document)

        representatives: list[tuple[float, KnowledgeDocument]] = []
        for file_documents in grouped.values():
            best = max(
                file_documents,
                key=lambda document: _evidence_fit_bonus(query, document),
            )
            fit = _evidence_fit_bonus(query, best)
            representatives.append((fit, best))

        representatives.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedDocument(document, 0.014 + (0.012 * fit))
            for fit, document in representatives[:limit]
        ]

    @staticmethod
    def _scope_documents(
        documents: list[KnowledgeDocument],
        *,
        company_id: int | None,
        role_scope: str | None,
    ) -> list[KnowledgeDocument]:
        """Fail closed to the current tenant/role when caller supplies scope."""

        allowed_roles = {"shared"}
        if role_scope:
            allowed_roles.add(role_scope)
        return [
            doc
            for doc in documents
            if (company_id is None or int(doc.company_id) == int(company_id))
            and (role_scope is None or doc.role_scope in allowed_roles)
        ]

    def _select_file_keys(
        self,
        query: str,
        file_chunks: list[KnowledgeDocument],
        *,
        access_partition: str,
        trace: TerminalChatTrace | None = None,
    ) -> tuple[set[str], dict[str, list[KnowledgeDocument]]]:
        """Rank whole files by aggregating their strongest chunk evidence.

        Scoring all chunks at this first stage means a rule near the end of a
        long file can still make that file relevant; the second stage then
        searches only the selected files in detail.
        """

        grouped: dict[str, list[KnowledgeDocument]] = defaultdict(list)
        for doc in file_chunks:
            key = _file_key(doc)
            if key:
                grouped[key].append(doc)
        if trace is not None:
            trace.counts(files_searched=len(grouped))
        if not grouped:
            return set(), grouped

        pre_k = min(
            len(file_chunks),
            max(
                int(self.settings.file_candidate_k) * 4,
                int(self.settings.file_top_k)
                * int(self.settings.max_chunks_per_file)
                * 4,
            ),
        )
        file_stage_started = time.monotonic()
        bm25 = self.bm25.search(query, file_chunks, pre_k)
        file_bm25_seconds = time.monotonic() - file_stage_started
        vector_started = time.monotonic()
        vector = self.file_vector.search(
            query,
            file_chunks,
            pre_k,
            access_partition=f"{access_partition}:file-stage",
        )
        file_vector_seconds = time.monotonic() - vector_started
        if trace is not None:
            trace.line(
                "FILE SEARCH TIMING",
                f"bm25_s={file_bm25_seconds:.3f}; vector_s={file_vector_seconds:.3f}; "
                f"total_s={time.monotonic() - file_stage_started:.3f}",
            )
            trace.line("FILE VECTOR STATUS", self.file_vector.diagnostic)
            trace.candidates(
                "FILE STAGE — BM25", bm25, score_label="bm25", show_excerpt=False
            )
            trace.candidates(
                "FILE STAGE — VECTOR NEAREST (cosine similarity)",
                vector,
                score_label="cosine",
                show_excerpt=False,
            )
        ranked_chunks = self._rerank_for_answerability(
            query, self._merge_rrf(bm25, vector)
        )
        if trace is not None:
            trace.candidates(
                "FILE STAGE — HYBRID RRF + ANSWER FIT",
                ranked_chunks,
                score_label="hybrid",
                show_excerpt=False,
            )
        if not ranked_chunks:
            selected_all = set(grouped)
            if trace is not None:
                trace.selected_files(selected_all, grouped)
            return selected_all, grouped

        per_file_evidence = max(1, int(self.settings.max_chunks_per_file))
        file_evidence: dict[str, list[float]] = defaultdict(list)
        for rank, item in enumerate(ranked_chunks, start=1):
            key = _file_key(item.document)
            if not key or len(file_evidence[key]) >= per_file_evidence:
                continue
            # RRF already includes rank information; keep that signal intact
            # instead of adding another rank term that can over-reward a file
            # simply for producing many nearby candidates.
            file_evidence[key].append(item.score)

        # The strongest matching chunk should decide most of a file's rank.
        # Extra supporting chunks help, but with diminishing weight so a very
        # long document cannot beat a concise exact-match file merely because
        # it produced more medium-strength hits.
        support_weights = (1.0, 0.005, 0.002)
        file_scores = {
            key: sum(
                score * (support_weights[index] if index < len(support_weights) else 0.001)
                for index, score in enumerate(scores)
            )
            for key, scores in file_evidence.items()
        }

        selected = {
            key
            for key, _score in sorted(
                file_scores.items(), key=lambda item: item[1], reverse=True
            )[:int(self.settings.file_top_k)]
        }
        selected = selected or set(grouped)
        if trace is not None:
            matched_chunk_counts: dict[str, int] = defaultdict(int)
            best_chunks: dict[str, str] = {}
            for item in ranked_chunks:
                key = _file_key(item.document)
                if key:
                    matched_chunk_counts[key] += 1
                    if key not in best_chunks:
                        metadata = item.document.metadata or {}
                        best_chunks[key] = (
                            f"{metadata.get('chunk_index') or '-'}/"
                            f"{metadata.get('total_chunks') or '-'}"
                        )
            trace.file_ranking(
                file_scores=file_scores,
                grouped=grouped,
                selected_keys=selected,
                matched_chunk_counts=matched_chunk_counts,
                best_chunks=best_chunks,
            )
            trace.selected_files(selected, grouped)
        return selected, grouped

    def _diversify_seeds(
        self,
        candidates: list[RetrievedDocument],
        *,
        limit: int | None = None,
    ) -> list[RetrievedDocument]:
        """Select the strongest balanced evidence without forcing file variety.

        A previous diversity-first pass could inject several weaker policies just
        because they came from different files.  Cross-file recall is now handled
        explicitly by ``_selected_file_representatives``; this step therefore
        respects score order and only caps how many chunks one file can consume.
        """

        target = max(1, int(limit or self.settings.final_top_k))
        per_file = max(1, int(self.settings.max_chunks_per_file))
        file_counts: dict[str, int] = defaultdict(int)
        selected: list[RetrievedDocument] = []

        for item in candidates:
            key = _file_key(item.document)
            if key and file_counts[key] >= per_file:
                continue
            selected.append(item)
            if key:
                file_counts[key] += 1
            if len(selected) >= target:
                break
        return selected

    @staticmethod
    def _preserve_direct_cross_file_evidence(
        query: str,
        seeds: list[RetrievedDocument],
        representatives: list[RetrievedDocument],
    ) -> tuple[list[RetrievedDocument], str]:
        """Reserve one slot for a second *direct* company-policy consequence.

        File discovery may correctly find multiple relevant policies while
        high-volume chunk scoring crowds the smaller policy out of the final
        prompt. This evidence floor requires question/body overlap AND a
        requested-fact cue; it never adds unselected or unauthorized files.
        Source variation alone is not enough to qualify. No QA examples or
        policy answers are embedded here.
        """
        if not seeds or len(seeds) < 2:
            return seeds, "not-applicable"
        if _question_evidence_profile(query) not in {
            "consequence", "eligibility", "yes_no", "procedure", "direct_fact"
        }:
            return seeds, "not-a-direct-rule-question"
        original_files = {
            _file_key(item.document) for item in seeds if _file_key(item.document)
        }
        if len(original_files) != 1:
            return seeds, "already-cross-file"
        primary_key = next(iter(original_files))
        best_fit = max(_evidence_fit_bonus(query, item.document) for item in seeds)
        qualifying: list[tuple[float, RetrievedDocument]] = []
        for item in representatives:
            document = item.document
            key = _file_key(document)
            if not key or key == primary_key or document.source_type not in {
                "policy", "company_document", "company_form"
            }:
                continue
            if document.company_id != seeds[0].document.company_id:
                continue
            if document.role_scope not in {"shared", seeds[0].document.role_scope}:
                continue
            diagnostics = _passage_diagnostic(query, document)
            fit = _evidence_fit_bonus(query, document)
            # Require a substantive direct rule, not just matching a title,
            # a generic HR noun, or a heading-only source.
            if (
                float(diagnostics["body_coverage"]) >= 0.40
                and float(diagnostics["answer_cue"]) >= 0.70
                and fit >= max(0.33, best_fit * 0.68)
            ):
                qualifying.append((fit, item))
        if not qualifying:
            return seeds, "no-supported-second-source"
        qualifying.sort(key=lambda pair: pair[0], reverse=True)
        second = qualifying[0][1]
        # Keep high-ranked primary evidence and substitute only its last seed.
        # The later neighbor-expansion phase may still fill the spare slot.
        return [*seeds[:-1], second], "direct-secondary-policy-preserved"

    def _expand_neighbors(
        self,
        query: str,
        seeds: list[RetrievedDocument],
        grouped: dict[str, list[KnowledgeDocument]],
        *,
        fallback_candidates: list[RetrievedDocument] | None = None,
        trace: TerminalChatTrace | None = None,
    ) -> list[RetrievedDocument]:
        """Add context only for chunks that are fragments of one semantic section.

        v8.8.221 reserved a neighbor slot for every file-backed seed.  The
        adaptive chunker can now mark whether a section was actually split, so
        intact sections no longer pay the latency/context cost of an automatic
        neighbor.  When a continuation is needed, choose the adjacent fragment
        with the strongest answer-fit rather than blindly preferring direction.
        """

        window = max(0, int(self.settings.neighbor_chunk_window))
        output: list[RetrievedDocument] = list(seeds)
        seen = {item.document.document_id for item in output}
        max_results = max(1, int(self.settings.final_top_k))
        neighbor_added = 0
        skipped_intact = 0

        if window and seeds and len(output) < max_results:
            for seed in seeds:
                key = _file_key(seed.document)
                if not key or key not in grouped:
                    continue
                metadata = seed.document.metadata or {}
                section_total = int(metadata.get("section_chunk_total") or 1)
                continuation_before = bool(int(metadata.get("continuation_before") or 0))
                continuation_after = bool(int(metadata.get("continuation_after") or 0))
                if section_total <= 1 or not (continuation_before or continuation_after):
                    skipped_intact += 1
                    continue

                seed_index = int(metadata.get("chunk_index") or 0)
                seed_section = str(metadata.get("section") or "")
                neighbor_options: list[tuple[float, int, KnowledgeDocument]] = []
                for distance in range(1, window + 1):
                    target_indexes: list[int] = []
                    if continuation_before:
                        target_indexes.append(seed_index - distance)
                    if continuation_after:
                        target_indexes.append(seed_index + distance)
                    for target_index in target_indexes:
                        for neighbor in grouped[key]:
                            if neighbor.document_id in seen:
                                continue
                            if int(neighbor.metadata.get("chunk_index") or 0) != target_index:
                                continue
                            neighbor_section = str(neighbor.metadata.get("section") or "")
                            if (
                                seed_section
                                and neighbor_section
                                and neighbor_section != seed_section
                            ):
                                continue
                            fit = _evidence_fit_bonus(query, neighbor)
                            # Prefer a nearby continuation when fit is tied.
                            neighbor_options.append((fit, -distance, neighbor))
                            break

                if not neighbor_options:
                    continue
                _fit, neg_distance, neighbor = max(
                    neighbor_options,
                    key=lambda item: (item[0], item[1]),
                )
                distance = abs(int(neg_distance))
                output.append(
                    RetrievedDocument(
                        neighbor,
                        max(0.0, seed.score - (distance * 0.0001)),
                    )
                )
                seen.add(neighbor.document_id)
                neighbor_added += 1
                if len(output) >= max_results:
                    break

        # Conditional responsibility questions can split a preamble from its
        # numbered tiers even when neither chunk is marked as a continuation:
        # the policy parser sometimes promotes the preamble to a section
        # heading. Prefer this *proved*, source-adjacent list over an unrelated
        # fallback chunk, without another embedding/vector/model request.
        conditional_list_neighbor_added = 0
        if window and len(output) < max_results and re.match(
            r"^if\b.{8,220}\bwho\b", _clean_text(query), re.I
        ):
            for seed in list(output):
                key = _file_key(seed.document)
                if not key or key not in grouped:
                    continue
                try:
                    next_index = int((seed.document.metadata or {}).get("chunk_index") or 0) + 1
                except (TypeError, ValueError):
                    continue
                for neighbor in grouped[key]:
                    if neighbor.document_id in seen:
                        continue
                    try:
                        neighbor_index = int((neighbor.metadata or {}).get("chunk_index") or 0)
                    except (TypeError, ValueError):
                        continue
                    if neighbor_index != next_index:
                        continue
                    candidate = RetrievedDocument(neighbor, max(0.0, seed.score - 0.0001))
                    if _contiguous_conditional_list_answer(
                        query, [seed, candidate], max_chars=2400
                    ) is None:
                        continue
                    output.append(candidate)
                    seen.add(neighbor.document_id)
                    conditional_list_neighbor_added += 1
                    break
                if len(output) >= max_results:
                    break

        # If no useful adjacent fragment exists, do not waste the reserved slot.
        # Fill it with the next strong independent candidate instead.
        for item in fallback_candidates or []:
            if item.document.document_id in seen:
                continue
            output.append(item)
            seen.add(item.document.document_id)
            if len(output) >= max_results:
                break

        if trace is not None:
            trace.line(
                "CONDITIONAL NEIGHBOR EXPANSION",
                (
                    f"added={neighbor_added}; intact_sections_skipped={skipped_intact}; "
                    f"conditional_list_added={conditional_list_neighbor_added}; "
                    f"window={window}; final_chunks={min(len(output), max_results)}"
                ),
            )
        return output[:max_results]

    def search(
        self,
        query: str,
        documents: list[KnowledgeDocument],
        *,
        company_id: int | None = None,
        role_scope: str | None = None,
        access_partition: str | None = None,
        trace: TerminalChatTrace | None = None,
    ) -> list[RetrievedDocument]:
        scoped = self._scope_documents(
            documents,
            company_id=company_id,
            role_scope=role_scope,
        )
        if trace is not None:
            trace.counts(
                authorized_documents=len(scoped),
                total_built_documents=len(documents),
            )
        if not scoped:
            if trace is not None:
                trace.line("RETRIEVAL", "No authorized knowledge documents available.")
            return []

        if access_partition is None:
            role_label = role_scope or "unspecified"
            access_partition = f"company:{company_id or 'unknown'}:role:{role_label}"

        file_chunks = [doc for doc in scoped if _file_key(doc)]
        structured = [doc for doc in scoped if not _file_key(doc)]
        if trace is not None:
            trace.counts(
                file_chunks=len(file_chunks),
                structured_records=len(structured),
            )
        selected_file_keys, grouped = self._select_file_keys(
            query,
            file_chunks,
            access_partition=access_partition,
            trace=trace,
        )
        selected_chunks = [
            doc for doc in file_chunks if _file_key(doc) in selected_file_keys
        ]
        search_space = structured + selected_chunks
        if trace is not None:
            trace.counts(
                selected_file_chunks=len(selected_chunks),
                chunk_stage_search_space=len(search_space),
            )
        if not search_space:
            if trace is not None:
                trace.line("RETRIEVAL", "Selected search space is empty.")
            return []

        chunk_stage_started = time.monotonic()
        bm25 = self.bm25.search(
            query, search_space, int(self.settings.bm25_top_k)
        )
        chunk_bm25_seconds = time.monotonic() - chunk_stage_started
        # Keep the semantic index on the stable authorized document snapshot
        # rather than re-indexing a query-specific subset on every question.
        chunk_vector_started = time.monotonic()
        vector_pool = self.vector.search(
            query,
            scoped,
            min(
                len(scoped),
                max(int(self.settings.vector_top_k) * 4, 24),
            ),
            access_partition=f"{access_partition}:all-stage",
        )
        allowed_ids = {doc.document_id for doc in search_space}
        vector = [
            item for item in vector_pool
            if item.document.document_id in allowed_ids
        ][:int(self.settings.vector_top_k)]
        chunk_vector_seconds = time.monotonic() - chunk_vector_started
        if trace is not None:
            trace.line(
                "CHUNK SEARCH TIMING",
                f"bm25_s={chunk_bm25_seconds:.3f}; vector_s={chunk_vector_seconds:.3f}; "
                f"total_s={time.monotonic() - chunk_stage_started:.3f}",
            )
            trace.line("CHUNK VECTOR STATUS", self.vector.diagnostic)
            trace.candidates(
                "CHUNK STAGE — BM25", bm25, score_label="bm25"
            )
            trace.candidates(
                "CHUNK STAGE — VECTOR NEAREST (cosine similarity)",
                vector,
                score_label="cosine",
            )
        candidates = self._rerank_for_answerability(
            query, self._merge_rrf(bm25, vector)
        )
        # EXPERIMENTAL, default off: deterministic extra BM25 queries only
        # against the already-authorized file/record search space. One vector
        # search is retained; no extra Ollama planning call is introduced.
        subqueries = (
            _adaptive_subqueries(query)
            if bool(getattr(self.settings, "adaptive_multi_query_enabled", False))
            else []
        )
        if subqueries:
            variant_hits = [
                self.bm25.search(part, search_space, min(8, int(self.settings.bm25_top_k)))
                for part in subqueries
            ]
            candidates = _merge_adaptive_bm25_candidates(
                query, candidates, variant_hits,
                allowed_document_ids={doc.document_id for doc in search_space},
            )
        if trace is not None:
            trace.line(
                "ADAPTIVE MULTI-QUERY",
                f"mode={'enabled' if bool(getattr(self.settings, 'adaptive_multi_query_enabled', False)) else 'disabled'}; "
                f"subqueries={len(subqueries)}; extra_vector_calls=0; "
                "source_scope=existing-authorized-search-space",
            )
            trace.candidates(
                "CHUNK STAGE — HYBRID RRF + ANSWER FIT",
                candidates,
                score_label="hybrid",
            )

        # Preserve a tiny cross-file evidence floor.  This prevents a long file
        # with many lexical hits from eliminating a second directly relevant
        # policy that the file stage already identified.
        representative_candidates = self._selected_file_representatives(
            query, selected_chunks
        )
        if representative_candidates:
            by_id = {item.document.document_id: item for item in candidates}
            for item in representative_candidates:
                existing = by_id.get(item.document.document_id)
                if existing is None or item.score > existing.score:
                    by_id[item.document.document_id] = item
            candidates = sorted(
                by_id.values(), key=lambda item: item.score, reverse=True
            )

        candidates = candidates[:max(
            int(self.settings.final_top_k) * int(self.settings.candidate_multiplier),
            int(self.settings.candidate_minimum),
        )]
        ambiguous = (
            len(candidates) >= int(self.settings.ambiguity_min_candidates)
            and (
                candidates[0].score
                - candidates[min(2, len(candidates) - 1)].score
            ) < float(self.settings.ambiguity_score_gap)
        )
        complex_query = len(_tokenize(query)) >= int(self.settings.complex_query_min_tokens) or bool(
            re.search(
                r"\b(compare|comparison|difference|explain|why|how|paano|bakit|pagkakaiba)\b",
                query,
                re.I,
            )
        )
        # Competing passages are often found for short questions too. Enable
        # reranking when best candidates are close in score, regardless of how
        # many words the user used. A cached local model is mandatory by default.
        competing = len(candidates) >= 2 and (
            ambiguous or candidates[0].score - candidates[1].score
            < float(getattr(self.settings, "reranker_competing_gap", 0.003))
        )
        if self.settings.reranker_enabled and candidates and competing:
            rerank_started = time.monotonic()
            try:
                model = _LocalCrossEncoder.get(
                    self.settings.reranker_model,
                    local_only=bool(getattr(self.settings, "reranker_local_only", True)),
                )
                if model is None:
                    if trace is not None:
                        trace.line("CROSS-ENCODER RERANK",
                                   "Skipped: model not in local cache. No implicit model download.")
                else:
                    candidates = _rerank_candidates(query, candidates, model)
                    if trace is not None:
                        trace.candidates("CROSS-ENCODER RERANK", candidates, score_label="hybrid+reranker")
            except Exception as exc:
                if trace is not None:
                    trace.line("CROSS-ENCODER RERANK",
                               f"Unavailable/failed; hybrid ranking retained ({type(exc).__name__}).")
            finally:
                if trace is not None:
                    trace.line("RERANK TIMING", f"cross_encoder_s={time.monotonic() - rerank_started:.3f}")
        elif trace is not None:
            trace.line("RERANK TIMING", "cross_encoder_s=0.000; skipped=yes")
            trace.line(
                "CROSS-ENCODER RERANK",
                "Not used for this request (disabled or query not ambiguous/complex).",
            )

        # Keep final evidence focused.  Earlier versions maximized file
        # diversity even when the extra files were much weaker, which could
        # send unrelated policy text to Qwen and dilute an otherwise exact
        # answer.  Preserve only candidates reasonably close to the best
        # evidence score; directly relevant second policies still survive via
        # the selected-file representative floor above.
        evidence_candidates = candidates
        if candidates:
            ratio = min(1.0, max(0.0, float(self.settings.evidence_min_score_ratio)))
            top_score = float(candidates[0].score)
            if top_score > 0:
                score_floor = top_score * ratio
            else:
                score_floor = top_score - max(0.05, abs(top_score) * (1.0 - ratio))
            evidence_candidates = [
                item for item in candidates if float(item.score) >= score_floor
            ] or candidates[:1]

        reserve = 0
        if grouped and int(self.settings.neighbor_chunk_window) > 0:
            reserve = min(
                max(0, int(self.settings.evidence_neighbor_reserve)),
                max(0, int(self.settings.final_top_k) - 1),
            )
        seed_limit = max(1, int(self.settings.final_top_k) - reserve)
        seeds = self._diversify_seeds(evidence_candidates, limit=seed_limit)
        seeds, cross_file_reason = self._preserve_direct_cross_file_evidence(
            query, seeds, representative_candidates,
        )
        if trace is not None:
            trace.line("DIRECT CROSS-FILE EVIDENCE", cross_file_reason)
            trace.candidates(
                "SELECTED EVIDENCE SEEDS", seeds, score_label="selection"
            )
        final_results = self._expand_neighbors(
            query,
            seeds,
            grouped,
            fallback_candidates=evidence_candidates,
            trace=trace,
        )
        if trace is not None:
            trace.candidates(
                "FINAL EVIDENCE TO QWEN", final_results, score_label="final"
            )
            trace.retrieval_matches(
                candidates=candidates,
                final_results=final_results,
            )
        return final_results


class OllamaClient:
    """Minimal local Ollama chat client with no Python SDK dependency."""

    _availability_cache: dict[str, float] = {}
    _availability_cache_seconds = 30.0

    def __init__(self) -> None:
        self.settings = get_chat_assistant_settings()

    @staticmethod
    def _is_timeout_error(exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, error.URLError):
            reason = getattr(exc, "reason", None)
            return isinstance(reason, (TimeoutError, socket.timeout))
        return False

    @staticmethod
    def _model_key(value: str) -> str:
        return (value or "").strip().casefold()

    @classmethod
    def _model_is_available(cls, configured: str, available: set[str]) -> bool:
        wanted = cls._model_key(configured)
        if not wanted:
            return True
        if wanted in available:
            return True
        # Ollama may display an explicit :latest tag for an untagged model.
        if ":" not in wanted and f"{wanted}:latest" in available:
            return True
        return False

    def check_available(self) -> None:
        """Verify Ollama is reachable and the configured primary model exists."""

        base_url = self.settings.ollama_base_url.rstrip("/")
        configured = str(self.settings.ollama_model)
        cache_key = f"{base_url}|{self._model_key(configured)}"
        cached_until = self._availability_cache.get(cache_key, 0.0)
        if cached_until > time.monotonic():
            return

        url = base_url + "/api/tags"
        req = request.Request(url, method="GET")
        timeout = float(self.settings.ollama_health_timeout_seconds)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read(2_000_000).decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
            models = data.get("models") if isinstance(data, dict) else None
            available: set[str] = set()
            for item in models or []:
                if not isinstance(item, dict):
                    continue
                for key in ("name", "model"):
                    value = self._model_key(str(item.get(key) or ""))
                    if value:
                        available.add(value)
            if not self._model_is_available(configured, available):
                raise RuntimeServiceModelUnavailableError(
                    "ollama",
                    model=configured,
                )
            self._availability_cache[cache_key] = (
                time.monotonic() + self._availability_cache_seconds
            )
        except RuntimeServiceModelUnavailableError:
            raise
        except error.HTTPError as exc:
            detail = str(getattr(exc, "reason", "") or "")
            raise RuntimeServiceResponseError(
                "ollama",
                status_code=int(exc.code),
                detail=detail,
                cause=exc,
            ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeServiceResponseError(
                "ollama",
                detail="Ollama returned an invalid model-list response.",
                cause=exc,
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            if self._is_timeout_error(exc):
                raise RuntimeServiceTimeoutError(
                    "ollama",
                    operation="health_check",
                    timeout_seconds=timeout,
                    cause=exc,
                ) from exc
            raise RuntimeServiceUnavailableError("ollama", cause=exc) from exc

    def generate(
        self,
        prompt: str,
        *,
        quality: bool = False,
        timeout_seconds: float | None = None,
    ) -> str | None:
        url = self.settings.ollama_base_url.rstrip("/") + "/api/generate"
        model = (
            self.settings.quality_ollama_model
            if quality
            else self.settings.ollama_model
        )
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "temperature": float(self.settings.temperature),
                "num_predict": (
                    int(self.settings.quality_max_tokens)
                    if quality
                    else int(self.settings.standard_max_tokens)
                ),
                "num_ctx": int(self.settings.context_window),
            },
        }).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else self.settings.ollama_timeout_seconds
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            value = _clean_model_answer(str(data.get("response", "")))
            return value or None
        except error.HTTPError as exc:
            detail = ""
            try:
                raw_detail = exc.read(4096).decode("utf-8", errors="replace")
                parsed_detail = json.loads(raw_detail)
                detail = (
                    str(parsed_detail.get("error") or raw_detail)
                    if isinstance(parsed_detail, dict)
                    else raw_detail
                )
            except Exception:
                detail = str(getattr(exc, "reason", "") or "")
            lowered = detail.casefold()
            if "model" in lowered and any(
                term in lowered
                for term in ("not found", "not available", "does not exist", "pull model")
            ):
                raise RuntimeServiceModelUnavailableError(
                    "ollama",
                    model=str(model),
                    cause=exc,
                ) from exc
            raise RuntimeServiceResponseError(
                "ollama",
                status_code=int(exc.code),
                detail=detail,
                cause=exc,
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            if self._is_timeout_error(exc):
                raise RuntimeServiceTimeoutError(
                    "ollama",
                    operation="generation",
                    timeout_seconds=timeout,
                    cause=exc,
                ) from exc
            raise RuntimeServiceUnavailableError("ollama", cause=exc) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeServiceResponseError(
                "ollama",
                detail="Ollama returned an invalid JSON response.",
                cause=exc,
            ) from exc



class SmartPortalAssistant:
    """Enhance deterministic portal answers without weakening access control."""

    _NEVER_ENHANCE_INTENTS = {"sensitive_security", "empty", "leave_carryover", "live_report", "policy_violation", "disciplinary_records", "employee_hierarchy", "employee_aggregate"}
    _RAG_INTENTS = {
        "policy", "policy_question", "policy_fallback", "benefits", "benefits_policy",
        "leave_type_details", "leave_request_status", "onboarding", "faq", "not_found",
        "employee_summary", "account_summary", "leave_summary",
        "announcement_summary", "attendance", "company_forms",
        "company_profile", "integrations", "audit_logs", "reports",
    }

    # These answers contain authoritative live portal values. They must never
    # be rewritten by an LLM because exact counts, balances, statuses, dates,
    # and employee records are already produced by secured HR services.
    _DIRECT_LIVE_INTENTS = {
        "employee_lookup", "leave_balance", "leave_status",
        "employee_profile", "personal_employee", "policy_summary", "dashboard",
    }


    _YES_NO_PATTERN = re.compile(
        r"^\s*(?:"
        r"can|could|may|might|should|would|will|do|does|did|"
        r"is|are|was|were|has|have|had|am|"
        r"pwede\s+ba|puwede\s+ba|maaari\s+ba"
        r")\b",
        re.I,
    )
    _NON_BINARY_REQUEST_PATTERN = re.compile(
        r"^\s*(?:"
        r"(?:who|what|when|where|why|how|which|show|list|tell|give|display|find|summarize|explain)\b"
        r"|(?:can|could|would|will)\s+you\s+"
        r"(?:show|list|tell|give|display|find|summarize|explain|help|open|check)"
        r"|(?:can|could|may)\s+i\s+"
        r"(?:see|view|show|list|check|know)"
        r")",
        re.I,
    )
    _FOLLOW_UP_PATTERNS = (
        r"\bhow about\b",
        r"\bwhat about\b",
        r"\babout it\b",
        r"\babout that\b",
        r"\bapprove(?:s)? it\b",
        r"\bwho (?:needs to )?approve(?:s)?\b",
        r"\bthat request\b",
        r"\bthis request\b",
        r"\bthe same request\b",
        r"\bwhat happens next\b",
        r"\band (?:vl|sl|el)\b",
        r"\bilan na lang\b",
        r"\bilan nalang\b",
        r"\bpaano naman\b",
        r"\byun\b",
        r"\bito\b",
    )
    _SCOPE_STOPWORDS = {
        "a", "an", "and", "ang", "ano", "are", "ba", "can", "could", "do",
        "does", "for", "from", "how", "i", "in", "is", "it", "ko", "may",
        "my", "ng", "of", "on", "or", "si", "sino", "the", "to", "what",
        "when", "where", "which", "who", "why", "with", "would", "you", "your",
    }
    _IN_SCOPE_TERMS = {
        "hr", "employee", "employees", "company", "work", "office", "manager",
        "leader", "leave", "vacation", "sick", "emergency", "lwop", "attendance",
        "dtr", "overtime", "policy", "policies", "benefit", "benefits", "onboarding",
        "announcement", "announcements", "form", "forms", "document", "documents",
        "report", "reports", "department", "job", "salary", "payroll", "schedule",
        "shift", "holiday", "holidays", "dress", "uniform", "attire", "parking",
        "park", "reimbursement", "travel", "fare", "meal", "break", "remote",
        "wfh", "wfo", "credit", "credits", "request", "requests", "approval",
        "approve", "approver", "contact", "contacts", "faq", "training",
    }
    _STRONG_IN_SCOPE_TERMS = {
        "hr", "employee", "employees", "company", "manager", "leader", "leave",
        "vacation", "sick", "emergency", "lwop", "attendance", "dtr", "overtime",
        "policy", "policies", "benefit", "benefits", "onboarding", "payroll",
        "department", "wfh", "wfo", "approval", "approver", "training",
    }
    _OBVIOUS_EXTERNAL_TERMS = {
        "batman", "superman", "marvel", "dc comics", "celebrity", "celebrities",
        "movie", "movies", "actor", "actress", "singer", "music", "song", "songs",
        "basketball", "football", "nba", "nfl", "sports", "score", "scores",
        "election", "politics", "politician", "president", "senator", "mayor",
        "python programming", "javascript", "programming", "source code", "coding",
        "recipe", "recipes", "weather", "horoscope", "astrology",
    }

    # Retrieval relevance is a second fail-closed layer after the existing
    # company/HR scope check. Generic domain words must not make an unrelated
    # nearest chunk look answerable (for example, ``Laptop policy`` matching a
    # Leave Policy only because both contain the word ``policy``).
    _RELEVANCE_GUARD_INTENTS = {
        "policy", "policy_question", "policy_fallback", "benefits", "benefits_policy", "not_found",
    }
    _RELEVANCE_GENERIC_TERMS = {
        "company", "detail", "details", "employee", "employees", "hr",
        "information", "policy", "policies", "rule", "rules", "work",
    }

    @classmethod
    def _is_yes_no_question(cls, question: str) -> bool:
        clean = _clean_text(question)
        if cls._NON_BINARY_REQUEST_PATTERN.search(clean):
            return False
        return bool(
            cls._YES_NO_PATTERN.search(clean)
            or re.search(r"\byes\s+or\s+no\b", clean, re.I)
        )

    @classmethod
    def _is_follow_up_question(
        cls,
        question: str,
        history: list[dict] | None,
    ) -> bool:
        if not history:
            return False
        clean = _clean_text(question).casefold()
        if any(re.search(pattern, clean, re.I) for pattern in cls._FOLLOW_UP_PATTERNS):
            return True
        # Very short reference-only questions are also follow-ups, but clear
        # standalone module/topic names are deliberately excluded.
        tokens = _tokenize(clean)
        standalone_topics = {
            "policy", "policies", "documents", "attendance", "overtime",
            "onboarding", "benefits", "announcements", "faq", "reports",
        }
        return (
            0 < len(tokens) <= 4
            and not standalone_topics.intersection(tokens)
            and bool(re.search(r"\b(it|that|those|this|these|them|same)\b", clean))
        )

    @staticmethod
    def _last_user_question(history: list[dict] | None) -> str | None:
        for message in reversed(history or []):
            if message.get("role") != "user":
                continue
            value = _clean_text(str(message.get("content", "")))
            if value:
                return value
        return None

    @classmethod
    def _contextual_search_query(
        cls,
        question: str,
        history: list[dict] | None,
    ) -> str:
        if not cls._is_follow_up_question(question, history):
            return question
        previous = cls._last_user_question(history)
        return f"{previous} {question}".strip() if previous else question

    @classmethod
    def _scope_terms(cls, value: str) -> set[str]:
        terms: set[str] = set()
        for token in _tokenize(value):
            if token in cls._SCOPE_STOPWORDS or len(token) <= 2:
                continue
            stem = token
            for suffix in ("ingly", "edly", "ing", "ed", "es", "s"):
                if stem.endswith(suffix) and len(stem) - len(suffix) >= 4:
                    stem = stem[:-len(suffix)]
                    break
            terms.add(stem)
        return terms

    @classmethod
    def _retrieval_has_lexical_support(
        cls,
        query: str,
        retrieved: list[RetrievedDocument],
    ) -> bool:
        query_terms = cls._scope_terms(query)
        if not query_terms:
            return False
        for item in retrieved:
            document_terms = cls._scope_terms(
                f"{item.document.title} {item.document.text}"
            )
            if query_terms.intersection(document_terms):
                return True
        return False

    @classmethod
    def _relevance_anchor_terms(cls, query: str) -> set[str]:
        """Return specific topic terms, excluding generic company/policy words."""

        return cls._scope_terms(query).difference(cls._RELEVANCE_GENERIC_TERMS)

    @classmethod
    def _retrieval_relevance_snapshot(
        cls,
        *,
        query: str,
        retrieved: list[RetrievedDocument],
        require_answer_cue: bool = False,
        min_answer_cue: float = 0.0,
    ) -> dict[str, object]:
        """Measure whether retrieved evidence actually covers the user's topic.

        This deliberately favors lexical topic anchors over raw nearest-neighbor
        rank. A vector result can be the mathematically nearest chunk while still
        being unrelated to the requested subject. The guard is fail-closed only
        for fallback/policy-style requests; exact live HR routes remain unchanged.
        """

        anchors = cls._relevance_anchor_terms(query)
        evidence_profile = _question_evidence_profile(query)
        if not retrieved:
            return {
                "accepted": False,
                "anchors": anchors,
                "matched": set(),
                "coverage": 0.0,
                "answer_fit": 0.0,
                "answer_cue": 0.0,
                "evidence_profile": evidence_profile,
                "source": "-",
                "reason": "No authorized evidence was retrieved.",
            }

        # If the wording contains only generic company/policy words, do not let
        # this guard invent a topic. The existing deterministic router remains
        # authoritative for those generic requests.
        if not anchors:
            return {
                "accepted": True,
                "anchors": anchors,
                "matched": set(),
                "coverage": 1.0,
                "answer_fit": 0.0,
                "answer_cue": 0.0,
                "evidence_profile": evidence_profile,
                "source": "-",
                "reason": "No specific topic anchor; retain existing router behavior.",
            }

        best: dict[str, object] | None = None
        candidates: list[dict[str, object]] = []
        for item in retrieved[: max(1, min(8, len(retrieved)))]:
            document = item.document
            document_terms = cls._scope_terms(
                f"{document.title} {document.text}"
            )
            matched = anchors.intersection(document_terms)
            coverage = len(matched) / max(1, len(anchors))
            fit = _evidence_fit_bonus(query, document)
            answer_cue = _answerability_cue_bonus(
                query, f"{document.title} {document.text}"
            )
            metadata = document.metadata or {}
            source = str(
                metadata.get("filename")
                or metadata.get("title")
                or document.title
                or document.document_id
            ).strip()
            candidate = {
                "anchors": anchors,
                "matched": matched,
                "coverage": coverage,
                "answer_fit": fit,
                "answer_cue": answer_cue,
                "evidence_profile": evidence_profile,
                "source": source,
            }
            candidates.append(candidate)
            if best is None or (coverage, fit) > (
                float(best["coverage"]),
                float(best["answer_fit"]),
            ):
                best = candidate

        assert best is not None
        # When the highest-overlap excerpt is only a heading, check nearby
        # authorized retrieved passages for an actual answer. Do NOT lower the
        # minimum cue or authorize a low-topic-match excerpt; switch only to a
        # passage with both strong lexical topic support and explicit fact cue.
        if require_answer_cue and float(best.get("answer_cue") or 0) < float(min_answer_cue):
            answer_bearing = [candidate for candidate in candidates
                if float(candidate["answer_cue"]) >= float(min_answer_cue)
                and (len(candidate["matched"]) == len(anchors) if len(anchors) <= 2
                     else len(candidate["matched"]) >= 2
                     and float(candidate["coverage"]) >= 0.50)
                and float(candidate["answer_fit"]) >= 0.30]
            if answer_bearing:
                best = max(answer_bearing, key=lambda c: (
                    float(c["coverage"]), float(c["answer_fit"]), float(c["answer_cue"])
                ))
        matched_count = len(best["matched"])
        anchor_count = len(anchors)
        coverage = float(best["coverage"])
        fit = float(best["answer_fit"])
        answer_cue = float(best.get("answer_cue") or 0.0)

        # Short subject phrases are strict: both terms in ``emergency loan``
        # must be supported, so an ``Emergency Leave`` chunk cannot pass merely
        # on the shared word ``emergency``. Longer natural questions allow half
        # of the specific anchors as long as at least two are supported.
        if anchor_count == 1:
            accepted = matched_count == 1
        elif anchor_count == 2:
            accepted = matched_count == 2
        else:
            accepted = matched_count >= 2 and coverage >= 0.50

        # A strong answer-shape fit can confirm a borderline long question, but
        # never rescues evidence with fewer than two supported topic anchors.
        if (
            not accepted
            and anchor_count >= 4
            and matched_count >= 2
            and coverage >= 0.40
            and fit >= 0.45
        ):
            accepted = True

        cue_required_profiles = {
            "amount",
            "duration_or_count",
            "date_or_time",
            "consequence",
            "eligibility",
            "procedure", "direct_fact",
        }
        cue_rejected = False
        if (
            accepted
            and require_answer_cue
            and evidence_profile in cue_required_profiles
            and answer_cue < max(0.0, float(min_answer_cue))
        ):
            accepted = False
            cue_rejected = True

        best["accepted"] = accepted
        if accepted:
            best["reason"] = "Retrieved evidence covers the specific topic anchors and requested fact shape."
        elif cue_rejected:
            best["reason"] = "Topic matched, but no sufficiently direct answer-bearing fact was found for this question type."
        else:
            best["reason"] = "Nearest evidence does not sufficiently cover the requested topic."
        return best

    @classmethod
    def _recover_authorized_policy_evidence(
        cls,
        *, query: str,
        retrieved: list[RetrievedDocument],
        documents: list[KnowledgeDocument],
        company_id: int,
        role_scope: str,
    ) -> list[RetrievedDocument]:
        """Bounded adjacent-subsection recovery when evidence gate rejects.

        Revisit *only* source files that retrieval already selected, from the
        caller's original authorized company/role snapshot. Never traverse a
        different file/tenant or promote an unrelated query by general HR words.
        """
        valid_roles = {"shared", role_scope}
        source_files = {
            _file_key(x.document) for x in retrieved[:5]
            if x.document.source_type in {"policy", "company_form_content"}
            and x.document.company_id == company_id
            and x.document.role_scope in valid_roles
            and len(set(_meaningful_evidence_tokens(query)) &
                    set(_meaningful_evidence_tokens(x.document.title))) >= 1
        }
        source_files.discard(None)
        if not source_files:
            return retrieved
        original_ids = {x.document.document_id for x in retrieved}
        eligible = [x for x in documents
                    if x.company_id == company_id
                    and x.role_scope in valid_roles
                    and x.source_type in {"policy", "company_form_content"}
                    and _file_key(x) in source_files
                    and x.document_id not in original_ids]
        eligible.sort(key=lambda x: _evidence_fit_bonus(query, x), reverse=True)
        recoveries = [RetrievedDocument(x, 0.0) for x in eligible[:8]
                      if _passage_diagnostic(query, x)["body_overlap"] >= 1]
        # Recovery is rescored as answer-bearing paragraphs first; preserve
        # original candidates for provenance and alternate context.
        return recoveries + retrieved

    @staticmethod
    def _retrieved_policy_sources(retrieved: list[RetrievedDocument]) -> list[PolicySource]:
        """Expose only policy citations with a real authorized policy ID."""
        result: list[PolicySource] = []
        seen: set[tuple[int, str]] = set()
        for item in retrieved:
            doc = item.document
            if doc.source_type != "policy":
                continue
            metadata = doc.metadata or {}
            policy_id = metadata.get("policy_id")
            if not isinstance(policy_id, int) or policy_id <= 0:
                continue
            section = str(metadata.get("section") or "")
            key = (policy_id, section)
            if key in seen:
                continue
            seen.add(key)
            result.append(PolicySource(
                policy_id=policy_id,
                title=str(metadata.get("title") or doc.title),
                category="",
                version=str(metadata.get("version") or ""),
                effective_date=None,
                uploaded_at=None,
                section_heading=section,
                filename=str(metadata.get("filename") or "") or None,
                page_number=metadata.get("page_number") if isinstance(metadata.get("page_number"), int) else None,
            ))
            if len(result) == 3:
                break
        return result

    @classmethod
    def _answer_supported_policy_source(
        cls,
        *,
        answer: str,
        query: str,
        retrieved: list[RetrievedDocument],
        fallback_sources: list,
    ) -> list:
        """Prefer a cited policy passage that supports the *answer's facts*.

        The top vector chunk or an earlier router citation can be topical but
        unrelated to the generated fact. This local post-check is scoped solely
        to already-authorized retrieved policy chunks. It cannot discover new
        records, guess policy IDs, or add cross-tenant citations.
        """
        tokens = set(_meaningful_evidence_tokens(answer))
        generic = {"company", "employees", "employee", "policy", "according",
                   "information", "answer", "staff", "work", "the", "and"}
        salient = {word for word in tokens if len(word) >= 4 and word not in generic}
        if len(salient) < 3:
            return fallback_sources
        query_terms = {word for word in _meaningful_evidence_tokens(query)
                       if len(word) >= 4 and word not in generic}
        answer_words = [word for word in _meaningful_evidence_tokens(answer)
                        if len(word) >= 4 and word not in generic]
        phrases = {" ".join(answer_words[i:i + 3])
                   for i in range(max(0, len(answer_words) - 2))}
        best = None
        best_score = 0.0
        for item in retrieved:
            doc = item.document
            if doc.source_type != "policy":
                continue
            body = _document_body_text(doc)
            words = set(_meaningful_evidence_tokens(body))
            matches = len(salient & words)
            if matches < 3 or (query_terms and not query_terms.intersection(words)):
                continue
            normalized = _normalized_phrase_text(body)
            phrase_matches = sum(1 for phrase in phrases if phrase in normalized)
            score = (matches / len(salient)) + min(0.5, phrase_matches * .09)
            if score > best_score:
                best = item
                best_score = score
        if best is None or best_score < .30:
            return fallback_sources
        sources = cls._retrieved_policy_sources([best])
        return sources or fallback_sources

    @staticmethod
    def _top_display_sources(
        sources: list,
        retrieved: list[RetrievedDocument],
    ) -> list:
        """Return one best policy source for the clean Streamlit source display."""

        if not sources:
            return []

        for item in retrieved:
            metadata = item.document.metadata or {}
            filename = str(metadata.get("filename") or "").strip().casefold()
            policy_id = metadata.get("policy_id")
            section = str(metadata.get("section") or "").strip().casefold()
            for source in sources:
                source_filename = str(getattr(source, "filename", "") or "").strip().casefold()
                source_section = str(
                    getattr(source, "section_heading", "") or ""
                ).strip().casefold()
                source_policy_id = getattr(source, "policy_id", None)
                file_matches = bool(filename and source_filename == filename)
                policy_matches = bool(
                    policy_id is not None and source_policy_id == policy_id
                )
                if not (file_matches or policy_matches):
                    continue
                if section and source_section and section != source_section:
                    # Prefer the exact best section when available, but the file
                    # itself remains the primary source if section labels differ.
                    continue
                return [source]

        # Deterministic policy search is already score ordered. Limiting to one
        # here also protects direct/fallback paths when a retriever match cannot
        # be mapped back to the policy source object.
        return [sources[0]]

    @staticmethod
    def _contains_scope_term(value: str, term: str) -> bool:
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
                value,
                re.I,
            )
        )

    @classmethod
    def _is_out_of_scope_question(
        cls,
        *,
        question: str,
        history: list[dict] | None,
        deterministic_intent: str,
        retrieved: list[RetrievedDocument],
    ) -> bool:
        # Recognized HR/application routes are already inside the product scope.
        if deterministic_intent not in {"policy_fallback", "not_found"}:
            return False
        if cls._is_follow_up_question(question, history):
            return False
        if cls._is_yes_no_question(question):
            # A yes/no workplace rule may be phrased without an explicit HR
            # keyword; allow retrieval/prompt grounding to decide it safely.
            return False

        normalized = _clean_text(question).casefold()
        has_strong_scope = any(
            cls._contains_scope_term(normalized, term)
            for term in cls._STRONG_IN_SCOPE_TERMS
        )
        has_external = any(
            cls._contains_scope_term(normalized, term)
            for term in cls._OBVIOUS_EXTERNAL_TERMS
        )
        if has_external and not has_strong_scope:
            return True
        if any(
            cls._contains_scope_term(normalized, term)
            for term in cls._IN_SCOPE_TERMS
        ):
            return False
        if cls._retrieval_has_lexical_support(question, retrieved):
            return False

        # Unknown wording with no authorized HR/company support is kept away
        # from the general-purpose knowledge of the local model.
        return True

    @staticmethod
    def _normalize_standard_answer(answer: str) -> str:
        """Remove an accidental binary prefix from non-binary answers.

        Local models occasionally start an ordinary Who/What/Show/List answer
        with ``YES.`` or ``NO.`` even when the question is not binary. Keep the
        useful grounded remainder but never present that misleading prefix.
        """

        clean = _clean_model_answer(answer)
        match = re.match(
            r"^\s*(?:\*\*)?(?:yes|no)\s*[.!,:;-]\s*(?:\*\*)?\s*(.+)$",
            clean,
            re.I | re.S,
        )
        if match:
            clean = match.group(1).strip()
        return _organize_answer(clean)

    @staticmethod
    def _normalize_yes_no_answer(answer: str) -> str:
        clean = _clean_model_answer(answer)
        if not clean:
            return UNDETERMINED_ANSWER
        if clean.casefold().startswith(UNDETERMINED_ANSWER.casefold()):
            return UNDETERMINED_ANSWER
        if clean.casefold().startswith(NOT_FOUND_ANSWER.casefold()):
            return UNDETERMINED_ANSWER
        match = re.match(
            r"^\s*(?:\*\*)?(yes|no)\s*[.!,:;-]?\s*(?:\*\*)?\s*(.*)$",
            clean,
            re.I | re.S,
        )
        if not match:
            # Do not infer a binary conclusion from prose. If the model did not
            # provide a grounded YES/NO, fail closed instead of guessing.
            return UNDETERMINED_ANSWER
        prefix = f"**{match.group(1).upper()}.**"
        remainder = match.group(2).strip()
        # A binary prefix and a contradictory explicit permission conclusion
        # must not be shown together. This is generic logical consistency,
        # not a company policy or question-specific expected answer.
        if match.group(1).casefold() == "no" and re.search(
            r"\b(?:does\s+not|will\s+not|would\s+not|doesn.t|won.t)\s+"
            r"(?:disqualif|prevent|prohibit|bar|exclude)\w*\b|"
            r"\b(?:is|remains|still)\s+(?:eligible|qualified|allowed|permitted)\b|"
            r"\b(?:can|may|could)\s+(?:still\s+)?(?:qualify|receive|participate|apply|claim|attend|use|take|be\s+eligible|be\s+allowed)\b|"
            r"\b(?:explicitly\s+)?exclud\w*\s+.{0,65}\s+from\s+(?:the\s+)?(?:criteria\s+for\s+)?disqualif\w*",
            remainder, re.I,
        ):
            return UNDETERMINED_ANSWER
        return f"{prefix} {remainder}".strip()

    def _repair_local_binary_answer(
        self,
        *,
        question: str,
        retrieved: list[RetrievedDocument],
        trace: TerminalChatTrace,
    ) -> str:
        """One evidence-only local retry after an explicit binary contradiction.

        Never flip YES/NO by assumption. The source blocks—not the previous
        model answer or any evaluation key—must establish the conclusion.
        A failed, contradictory, or timed-out retry remains undetermined.
        """
        if not bool(getattr(self.settings, "binary_repair_enabled", True)):
            return UNDETERMINED_ANSWER
        if not retrieved:
            return UNDETERMINED_ANSWER
        evidence = self._build_evidence_context(
            query=question, retrieved=retrieved[:3],
        )
        evidence = self._truncate_prompt_text(evidence, 2300)
        repair_prompt = (
            "You are answering a company policy YES/NO question. Only the "
            "authenticated company's evidence below is allowed. Ignore "
            "general knowledge. Check exceptions and exclusions carefully. "
            "The prior answer was internally contradictory and must NOT be "
            "used as evidence. Respond with exactly YES. or NO. followed "
            "by one evidence-based explanation. If unclear, respond exactly: "
            f"{UNDETERMINED_ANSWER}\n\n"
            f"Question: {question}\n\nAuthorized evidence:\n{evidence}\n\nAnswer:"
        )
        timeout = max(5.0, float(getattr(self.settings, "binary_repair_timeout_seconds", 45.0)))
        trace.line("LOCAL BINARY REPAIR", f"attempt=1; prompt_chars={len(repair_prompt)}; timeout={timeout}s")
        started = time.monotonic()
        try:
            raw_repair = self.ollama.generate(
                repair_prompt, quality=False, timeout_seconds=timeout,
            )
        except (
            RuntimeServiceModelUnavailableError,
            RuntimeServiceResponseError,
            RuntimeServiceTimeoutError,
            RuntimeServiceUnavailableError,
        ) as exc:
            trace.line(
                "LOCAL BINARY REPAIR",
                f"failed={type(exc).__name__}; elapsed_s={time.monotonic() - started:.2f}; abstained=yes",
            )
            return UNDETERMINED_ANSWER
        normalized = self._normalize_yes_no_answer(raw_repair)
        trace.line(
            "LOCAL BINARY REPAIR",
            f"elapsed_s={time.monotonic() - started:.2f}; "
            f"result={'supported-format' if normalized != UNDETERMINED_ANSWER else 'abstained'}",
        )
        # This repairs logical presentation, not proof of full entailment;
        # the same source-grounding requirements apply as to the first answer.
        return normalized

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_chat_assistant_settings()
        self.retriever = HybridRetriever()
        self.ollama = OllamaClient()
        self.groq = GroqClient()


    def preflight_connection_issue(
        self,
        *,
        role_scope: str,
    ):
        """Check only the provider(s) selected in .env; keep verified HR answers."""
        if not self.settings.enabled:
            return None
        mode = getattr(self.settings, "llm_mode", "local")
        try:
            if mode == "local":
                self.ollama.check_available()
            elif mode == "groq":
                self.groq.check_available()
            elif mode == "hybrid":
                try:
                    self.groq.check_available()
                except (
                    RuntimeServiceResponseError,
                    RuntimeServiceTimeoutError,
                    RuntimeServiceUnavailableError,
                ):
                    # A valid local model makes the hybrid route usable.
                    self.ollama.check_available()
            else:
                raise ValueError("Unsupported AI LLM mode")
            return None
        except (
            RuntimeServiceModelUnavailableError,
            RuntimeServiceResponseError,
            RuntimeServiceTimeoutError,
            RuntimeServiceUnavailableError,
        ) as exc:
            issue = classify_runtime_connection_issue(exc, service_hint=mode)
            if issue is None:
                raise
            log_runtime_connection_issue(
                exc, issue, context=f"chat_preflight:{role_scope};mode={mode}"
            )
            return issue

    def _history_text(self, history: list[dict] | None) -> str:
        lines = []
        for message in (history or [])[-max(1, int(self.settings.history_messages)):]:
            role = str(message.get("role", "user")).title()
            content = _clean_text(str(message.get("content", "")))
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _truncate_prompt_text(
        value: str,
        limit: int,
        *,
        suffix: str = "\n[Additional authorized context omitted for safe model input size.]",
    ) -> str:
        """Bound one prompt section without changing authoritative source data."""

        clean = str(value or "").strip()
        if limit <= 0 or len(clean) <= limit:
            return clean
        usable = max(0, limit - len(suffix))
        return clean[:usable].rstrip() + suffix

    def _build_evidence_context(
        self,
        *,
        query: str,
        retrieved: list[RetrievedDocument],
        excerpt_chars: int | None = None,
        max_documents: int | None = None,
    ) -> str:
        """Build compact, source-labeled evidence blocks for the local model.

        The retriever may return several 260-300 word chunks, but Qwen's 4096
        context window cannot safely receive all of them verbatim alongside the
        grounding rules and router answer.  Keep the most question-relevant
        sentences/rows from every selected chunk so multiple applicable policy
        rules survive the prompt budget instead of the first chunk consuming it.
        """

        if not retrieved:
            return "No additional approved portal context was retrieved."

        blocks: list[str] = []
        excerpt_limit = max(320, int(excerpt_chars if excerpt_chars is not None
                                     else self.settings.evidence_excerpt_chars))
        items = retrieved[:max_documents] if max_documents is not None else retrieved
        for index, item in enumerate(items, start=1):
            metadata = item.document.metadata or {}
            source_name = str(
                metadata.get("filename")
                or metadata.get("title")
                or item.document.title
                or "Authorized company source"
            ).strip()
            section = str(metadata.get("section") or "").strip()
            page_number = metadata.get("page_number")
            labels = [f"Source: {source_name}"]
            if section:
                labels.append(f"Section: {section}")
            if page_number:
                labels.append(f"Page: {page_number}")
            excerpt = _focused_evidence_excerpt(
                query,
                item.document.text,
                excerpt_limit,
            )
            blocks.append(
                f"[Evidence {index} | {' | '.join(labels)}]\n{excerpt}"
            )
        return "\n\n".join(blocks)

    def _budget_prompt_sections(
        self,
        *,
        history_text: str,
        router_answer: str,
        context: str,
        rag_priority: bool = False,
        compact: bool = False,
    ) -> tuple[str, str, str]:
        """Keep prompt sections safe while preserving multi-source RAG evidence."""

        context_window = max(2048, int(self.settings.context_window))
        if rag_priority:
            variable_budget = max(4600, min(9800, int(context_window * 1.9)))
        else:
            # Preserve the established non-RAG prompt budget so structured/live
            # answers do not lose the router-first behavior while policy/document
            # questions can use the larger evidence budget above.
            variable_budget = max(4200, min(8200, int(context_window * 1.6)))
        if compact:
            variable_budget = max(3200, int(variable_budget * 0.58))

        if rag_priority:
            # Policy/document questions need more evidence than router prose.
            # The router remains authoritative when exact, but it may be a
            # focused extract; allocate enough space to preserve distinct
            # clauses, exceptions, and cross-policy rules.
            context_limit = int(variable_budget * 0.62)
            router_limit = int(variable_budget * 0.24)
        else:
            router_limit = int(variable_budget * 0.54)
            context_limit = int(variable_budget * 0.34)
        history_limit = max(420, variable_budget - router_limit - context_limit)

        return (
            self._truncate_prompt_text(history_text, history_limit),
            self._truncate_prompt_text(
                router_answer,
                router_limit,
                suffix=(
                    "\n[Additional verified router rows omitted from AI rewriting; "
                    "the verified portal result remains authoritative.]"
                ),
            ),
            self._truncate_prompt_text(context, context_limit),
        )

    def enhance(
        self,
        *,
        current_user: AuthenticatedUser,
        role_scope: str,
        question: str,
        history: list[dict] | None,
        deterministic_response: HRAssistantResponse,
        log_session_id: str | None = None,
        log_question_number: int = 0,
    ) -> HRAssistantResponse:
        trace = TerminalChatTrace.create(
            self.settings,
            session_id=log_session_id,
            company_id=getattr(current_user, "company_id", None),
            user_id=getattr(current_user, "user_id", None),
            role_scope=role_scope,
            question_number=log_question_number,
        )
        trace.start(
            role_scope=role_scope,
            intent=deterministic_response.intent,
            question=question,
        )
        trace.answer("DETERMINISTIC / ROUTER ANSWER", deterministic_response.answer)

        semantics = analyze_query_semantics(question)
        trace.line(
            "SOURCE ROUTING ANALYSIS",
            (
                f"Router intent      : {deterministic_response.intent}\n"
                f"Request shape     : {semantics.request_shape}\n"
                f"Shape confidence  : {semantics.confidence:.2f}\n"
                f"Collection request: {'YES' if semantics.collection_request else 'NO'}\n"
                f"Explanation/fact  : {'YES' if semantics.explanation_request else 'NO'}"
            ),
        )
        compatible, compatibility_reason = validate_deterministic_answer_shape(
            question,
            deterministic_response.intent,
            deterministic_response.answer,
            has_report=bool(deterministic_response.report),
        )
        # Scope this safeguard to answer families which claim to identify a
        # named entity or case/rule. Numeric counts, balances, and tabular
        # aggregates legitimately omit the question's words and must not be
        # rejected by a lexical topic test.
        record_intents = {
            "employee_lookup", "employee_profile", "policy_violation",
            "disciplinary_records",
        }
        if compatible and deterministic_response.intent in record_intents and not deterministic_response.report:
            if not _record_intent_matches_request(question, deterministic_response.intent):
                compatible, compatibility_reason = False, "record-entity-type-not-requested"
            elif not _record_answer_relevance(question, deterministic_response.answer):
                compatible, compatibility_reason = False, "live-record-topic-not-supported"
        if not compatible:
            trace.line(
                "UNIVERSAL ANSWER COMPATIBILITY GUARD",
                (
                    f"Original intent: {deterministic_response.intent}\n"
                    f"Request shape : {semantics.request_shape}\n"
                    f"Decision      : REJECT INCOMPATIBLE DETERMINISTIC OUTPUT\n"
                    f"Reason        : {compatibility_reason}\n"
                    "Recovery      : authorized evidence-gated retrieval only"
                ),
            )
            # Do not pass an unrelated record list, metadata, or attached
            # actions into RAG. The tenant/role filtered retrieval pipeline
            # either finds supported evidence or abstains.
            deterministic_response = HRAssistantResponse(
                answer=NOT_FOUND_ANSWER, intent="not_found", actions=[], sources=[],
            )

        def complete(
            response: HRAssistantResponse,
            *,
            status: str = "complete",
        ) -> HRAssistantResponse:
            if response.runtime_warning_code:
                trace.runtime_issue(
                    code=response.runtime_warning_code,
                    title=response.runtime_warning_title or "Runtime warning",
                    message=response.runtime_warning or "",
                )
            selected_answer = (
                "qwen" if status == "qwen-answer" else "deterministic/router"
            )
            trace.answer_selection(selected=selected_answer, reason=status)
            trace.answer("FINAL CHAT ANSWER", response.answer)
            trace.finish(status)
            return response

        if not self.settings.enabled:
            trace.line("AI PATH", "Smart AI enhancement is disabled; deterministic answer retained.")
            return complete(deterministic_response, status="smart-ai-disabled")
        if deterministic_response.intent in self._NEVER_ENHANCE_INTENTS:
            trace.line("AI PATH", "Intent is excluded from AI enhancement; no retrieval performed.")
            return complete(deterministic_response, status="never-enhance-intent")

        is_yes_no = self._is_yes_no_question(question)
        is_follow_up = self._is_follow_up_question(question, history)

        # Exact live answers stay deterministic unless the user explicitly
        # asked a binary question or an incomplete follow-up needs resolution.
        if (
            deterministic_response.intent in self._DIRECT_LIVE_INTENTS
            and not is_yes_no
            and not is_follow_up
        ):
            trace.line("AI PATH", "Exact live HR answer retained; RAG/Qwen enhancement not needed.")
            return complete(
                HRAssistantResponse(
                    answer=_organize_answer(deterministic_response.answer),
                    intent=deterministic_response.intent,
                    actions=deterministic_response.actions,
                    sources=deterministic_response.sources,
                ),
                status="direct-live-answer",
            )

        question_tokens = _tokenize(question)
        # "How many" is a count request, not a request for an AI explanation.
        # Only route genuine explanation/how-to wording to the LLM.
        asks_for_explanation = bool(semantics.explanation_request or re.search(
            r"\b(explain|compare|comparison|difference|why|paano|bakit|pagkakaiba|summarize)\b"
            r"|\bhow\s+(?:do|does|did|is|are|can|should|to)\b",
            question,
            re.I,
        ))
        needs_ai = (
            deterministic_response.intent in self._RAG_INTENTS
            or asks_for_explanation
            or is_yes_no
            or is_follow_up
            or len(question_tokens) >= int(self.settings.min_question_tokens)
        )
        evidence_profile = _question_evidence_profile(question)
        if not needs_ai:
            trace.question_analysis(
                yes_no=is_yes_no,
                follow_up=is_follow_up,
                explanation=asks_for_explanation,
                needs_ai=False,
                token_count=len(question_tokens),
                evidence_profile=evidence_profile,
            )
            trace.line("AI PATH", "Question does not require RAG/Qwen enhancement.")
            return complete(
                HRAssistantResponse(
                    answer=_organize_answer(deterministic_response.answer),
                    intent=deterministic_response.intent,
                    actions=deterministic_response.actions,
                    sources=deterministic_response.sources,
                ),
                status="deterministic-answer",
            )

        retrieval_query = self._contextual_search_query(question, history)
        trace.question_analysis(
            yes_no=is_yes_no,
            follow_up=is_follow_up,
            explanation=asks_for_explanation,
            needs_ai=True,
            token_count=len(question_tokens),
            evidence_profile=evidence_profile,
            retrieval_query=retrieval_query,
        )
        knowledge_build_started = time.monotonic()
        documents = PortalKnowledgeBuilder(self.session).build(
            current_user=current_user,
            role_scope=role_scope,
            trace=trace,
        )
        trace.line(
            "KNOWLEDGE BUILD TIMING",
            f"company_role_filtered_build_s={time.monotonic() - knowledge_build_started:.3f}; "
            f"entries={len(documents)}",
        )
        # Exact, whole-policy questions can be answered from the same
        # authorized, current knowledge builder without loading embeddings.
        # The *strict* source matchers also run after normal retrieval below;
        # this earlier check only avoids a cold model for unambiguous overviews.
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no and not is_follow_up
            and evidence_profile in {"standard", "list"}
            and deterministic_response.intent in self._RAG_INTENTS
            and not deterministic_response.report
        ):
            available_policies = [
                RetrievedDocument(document, 0.0) for document in documents
                if document.source_type == "policy"
            ]
            record_candidates = [
                item for item in available_policies
                if str((item.document.metadata or {}).get('file_key') or '').endswith(':record')
            ]
            record_text, record_meta = _verbatim_published_policy_overview(
                retrieval_query, record_candidates,
                company_id=current_user.company_id, role_scope=role_scope,
                max_chars=int(getattr(self.settings, "grounded_extractive_max_chars", 1800)),
            )
            uploaded_text, uploaded_meta = _verbatim_complete_document_policy_overview(
                retrieval_query, available_policies,
                company_id=current_user.company_id, role_scope=role_scope,
            )
            if bool(record_text) != bool(uploaded_text):
                is_uploaded = bool(uploaded_text)
                answer = uploaded_text if is_uploaded else _organize_answer(record_text)
                meta = uploaded_meta if is_uploaded else record_meta
                if is_uploaded:
                    source_items = [
                        item for item in available_policies
                        if str((item.document.metadata or {}).get('file_key')) == str(meta['file_key'])
                    ]
                else:
                    source_items = [
                        item for item in available_policies
                        if str((item.document.metadata or {}).get('policy_id')) == str(meta['policy_id'])
                        and str((item.document.metadata or {}).get('file_key', '')).endswith(':record')
                    ]
                trace.line(
                    "VERIFIED PRE-RETRIEVAL POLICY",
                    f"source={meta.get('source', '-')}; "
                    f"type={'complete-uploaded-policy' if is_uploaded else 'published-record'}; "
                    "vector_skipped=yes; ollama_skipped=yes",
                )
                trace.top_source(source_items[0] if source_items else None)
                trace.answer("ANSWER OPTION — VERIFIED POLICY", answer)
                return complete(
                    HRAssistantResponse(
                        answer=answer,
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=self._retrieved_policy_sources(source_items),
                        report=deterministic_response.report,
                    ),
                    status="verified-policy-direct-answer",
                )

        retrieval_started = time.monotonic()
        retrieved = self.retriever.search(
            retrieval_query,
            documents,
            company_id=current_user.company_id,
            role_scope=role_scope,
            access_partition=(
                f"company:{current_user.company_id}:role:{role_scope}:"
                f"user:{current_user.user_id}"
            ),
            trace=trace,
        )
        trace.line(
            "RETRIEVAL TIMING",
            f"hybrid_total_s={time.monotonic() - retrieval_started:.3f}",
        )
        trace.retrieval_summary()

        if self._is_out_of_scope_question(
            question=question,
            history=history,
            deterministic_intent=deterministic_response.intent,
            retrieved=retrieved,
        ):
            trace.line("SCOPE CHECK", "Question classified as outside authorized company HR scope.")
            trace.top_source(retrieved[0] if retrieved else None)
            return complete(
                HRAssistantResponse(
                    answer=OUT_OF_SCOPE_ANSWER,
                    intent="out_of_scope",
                    actions=[],
                    sources=[],
                ),
                status="out-of-scope",
            )

        # A deterministic portal router can label a general conditional
        # policy question as an attendance or leave intent. Only a *complete*
        # multi-chunk policy proof (not generic title/keyword overlap) may
        # override that route. This bypass does not touch live record answers
        # and is strictly limited to already company/role-authorized policy
        # chunks. No generated or stored QA answer keys are consulted.
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no and not is_follow_up
            and not deterministic_response.report
            and re.match(r"^if\b.{8,220}\bwho\b", _clean_text(retrieval_query), re.I)
        ):
            conditional_answer = _contiguous_conditional_list_answer(
                retrieval_query, retrieved,
                max_chars=int(getattr(self.settings, "grounded_extractive_max_chars", 1800)),
            )
            if conditional_answer is not None:
                answer_text, meta = conditional_answer
                key = str(meta.get("file_key") or "")
                source_items = [
                    item for item in retrieved
                    if item.document.source_type == "policy"
                    and item.document.company_id == current_user.company_id
                    and item.document.role_scope in {"shared", role_scope}
                    and str((item.document.metadata or {}).get("file_key") or "") == key
                ]
                if len(source_items) >= 2:
                    trace.line(
                        "VERIFIED CONDITIONAL POLICY CHAIN",
                        f"decision={meta['decision']}; "
                        f"tiers={meta['items']}; "
                        "source_scope=authorized-consecutive-policy-chunks; "
                        "ollama_skipped=yes",
                    )
                    trace.answer("ANSWER OPTION — CONTIGUOUS POLICY CHAIN", answer_text)
                    return complete(
                        HRAssistantResponse(
                            answer=_organize_answer(answer_text),
                            intent=deterministic_response.intent,
                            actions=deterministic_response.actions,
                            sources=self._retrieved_policy_sources(source_items),
                            report=deterministic_response.report,
                        ),
                        status="grounded-extractive-answer",
                    )

        relevance: dict[str, object] | None = None
        # A policy eligibility or rule-consequence question can be routed to
        # Attendance/Leave by the deterministic UI router. Without this guard
        # it sends unrelated live records to Ollama for a long, inevitable
        # abstention. Evaluate *rule-bearing* evidence, not individual employee
        # activity, whenever the requested answer is a general rule.
        rule_question = evidence_profile in {"eligibility", "consequence"}
        requires_evidence_gate = (
            deterministic_response.intent in self._RELEVANCE_GUARD_INTENTS
            or rule_question
        )
        rule_sources = {
            "policy", "company_form_content", "policy_violation",
            "live_company_benefit", "portal_guide",
        }
        gate_candidates = (
            [item for item in retrieved if item.document.source_type in rule_sources]
            if rule_question else retrieved
        )
        if requires_evidence_gate:
            relevance = self._retrieval_relevance_snapshot(
                query=retrieval_query,
                retrieved=gate_candidates,
                require_answer_cue=bool(
                    getattr(self.settings, "evidence_gate_enabled", True)
                ),
                min_answer_cue=float(
                    getattr(self.settings, "evidence_gate_min_answer_cue", 0.70)
                ),
            )
            trace.relevance_guard(
                anchors=relevance["anchors"],
                matched_anchors=relevance["matched"],
                coverage=float(relevance["coverage"]),
                answer_fit=float(relevance["answer_fit"]),
                answer_cue=float(relevance.get("answer_cue") or 0.0),
                evidence_profile=str(relevance.get("evidence_profile") or "standard"),
                source=str(relevance["source"]),
                decision="ACCEPT" if relevance["accepted"] else "REJECT",
                reason=str(relevance["reason"]),
            )
            if not bool(relevance["accepted"]):
                recovered = self._recover_authorized_policy_evidence(
                    query=retrieval_query, retrieved=retrieved, documents=documents,
                    company_id=current_user.company_id, role_scope=role_scope,
                )
                if len(recovered) > len(retrieved):
                    second = self._retrieval_relevance_snapshot(
                        query=retrieval_query,
                        retrieved=(
                            [item for item in recovered if item.document.source_type in rule_sources]
                            if rule_question else recovered
                        ),
                        require_answer_cue=bool(getattr(self.settings, "evidence_gate_enabled", True)),
                        min_answer_cue=float(getattr(self.settings, "evidence_gate_min_answer_cue", 0.70)),
                    )
                    trace.line(
                        "AUTHORIZED PASSAGE RECOVERY",
                        f"candidates_added={len(recovered)-len(retrieved)}; "
                        f"accepted={second['accepted']}; source={second['source']}; "
                        f"reason={second['reason']}",
                    )
                    if second["accepted"]:
                        # Scope is identical; source label and section are
                        # carried forward to synthesis and citations.
                        retrieved = recovered
                        relevance = second
            if not bool(relevance["accepted"]):
                trace.top_source(retrieved[0] if retrieved else None)
                guard_answer = (
                    UNDETERMINED_ANSWER if is_yes_no else NOT_FOUND_ANSWER
                )
                return complete(
                    HRAssistantResponse(
                        answer=guard_answer,
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=[],
                        report=deterministic_response.report,
                    ),
                    status="relevance-guard-no-match",
                )

        display_sources = self._top_display_sources(
            deterministic_response.sources,
            retrieved,
        )
        if not display_sources:
            display_sources = self._retrieved_policy_sources(retrieved)
        trace.top_source(retrieved[0] if retrieved else None)

        if trace.enabled:
            candidate_answer_limit = max(
                320,
                int(getattr(self.settings, "terminal_debug_candidate_answer_chars", 760)),
            )
            candidate_answers = []
            for item in retrieved[: trace.top_k]:
                metadata = item.document.metadata or {}
                chunk_index = metadata.get("chunk_index") or "-"
                total_chunks = metadata.get("total_chunks") or "-"
                candidate_answers.append(
                    {
                        "retrieval_score": float(item.score),
                        "answer_fit": _evidence_fit_bonus(
                            retrieval_query, item.document
                        ),
                        "source": (
                            metadata.get("filename")
                            or metadata.get("title")
                            or item.document.title
                            or item.document.document_id
                        ),
                        "section": metadata.get("section") or "-",
                        "page": metadata.get("page_number") or "-",
                        "chunk": f"{chunk_index}/{total_chunks}",
                        "passage_diagnostic": _passage_diagnostic(retrieval_query, item.document),
                        "possible_answer": _focused_evidence_excerpt(
                            retrieval_query,
                            item.document.text,
                            candidate_answer_limit,
                        ),
                    }
                )
            trace.answer_candidates(candidate_answers)

        # A simple overview that names exactly one complete, short, published
        # editor policy should not rely on a 7B model to restate or reject it.
        # In particular, the deterministic router may label a *policy question*
        # as leave_summary or attendance rather than a policy intent. The
        # source-specific guard below, not router classification alone, decides
        # whether a verbatim answer is safe. All other questions keep RAG.
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no
            and not is_follow_up
            and evidence_profile in {"standard", "list"}
            and deterministic_response.intent in self._RAG_INTENTS
            and not deterministic_response.report
        ):
            whole_policy, overview_meta = _verbatim_published_policy_overview(
                retrieval_query, retrieved,
                company_id=current_user.company_id, role_scope=role_scope,
                max_chars=int(getattr(self.settings, "grounded_extractive_max_chars", 1800)),
            )
            trace.line(
                "VERBATIM PUBLISHED POLICY OVERVIEW",
                f"decision={overview_meta.get('decision')}; "
                f"source={overview_meta.get('source', '-')}; "
                f"ollama_skipped={'yes' if whole_policy else 'no'}",
            )
            if whole_policy:
                trace.answer("ANSWER OPTION — PUBLISHED POLICY", whole_policy)
                return complete(
                    HRAssistantResponse(
                        answer=_organize_answer(whole_policy),
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=self._retrieved_policy_sources(
                            [item for item in retrieved
                             if str((item.document.metadata or {}).get('policy_id'))
                             == str(overview_meta['policy_id'])]
                        ),
                        report=deterministic_response.report,
                    ),
                    status="published-policy-verbatim-answer",
                )

        # Generic complete-document path for simple policy overview questions.
        # Unlike the single editor-record shortcut above, this accepts an
        # uploaded policy only when *every* source chunk is retrieved and its
        # full title is unambiguous. Source text is copied, not synthesized.
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no and not is_follow_up
            and evidence_profile in {"standard", "list"}
            and deterministic_response.intent in self._RAG_INTENTS
            and not deterministic_response.report
        ):
            whole_document, document_meta = _verbatim_complete_document_policy_overview(
                retrieval_query, retrieved,
                company_id=current_user.company_id, role_scope=role_scope,
            )
            trace.line(
                "VERBATIM COMPLETE POLICY DOCUMENT",
                f"decision={document_meta.get('decision')}; "
                f"source={document_meta.get('source', '-')}; "
                f"chunks={document_meta.get('chunks', 0)}; "
                f"ollama_skipped={'yes' if whole_document else 'no'}",
            )
            if whole_document:
                source_key = str(document_meta['file_key'])
                source_items = [
                    item for item in retrieved
                    if str((item.document.metadata or {}).get('file_key')) == source_key
                ]
                trace.answer("ANSWER OPTION — COMPLETE DOCUMENT", whole_document)
                return complete(
                    HRAssistantResponse(
                        answer=whole_document,
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=self._retrieved_policy_sources(source_items),
                        report=deterministic_response.report,
                    ),
                    status="complete-policy-document-answer",
                )

        # v8.8.224 latency/faithfulness fast path: when a policy/document query
        # already has accepted, direct evidence, select complete source units
        # verbatim instead of sending a duplicate 7B rewrite request.  This is
        # intentionally limited to fact/list/procedure shapes; comparisons,
        # YES/NO, follow-ups, and synthesis-heavy standard explanations still
        # use Qwen so the assistant does not over-simplify ambiguous cases.
        fast_profiles = {
            "list", "procedure", "direct_fact", "amount", "duration_or_count",
            "date_or_time", "eligibility",
        }
        # A uniquely named policy's top-level statement can answer a purpose
        # question without invoking Qwen. Do not generalize to broad summaries
        # or nested 'Purpose' subsections of another procedure.
        named_statement = None
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no and not is_follow_up
            and not deterministic_response.report
        ):
            named_statement = _verified_source_statement_or_examples(
                retrieval_query, retrieved,
                max_chars=int(getattr(self.settings, "grounded_extractive_max_chars", 1800)),
            )
        if named_statement is None and evidence_profile == "consequence":
            named_statement = _verified_multi_condition_sanctions(
                retrieval_query, retrieved,
                max_chars=int(getattr(self.settings, "grounded_extractive_max_chars", 1800)),
            )
        if named_statement is not None:
            answer_text, statement_meta = named_statement
            trace.line(
                "VERIFIED POLICY-STRUCTURE FAST PATH",
                f"decision={statement_meta['decision']}; ollama_skipped=yes",
            )
            trace.answer("ANSWER OPTION — POLICY STRUCTURE", answer_text)
            return complete(
                HRAssistantResponse(
                    answer=_organize_answer(answer_text),
                    intent=deterministic_response.intent,
                    actions=deterministic_response.actions,
                    sources=self._retrieved_policy_sources([
                        item for item in retrieved
                        if item.document.source_type == "policy"
                        and str((item.document.metadata or {}).get("filename") or "")
                        in set(statement_meta.get("sources") or [])
                    ]) or display_sources,
                    report=deterministic_response.report,
                ),
                status="grounded-extractive-answer",
            )
        direct_fact_rejected = False
        scoped_workflow_rejected = False
        if (
            bool(getattr(self.settings, "grounded_extractive_fast_path_enabled", True))
            and not is_yes_no
            and not is_follow_up
            and evidence_profile in fast_profiles
            and deterministic_response.intent in self._RELEVANCE_GUARD_INTENTS
            and relevance is not None
            and bool(relevance.get("accepted"))
            and float(relevance.get("coverage") or 0.0)
            >= float(
                getattr(
                    self.settings,
                    "grounded_extractive_min_anchor_coverage",
                    0.60,
                )
            )
        ):
            extractive_started = time.monotonic()
            extractive_answer, extractive_meta = _grounded_extractive_answer(
                retrieval_query,
                retrieved,
                max_items=int(
                    getattr(self.settings, "grounded_extractive_max_items", 6)
                ),
                max_chars=int(
                    getattr(self.settings, "grounded_extractive_max_chars", 1800)
                ),
            )
            trace.line(
                "EXTRACTIVE VALIDATION TIMING",
                f"selection_and_target_validation_s={time.monotonic() - extractive_started:.3f}; "
                f"decision={extractive_meta.get('decision', 'no-candidates')}; "
                f"target={extractive_meta.get('target', '-')}; "
                f"covered_facets={','.join(extractive_meta.get('covered_facets') or []) or '-'}; "
                f"required_facets={','.join(extractive_meta.get('required_facets') or []) or '-'}"
            )
            if not extractive_answer and evidence_profile == "direct_fact":
                direct_fact_rejected = True
                trace.line(
                    "DIRECT FACT FALLBACK BUDGET",
                    "Grounded extraction incomplete; bounded standard Qwen attempt, no retry.",
                )
            if not extractive_answer and extractive_meta.get("decision") == "scoped-workflow-evidence-incomplete":
                scoped_workflow_rejected = True
                trace.line(
                    "BOUNDED WORKFLOW FALLBACK",
                    "A complete named workflow was not proven; compact authorized context, "
                    "standard model only, one bounded attempt, no retry.",
                )
            if extractive_answer:
                trace.line(
                    "GROUNDED EXTRACTIVE FAST PATH",
                    (
                        f"used=yes; profile={extractive_meta.get('profile')}; "
                        f"items={extractive_meta.get('items')}; "
                        f"sources={', '.join(extractive_meta.get('sources') or []) or '-'}; "
                        "ollama_skipped=yes"
                    ),
                )
                trace.answer("ANSWER OPTION — EXTRACTIVE", extractive_answer)
                return complete(
                    HRAssistantResponse(
                        answer=_organize_answer(extractive_answer),
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=self._retrieved_policy_sources([
                            item for item in retrieved
                            if str((item.document.metadata or {}).get("filename")
                                   or (item.document.metadata or {}).get("title")
                                   or item.document.title
                                   or item.document.document_id)
                            in set(extractive_meta.get("sources") or [])
                        ]) or display_sources,
                        report=deterministic_response.report,
                    ),
                    status="grounded-extractive-answer",
                )

        # Use the pre-existing bounded direct-fact model budget for any
        # narrowly rejected explicit workflow contract. No global timeout,
        # provider, or configuration changes, and never a second local retry.
        bounded_evidence_fallback = direct_fact_rejected or scoped_workflow_rejected
        context = self._build_evidence_context(
            query=retrieval_query,
            retrieved=retrieved,
            excerpt_chars=540 if bounded_evidence_fallback else None,
            max_documents=4 if bounded_evidence_fallback else None,
        )
        if bounded_evidence_fallback:
            trace.line(
                "BOUNDED ANSWER EVIDENCE",
                f"chunks={min(len(retrieved), 4)}; context_chars={len(context)}; "
                "policy_sources=authorized-only; no_retry=yes",
            )
        trace.line(
            "EVIDENCE CONTEXT",
            f"retrieved_chunks={len(retrieved)}; context_chars={len(context)}",
        )

        role_rule = (
            "You may use authorized company-wide records provided in the deterministic answer."
            if role_scope == "admin"
            else "You may use only the signed-in employee's own private records and company-wide published information."
        )
        rag_priority = deterministic_response.intent in self._RAG_INTENTS
        full_history_text = self._history_text(history)
        # For document RAG, a fallback portal/navigation hint is not a verified
        # policy answer. Preserve source-backed deterministic rules, but never
        # tell Qwen that an unsourced help reply is authoritative evidence.
        full_router_answer = deterministic_response.answer
        if rag_priority and not deterministic_response.sources and not deterministic_response.report:
            # Keep the unverified router hint entirely out of the LLM prompt.
            # A replacement sentinel is not evidence: small local models can
            # copy it into the user-facing answer as if it were policy text.
            full_router_answer = ""
            trace.line("ROUTER EVIDENCE AUTHORITY", "Unsourced RAG router hint omitted from grounded model context.")
        full_context = context
        history_text, router_answer, context = self._budget_prompt_sections(
            history_text=full_history_text,
            router_answer=full_router_answer,
            context=full_context,
            rag_priority=rag_priority,
        )
        prompt = build_hr_assistant_prompt(
            role_rule=role_rule,
            history_text=history_text,
            question=question,
            router_answer=router_answer,
            context=context,
            question_mode="yes_no" if is_yes_no else "standard",
            evidence_profile=_question_evidence_profile(question),
            follow_up=is_follow_up,
            current_datetime_text=datetime.now(
                ZoneInfo(get_settings().display_timezone)
            ).strftime("%Y/%m/%d %I:%M %p %Z"),
        )
        use_quality_model = asks_for_explanation and (
            len(question_tokens) >= int(self.settings.quality_min_question_tokens)
            or len(retrieved) >= int(self.settings.quality_min_retrieved_documents)
        )
        if bounded_evidence_fallback:
            use_quality_model = False
            history_text, router_answer, context = self._budget_prompt_sections(
                history_text=full_history_text,
                router_answer=full_router_answer,
                context=full_context,
                rag_priority=rag_priority,
                compact=True,
            )
            prompt = build_hr_assistant_prompt(
                role_rule=role_rule,
                history_text=history_text,
                question=question,
                router_answer=router_answer,
                context=context,
                question_mode="standard",
                evidence_profile=evidence_profile,
                follow_up=is_follow_up,
                current_datetime_text=datetime.now(
                    ZoneInfo(get_settings().display_timezone)
                ).strftime("%Y/%m/%d %I:%M %p %Z"),
            )
        def generation_failure_answer() -> str:
            """Never label unsourced portal navigation as a policy answer."""
            if bounded_evidence_fallback:
                return UNDETERMINED_ANSWER
            if (rag_priority and not deterministic_response.sources
                    and not deterministic_response.report):
                # Missing AI generation is not evidence that the policy is
                # absent. Never swap in a navigation hint or claim that a
                # retrieved company document was not found.
                return (
                    "A complete, verified answer could not be generated right now "
                    "because the AI service is unavailable or timed out. "
                    "Please try again."
                )
            return _organize_answer(deterministic_response.answer)

        # Cloud mode is explicit opt-in. Keep all v8.8.241 local generation and
        # retry logic below intact. The cloud never executes retrieval itself.
        selected_mode = getattr(self.settings, "llm_mode", "local")
        if selected_mode in {"groq", "hybrid"}:
            groq_model = str(getattr(self.settings, "groq_model", ""))
            groq_timeout = float(getattr(self.settings, "groq_timeout_seconds", 25.0))
            if bounded_evidence_fallback:
                groq_timeout = min(groq_timeout, max(5.0, float(
                    getattr(self.settings, "grounded_direct_fact_ollama_timeout_seconds", 30)
                )))
            trace.line(
                "GROQ REQUEST",
                f"mode={selected_mode}; provider=groq; model={groq_model}; "
                f"prompt_chars={len(prompt)}; timeout={groq_timeout}s",
            )
            cloud_started = time.monotonic()
            try:
                generated = self.groq.generate(
                    prompt, quality=use_quality_model,
                    timeout_seconds=groq_timeout,
                )
                if not generated:
                    raise RuntimeServiceResponseError("groq", detail="Empty response")
                trace.line(
                    "GROQ RESULT",
                    f"provider=groq; model={groq_model}; "
                    f"primary completed in {time.monotonic() - cloud_started:.2f}s",
                )
                trace.answer("ANSWER OPTION — ROUTER", deterministic_response.answer)
                trace.answer("ANSWER OPTION — GROQ", generated)
                final_answer = (
                    self._normalize_yes_no_answer(generated)
                    if is_yes_no else self._normalize_standard_answer(generated)
                )
                if is_yes_no and final_answer == UNDETERMINED_ANSWER:
                    trace.line("BINARY ANSWER VALIDATION", "Cloud conclusion unsupported or contradictory; abstained.")
                return complete(
                    HRAssistantResponse(
                        answer=final_answer,
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=self._answer_supported_policy_source(
                            answer=final_answer, query=retrieval_query,
                            retrieved=retrieved, fallback_sources=display_sources,
                        ) if rag_priority else display_sources,
                        report=deterministic_response.report,
                    ),
                    status="groq-answer",
                )
            except (
                RuntimeServiceModelUnavailableError,
                RuntimeServiceResponseError,
                RuntimeServiceTimeoutError,
                RuntimeServiceUnavailableError,
            ) as exc:
                # NEVER log HTTP bodies, prompts, credentials, or API keys.
                safe_failure = (
                    f"type={type(exc).__name__}; http={getattr(exc, 'status_code', '-')}; "
                    f"seconds={time.monotonic() - cloud_started:.2f}"
                )
                if selected_mode == "hybrid":
                    trace.line("GROQ FALLBACK", f"groq failed; local Ollama next; {safe_failure}")
                    # Fall through to the same Ollama path (with existing retry
                    # and safe-answer behavior) used by local-only mode.
                else:
                    trace.line("GROQ RESULT", f"groq-only unavailable; {safe_failure}")
                    issue = classify_runtime_connection_issue(exc, service_hint="groq")
                    if issue is None:
                        raise
                    log_runtime_connection_issue(
                        exc, issue,
                        context=f"chat_enhancement:{role_scope};mode=groq",
                    )
                    fallback_answer = generation_failure_answer()
                    return complete(
                        HRAssistantResponse(
                            answer=fallback_answer,
                            intent=deterministic_response.intent,
                            actions=deterministic_response.actions,
                            sources=display_sources,
                            report=deterministic_response.report,
                            runtime_warning=issue.message,
                            runtime_warning_title=issue.title,
                            runtime_warning_code=issue.code,
                        ),
                        status="groq-error-fallback",
                    )
        primary_model = (
            getattr(self.settings, "quality_ollama_model", "quality-model")
            if use_quality_model
            else getattr(self.settings, "ollama_model", "configured-model")
        )
        primary_timeout = (
            max(5.0, min(60.0, float(getattr(self.settings, "grounded_direct_fact_ollama_timeout_seconds", 30))))
            if bounded_evidence_fallback else float(getattr(self.settings, "ollama_timeout_seconds", 180))
        )
        trace.line(
            "OLLAMA REQUEST",
            (
                f"mode={selected_mode}; provider=ollama; model={primary_model}; quality={use_quality_model}; "
                f"prompt_chars={len(prompt)}; timeout={primary_timeout}s"
            ),
        )
        started = time.monotonic()
        try:
            if bounded_evidence_fallback:
                generated = self.ollama.generate(prompt, quality=False, timeout_seconds=primary_timeout)
            else:
                generated = self.ollama.generate(prompt, quality=use_quality_model)
            trace.line(
                "OLLAMA RESULT",
                f"primary completed in {time.monotonic() - started:.2f}s",
            )
        except RuntimeServiceTimeoutError as first_timeout:
            trace.line(
                "OLLAMA TIMEOUT",
                f"primary timed out after {time.monotonic() - started:.2f}s",
            )
            if bool(self.settings.ollama_timeout_retry_enabled) and not bounded_evidence_fallback:
                retry_issue = classify_runtime_connection_issue(
                    first_timeout, service_hint="ollama"
                )
                if retry_issue is None:
                    raise
                log_runtime_connection_issue(
                    first_timeout,
                    retry_issue,
                    context=f"chat_enhancement_timeout_retry:{role_scope}",
                )
                retry_history, retry_router, retry_context = self._budget_prompt_sections(
                    history_text=full_history_text,
                    router_answer=full_router_answer,
                    context=full_context,
                    rag_priority=rag_priority,
                    compact=True,
                )
                retry_prompt = build_hr_assistant_prompt(
                    role_rule=role_rule,
                    history_text=retry_history,
                    question=question,
                    router_answer=retry_router,
                    context=retry_context,
                    question_mode="yes_no" if is_yes_no else "standard",
                    evidence_profile=_question_evidence_profile(question),
                    follow_up=is_follow_up,
                    current_datetime_text=datetime.now(
                        ZoneInfo(get_settings().display_timezone)
                    ).strftime("%Y/%m/%d %I:%M %p %Z"),
                )
                trace.line(
                    "OLLAMA RETRY",
                    (
                        f"model={getattr(self.settings, 'ollama_model', 'configured-model')}; quality=False; "
                        f"prompt_chars={len(retry_prompt)}; "
                        f"timeout={self.settings.ollama_retry_timeout_seconds}s"
                    ),
                )
                retry_started = time.monotonic()
                try:
                    # One internal retry only: smaller prompt + shorter standard
                    # output budget.  This does not resubmit the user's request
                    # or create a second chat message.
                    generated = self.ollama.generate(
                        retry_prompt,
                        quality=False,
                        timeout_seconds=float(
                            self.settings.ollama_retry_timeout_seconds
                        ),
                    )
                    trace.line(
                        "OLLAMA RESULT",
                        f"retry completed in {time.monotonic() - retry_started:.2f}s",
                    )
                except (
                    RuntimeServiceModelUnavailableError,
                    RuntimeServiceResponseError,
                    RuntimeServiceTimeoutError,
                    RuntimeServiceUnavailableError,
                ) as exc:
                    issue = classify_runtime_connection_issue(
                        exc, service_hint="ollama"
                    )
                    if issue is None:
                        raise
                    log_runtime_connection_issue(
                        exc,
                        issue,
                        context=f"chat_enhancement_retry_failed:{role_scope}",
                    )
                    fallback_answer = generation_failure_answer()
                    return complete(
                        HRAssistantResponse(
                            answer=fallback_answer,
                            intent=deterministic_response.intent,
                            actions=deterministic_response.actions,
                            sources=display_sources,
                            report=deterministic_response.report,
                            runtime_warning=issue.message,
                            runtime_warning_title=issue.title,
                            runtime_warning_code=issue.code,
                        ),
                        status="ollama-retry-fallback",
                    )
            else:
                issue = classify_runtime_connection_issue(
                    first_timeout, service_hint="ollama"
                )
                if issue is None:
                    raise
                log_runtime_connection_issue(
                    first_timeout,
                    issue,
                    context=f"chat_enhancement:{role_scope}",
                )
                fallback_answer = generation_failure_answer()
                return complete(
                    HRAssistantResponse(
                        answer=fallback_answer,
                        intent=deterministic_response.intent,
                        actions=deterministic_response.actions,
                        sources=display_sources,
                        report=deterministic_response.report,
                        runtime_warning=issue.message,
                        runtime_warning_title=issue.title,
                        runtime_warning_code=issue.code,
                    ),
                    status="ollama-timeout-fallback",
                )
        except (
            RuntimeServiceModelUnavailableError,
            RuntimeServiceResponseError,
            RuntimeServiceUnavailableError,
        ) as exc:
            issue = classify_runtime_connection_issue(exc, service_hint="ollama")
            if issue is None:
                raise
            log_runtime_connection_issue(
                exc,
                issue,
                context=f"chat_enhancement:{role_scope}",
            )
            fallback_answer = generation_failure_answer()
            return complete(
                HRAssistantResponse(
                    answer=fallback_answer,
                    intent=deterministic_response.intent,
                    actions=deterministic_response.actions,
                    sources=display_sources,
                    report=deterministic_response.report,
                    runtime_warning=issue.message,
                    runtime_warning_title=issue.title,
                    runtime_warning_code=issue.code,
                ),
                status="ollama-error-fallback",
            )
        if not generated:
            trace.line("OLLAMA RESULT", "No model text returned; safe fallback retained.")
            fallback_answer = generation_failure_answer()
            return complete(
                HRAssistantResponse(
                    answer=fallback_answer,
                    intent=deterministic_response.intent,
                    actions=deterministic_response.actions,
                    sources=display_sources,
                    report=deterministic_response.report,
                ),
                status="empty-model-fallback",
            )
        trace.answer("ANSWER OPTION — ROUTER", deterministic_response.answer)
        trace.answer("ANSWER OPTION — QWEN", generated)
        trace.answer("QWEN RAW ANSWER", generated)
        final_answer = (
            self._normalize_yes_no_answer(generated)
            if is_yes_no
            else self._normalize_standard_answer(generated)
        )
        if is_yes_no and final_answer == UNDETERMINED_ANSWER:
            trace.line("BINARY ANSWER VALIDATION", "Model conclusion unsupported or contradicts explanation; abstained.")
            # Retry only a clearly contradictory *binary-prefixed* response.
            # Unanswered/ambiguous prompts remain a safe abstention; do not
            # burn an extra local generation attempt for every missing fact.
            if re.match(r"^\s*(?:\*\*)?(?:yes|no)\s*[.!,:;-]", generated, re.I):
                final_answer = self._repair_local_binary_answer(
                    question=question, retrieved=retrieved, trace=trace,
                )
        return complete(
            HRAssistantResponse(
                answer=final_answer,
                intent=deterministic_response.intent,
                actions=deterministic_response.actions,
                sources=self._answer_supported_policy_source(
                    answer=final_answer, query=retrieval_query,
                    retrieved=retrieved, fallback_sources=display_sources,
                ) if rag_priority else display_sources,
            ),
            status="hybrid-ollama-answer" if selected_mode == "hybrid" else "qwen-answer",
        )
