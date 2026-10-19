"""Lightweight query-shape analysis for safe HR routing.

This module deliberately classifies *how* a user is asking for information,
not the company's HR policy or business meaning.  It is therefore safe to use
as a deterministic guard before live-record handlers: unsupported conditions
must fall through to retrieval/other routes rather than being silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class QuerySemantics:
    """Generic linguistic shape of one user request."""

    request_shape: str
    confidence: float
    collection_request: bool = False
    explanation_request: bool = False


_SPACE_RE = re.compile(r"\s+")
# Grammar-only patterns: these describe the information requested, never the
# HR topic, policy substance, company, or a list of canned QA phrases.
_CONDITIONAL_CLAUSE_RE = re.compile(
    r"^\s*(?:if|in case of|in the event of|during|after|before|upon|when)\b[^?]*?,\s*",
    re.I,
)
_RESPONSIBILITY_RE = re.compile(
    r"^\s*(?:who\s+(?:(?:is|are)\s+(?:responsible|accountable)\b|"
    r"(?:should|must|needs?\s+to|has\s+to|is\s+required\s+to|"
    r"will|shall|pays?|shoulders?|handles?)\b)|"
    r"who\s+to\s+(?:inform|notify|contact|approach)|"
    r"whose\s+(?:responsibility|duty)\b)",
    re.I,
)
_REQUESTED_ACTION_RE = re.compile(
    r"^\s*(?:(?:what|which)\s+(?:should|must|can|could)\b|"
    r"how\s+(?:should|must|can|could|does|do|to)\b|"
    r"(?:paano|ano\s+ang\s+dapat)\b)",
    re.I,
)

_COUNT_RE = re.compile(r"^\s*(?:how\s+many|count(?:\s+the)?|number\s+of|ilan)\b", re.I)
_CHART_RE = re.compile(
    r"^\s*(?:show|display|give|create|make|plot|graph|chart|visualize)\b.*\b(?:chart|graph|plot|breakdown|visual)\b"
    r"|\b(?:bar|pie|line)\s+chart\b",
    re.I,
)
_GROUP_RE = re.compile(
    r"^\s*(?:what|which)\s+departments?\b|"
    r"^\s*(?:show|list|give|display)\b.*\b(?:departments?|breakdown)\b",
    re.I,
)
_LIST_RE = re.compile(
    r"^\s*(?:"
    r"(?:mga\s+)?sino\b|"
    r"who\b|"
    r"which\b|"
    r"list\b|"
    r"show(?:\s+me)?\b|"
    r"display\b|"
    r"find\b|"
    r"give\s+me\s+(?:the\s+)?names?\b|"
    r"names?(?:\s+of\b)?"
    r")",
    re.I,
)
_PROCEDURE_RE = re.compile(
    r"^\s*(?:how\s+(?:do|does|did|can|could|should|to)\b|what\s+should\b|paano\b)",
    re.I,
)
_EXPLANATION_RE = re.compile(
    r"^\s*(?:what\b|why\b|when\b|where\b|ano\b|bakit\b|kailan\b|saan\b|explain\b|describe\b|tell\s+me\s+about\b|summarize\b)",
    re.I,
)
_YES_NO_RE = re.compile(
    r"^\s*(?:can|could|may|might|should|would|will|do|does|did|is|are|was|were|has|have|had|am)\b",
    re.I,
)


def normalize_query_text(value: str) -> str:
    """Return compact text for linguistic routing only."""

    return _SPACE_RE.sub(" ", str(value or "").strip())


def analyze_query_semantics(question: str) -> QuerySemantics:
    """Classify generic request shape without interpreting HR business rules."""

    clean = normalize_query_text(question)
    if not clean:
        return QuerySemantics("empty", 1.0)
    # A leading condition does not determine the expected answer shape.  For
    # example "In case of X, who should Y inform?" asks for a responsibility,
    # not for case records or an employee headcount.
    request_clause = _CONDITIONAL_CLAUSE_RE.sub("", clean, count=1)
    if request_clause == clean and re.match(
        r"^(?:if|in case of|in the event of|during|after|before|upon|when)\b",
        clean, re.I,
    ):
        # Some existing HR routers normalize away punctuation before calling
        # this analyzer. Recover the main question clause even without commas.
        main_clause = re.search(
            r"\b(?:who\s+(?:(?:is|are)\s+responsible|should|must|needs?\s+to)|"
            r"what\s+should|which\s+should|how\s+should)\b", clean, re.I,
        )
        if main_clause:
            request_clause = clean[main_clause.start():]
    if _RESPONSIBILITY_RE.search(request_clause):
        return QuerySemantics("responsibility", 0.95, explanation_request=True)
    if _REQUESTED_ACTION_RE.search(request_clause):
        return QuerySemantics("requested_action", 0.94, explanation_request=True)
    if _COUNT_RE.search(request_clause):
        return QuerySemantics("count", 0.98, collection_request=True)
    if _CHART_RE.search(request_clause):
        return QuerySemantics("chart", 0.96, collection_request=True)
    if _GROUP_RE.search(request_clause):
        return QuerySemantics("group", 0.94, collection_request=True)
    if _LIST_RE.search(request_clause):
        return QuerySemantics("entity_list", 0.94, collection_request=True)
    if _PROCEDURE_RE.search(request_clause):
        return QuerySemantics("procedure", 0.94, explanation_request=True)
    if _EXPLANATION_RE.search(request_clause):
        return QuerySemantics("explanation", 0.92, explanation_request=True)
    if _YES_NO_RE.search(request_clause):
        return QuerySemantics("yes_no", 0.90, explanation_request=True)
    return QuerySemantics("unknown", 0.45)


def employee_aggregate_shape_compatible(question: str) -> bool:
    """Return whether the user explicitly asked for collection-style output.

    A relative clause such as ``employees who reach five years`` must not count
    as a list request merely because the word ``who`` appears later in the
    sentence.  Only the leading request clause determines this result.
    """

    return analyze_query_semantics(question).collection_request


# Intent-to-output compatibility is a safety boundary shared by both portals.
# Do not use this to determine any business policy or employee status: only
# disallow a deterministic *output family* when its question shape conflicts.
# Report payloads remain authoritative only when a real report exists.
def validate_deterministic_answer_shape(
    question: str,
    intent: str,
    answer: str,
    *,
    has_report: bool = False,
) -> tuple[bool, str]:
    semantics = analyze_query_semantics(question)
    shape = semantics.request_shape
    response = str(answer or "").casefold()
    if intent in {"sensitive_security", "empty"}:
        return True, "security-or-empty"
    if intent == "live_report":
        return (has_report, "verified-report" if has_report else "report-payload-missing")
    if intent == "employee_aggregate":
        allowed = semantics.collection_request
        return allowed, "collection-shape" if allowed else "not-a-collection-request"
    if intent == "employee_hierarchy":
        # A hierarchy is a live reporting relationship, not an answer to an
        # unrelated responsibility or procedural question mentioning a manager.
        allowed = shape not in {"responsibility", "requested_action", "procedure"}
        return allowed, "hierarchy-shape" if allowed else "relationship-not-requested"
    # All direct live-record families must answer an actual record-shaped
    # request. This remains a generic response-class guard: no company-specific
    # benefits, leave rules, policy content or invented intent keywords.
    if intent in {
        "employee_lookup", "employee_profile", "leave_balance", "leave_status",
        "employee_summary", "account_summary", "leave_summary",
        "announcement_summary", "policy_summary", "dashboard",
    }:
        allowed = shape not in {"responsibility", "requested_action", "procedure"}
        return allowed, "live-record-shape" if allowed else "live-record-not-requested"
    if intent == "disciplinary_records":
        # Case listing/counts can only answer record-oriented requests.  An
        # incidental phrase such as 'in case of sickness' is not a case lookup.
        allowed = shape not in {"responsibility", "requested_action", "procedure"}
        allowed = allowed and ("disciplinary" in response or "case" in response)
        return allowed, "case-record-shape" if allowed else "case-record-not-requested"
    if intent == "policy_violation":
        # Published rule definitions are not private employee case records.
        return True, "verified-violation-rule"
    if intent == "leave_carryover":
        return True, "configured-leave-rule"
    return True, "other-deterministic-intent"
