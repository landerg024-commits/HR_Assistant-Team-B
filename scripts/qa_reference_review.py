"""Offline, company-scoped QA reference/log review.

Never queries HR records or sends chat requests. Only examines explicitly supplied
unified QA session log files. It NEVER awards automated semantic PASS scores.

Examples:
  python scripts/qa_reference_review.py \
    --reference qa/reference/additional_45_sample_behavior.csv \
    --log logs/chat_assistant/<company>/<portal>/<user>/QA_Session_*.log \
    --output logs/qa_reviews/additional_45_review.csv

The expected answer is a QA comparison reference, NOT a source of HR authority.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_QBLOCK = re.compile(r"(?m)^={6,}\s*SESSION QUESTION #(?P<num>\d+)\s*={6,}\s*$")
_QPAT = re.compile(r"(?m)^\[1\] QUESTION\s*\r?\n-+\s*\r?\n(?P<question>.*?)(?=\r?\n\s*\r?\n\[2\])", re.S)
_ANSWER = re.compile(r"(?m)^\[\d+\] FINAL CHAT ANSWER\s*\r?\n-+\s*\r?\n(?P<answer>.*?)(?=\r?\n\[\d+\] REQUEST SUMMARY|\Z)", re.S)
_TRACE = re.compile(r"(?m)^Trace ID\s*:\s*(?P<value>\S+)")
_PORTAL = re.compile(r"(?m)^Portal\s*:\s*(?P<value>\S+)")
_LOG_LOCATION = re.compile(r"(?im)^Log File\s*:\s*.*?company_(?P<company>[^\\/]+)[\\/](?P<portal>admin|employee)[\\/]user_(?P<user>[^\\/]+)")
_TIME = re.compile(r"(?m)^Total Request Time\s*:\s*(?P<value>[0-9.]+)\s*sec")
_RESULT = re.compile(r"(?m)^Result\s*:\s*(?P<value>.+)$")


class QAReviewError(ValueError):
    """Malformed QA inputs; no silent case dropping."""


def normalize_question(value: str) -> str:
    """Only normalization, not loose/fuzzy matching that could confuse cases."""
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def _capture(regex: re.Pattern, text: str) -> str:
    found = regex.search(text)
    return found.group("value").strip() if found else ""


def parse_qa_log(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    boundaries = list(_QBLOCK.finditer(content))
    items: list[dict] = []
    for index, hit in enumerate(boundaries):
        block = content[hit.start(): boundaries[index + 1].start() if index + 1 < len(boundaries) else len(content)]
        q = _QPAT.search(block)
        if not q:
            continue
        a = _ANSWER.search(block)
        result = _RESULT.findall(block)
        times = _TIME.findall(block)
        location = _LOG_LOCATION.search(block)
        items.append({
            "company_key": location.group("company") if location else "",
            "user_key": location.group("user") if location else "",
            "question": q.group("question").strip(),
            "actual_answer": a.group("answer").strip() if a else "",
            "trace_id": _capture(_TRACE, block),
            "portal": _capture(_PORTAL, block),
            "response_seconds": times[-1] if times else "",
            "runtime_result": result[-1].strip() if result else "",
            "question_index": hit.group("num"),
            "log_file": str(path),
        })
    return items


def _field(row: dict, *names: str) -> str:
    keyed = {re.sub(r"[^a-z0-9]", "", str(k).casefold()): str(v or "").strip() for k, v in row.items() if k}
    for name in names:
        value = keyed.get(re.sub(r"[^a-z0-9]", "", name.casefold()))
        if value:
            return value
    return ""


def read_reference_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    if not raw:
        raise QAReviewError(f"No reference cases in: {path}")
    rows: list[dict] = []
    seen = set()
    for i, row in enumerate(raw, 1):
        question = _field(row, "question", "user query", "user question", "test question", "query")
        if not question:
            raise QAReviewError(f"Reference row {i} has no question: {path}")
        rid = _field(row, "id", "add-on id", "question id", "test id") or f"ROW-{i:03}"
        if rid in seen:
            raise QAReviewError(f"Duplicate reference id: {rid}")
        seen.add(rid)
        rows.append({
            "id": rid,
            "portal_expected": _field(row, "portal", "portal expected"),
            "account": _field(row, "account", "account login", "login"),
            "policy_area": _field(row, "policy_area", "policy area", "category", "module"),
            "question": question,
            "expected_answer": _field(row, "expected_answer", "reference expected answer", "ground truth", "ground truth expected answer"),
            "required_facets": _field(row, "required_facets", "key required facets", "answer criteria"),
            "suggested_source": _field(row, "suggested_source", "suggested policy to verify", "source"),
        })
    return rows


def _expected_portals(value: str) -> set[str]:
    # Grammar of the QA table, not any HR business classification.
    text = str(value or "").casefold()
    if not text:
        return set()
    expected = {p for p in ("admin", "employee") if p in text}
    return expected


def review(
    reference: list[dict], log_items: list[dict], *,
    account_user_ids: dict[str, str] | None = None,
) -> tuple[list[dict], dict]:
    """Review within explicit portal/account scopes; NEVER merge employee identities.

    An expected Employee account login is not equivalent to an opaque runtime
    user ID. A caller must explicitly supply that mapping. Shared portal tests
    should be evaluated as independent portal runs, never combined blindly.
    """
    account_user_ids = account_user_ids or {}
    by_question: dict[str, list[dict]] = {}
    for item in log_items:
        by_question.setdefault(normalize_question(item["question"]), []).append(item)
    output = []
    for row in reference:
        original = by_question.get(normalize_question(row["question"]), [])
        expected_portals = _expected_portals(row.get("portal_expected", ""))
        found = [x for x in original if not expected_portals or x.get("portal", "").casefold() in expected_portals]
        account = str(row.get("account") or "").strip()
        scope_warning = ""
        if account and "employee" in expected_portals:
            user_id = account_user_ids.get(account)
            if not user_id:
                scope_warning = "Needs Account Mapping"
                found = []
            else:
                found = [x for x in found if x.get("user_key") == user_id]
        # Do not silently merge tenant/company, accounts, or both portal runs.
        tenants = {x.get("company_key") for x in found if x.get("company_key")}
        portals = {x.get("portal") for x in found if x.get("portal")}
        users = {x.get("user_key") for x in found if x.get("user_key")}
        if len(tenants) > 1 or len(users) > 1 or len(portals) > 1:
            scope_warning = "Ambiguous Scope - Review Separately"
            found = []
        actual = found[-1] if found else {}
        result = actual.get("runtime_result", "")
        answer = actual.get("actual_answer", "")
        if scope_warning:
            status = scope_warning
        elif not found:
            status = "Not Run / No Exact Match"
        elif not answer:
            status = "Missing Final Answer"
        elif re.search(r"timeout|\berror\b|\bfail(?:ed|ure)?\b", result, re.I) or re.search(r"^Cannot be determined from the available company information\.?$", answer, re.I):
            status = "Needs Investigation"
        else:
            status = "Needs Human Review"
        output.append({
            **row, "review_status": status, "actual_answer": answer,
            "runtime_result": result, "response_seconds": actual.get("response_seconds", ""),
            "portal": actual.get("portal", ""), "trace_id": actual.get("trace_id", ""),
            "company_key": actual.get("company_key", ""), "user_key": actual.get("user_key", ""),
            "log_file": actual.get("log_file", ""), "match_count": len(found),
            "reviewer_verdict": "", "reviewer_notes": "",
        })
    summary = {
        "reference_cases": len(reference),
        "provided_qa_traces": len(log_items),
        "exact_matched_cases": sum(x["match_count"] > 0 for x in output),
        "unmatched_cases": sum(x["match_count"] == 0 for x in output),
        "status_counts": dict(Counter(x["review_status"] for x in output)),
        "automatically_assigned_passes": 0,
        "notice": "Separate tenant/portal/employee evaluation; verify authorized live records before PASS.",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    return output, summary


def save_review(rows: list[dict], summary: dict, out_csv: Path, out_json: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="A CSV containing question and expected_answer columns")
    parser.add_argument("--log", type=Path, nargs="+", required=True, help="Explicit QA_Session log path(s); do not mix tenants")
    parser.add_argument("--output", type=Path, required=True, help="Output CSV review matrix")
    parser.add_argument("--summary", type=Path, help="Optional JSON path; defaults beside output CSV")
    parser.add_argument("--account-map", type=Path, help="Optional private JSON login -> opaque log user_id mapping for Employee QA")
    args = parser.parse_args(argv)
    refs = read_reference_csv(args.reference)
    logs: list[dict] = []
    for path in args.log:
        if not path.is_file():
            parser.error(f"Log not found: {path}")
        logs.extend(parse_qa_log(path))
    mappings = {}
    if args.account_map:
        mappings = json.loads(args.account_map.read_text(encoding="utf-8-sig"))
        if not isinstance(mappings, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mappings.items()):
            parser.error("Account map must be a JSON object of login strings to runtime user_id strings")
    rows, summary = review(refs, logs, account_user_ids=mappings)
    out_json = args.summary or args.output.with_suffix(".summary.json")
    save_review(rows, summary, args.output, out_json)
    print(f"Reference={len(refs)} | exact_matched={summary['exact_matched_cases']} | pending={summary['unmatched_cases']} | automatic_passes=0")
    print(f"Review CSV: {args.output}")
    print(f"Summary JSON: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
