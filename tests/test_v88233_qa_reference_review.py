"""v8.8.233 regression — QA review never fabricates a pass or mixes user scopes."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.qa_reference_review import (
    QAReviewError,
    normalize_question,
    parse_qa_log,
    read_reference_csv,
    review,
    save_review,
)


def _log(q: str, a: str, result="GROUNDED-EXTRACTIVE-ANSWER", secs="0.56"):
    return f"""========================================================================================
================================== SESSION QUESTION #1 ==================================
========================================================================================
Trace ID : TEST1234
Portal   : admin
[1] QUESTION
----------------------------------------------------------------------------------------
{q}

[2] DETERMINISTIC / ROUTER ANSWER
----------------------------------------------------------------------------------------
Example
[42] FINAL ANSWER SELECTION
----------------------------------------------------------------------------------------
Selected : deterministic/router
[43] FINAL CHAT ANSWER
----------------------------------------------------------------------------------------
{a}
[44] REQUEST SUMMARY
----------------------------------------------------------------------------------------
Total Request Time      : {secs} sec
Result                  : {result}
========================================================================================
SESSION CHECKPOINT | question=1 | trace=TEST1234
"""


def _ref(question="Who notifies management?"):
    return [{"id":"ADD-001","question":question,"policy_area":"Policy","expected_answer":"Immediate superior","required_facets":"Recipient list","suggested_source":"Policy.docx"}]


def test_normalization_is_question_only_not_semantic_similarity():
    assert normalize_question("Who  notifies management?!") == normalize_question("WHO notifies MANAGEMENT")
    assert normalize_question("Who notifies HR?") != normalize_question("Who notifies management?")


def test_realistic_trace_parse(tmp_path):
    path = tmp_path / "QA_Session_test.log"
    path.write_text(_log("Who notifies management?", "Immediate superior.", secs="0.44"),encoding="utf-8")
    found = parse_qa_log(path)
    assert len(found) == 1
    assert found[0]["trace_id"] == "TEST1234"
    assert found[0]["portal"] == "admin"
    assert found[0]["response_seconds"] == "0.44"
    assert found[0]["actual_answer"] == "Immediate superior."
    assert found[0]["runtime_result"] == "GROUNDED-EXTRACTIVE-ANSWER"


def test_match_needs_human_review_not_pass(tmp_path):
    path = tmp_path / "qa.log"
    path.write_text(_log("Who notifies management?", "Immediate superior."),encoding="utf-8")
    rows, summary = review(_ref(),parse_qa_log(path))
    assert rows[0]["review_status"] == "Needs Human Review"
    assert rows[0]["reviewer_verdict"] == ""
    assert summary["automatically_assigned_passes"] == 0
    assert summary["exact_matched_cases"] == 1


def test_unmatched_awaits_real_testing():
    rows, summary = review(_ref(),[])
    assert rows[0]["review_status"] == "Not Run / No Exact Match"
    assert summary["unmatched_cases"] == 1


def test_timeout_and_unavailable_answer_flagged(tmp_path):
    path = tmp_path / "QA_Session_timeout.log"
    path.write_text(_log("Who notifies management?", "Cannot be determined from the available company information.",result="OLLAMA-TIMEOUT-FALLBACK",secs="32.1"),encoding="utf-8")
    rows,_ = review(_ref(),parse_qa_log(path))
    assert rows[0]["review_status"] == "Needs Investigation"


def test_last_observation_selected_but_count_preserved(tmp_path):
    p1=tmp_path/"qa1.log"; p2=tmp_path/"qa2.log"
    p1.write_text(_log("Who notifies management?", "Old"),encoding="utf-8")
    p2.write_text(_log("Who notifies management?", "New"),encoding="utf-8")
    rows,_=review(_ref(),parse_qa_log(p1)+parse_qa_log(p2))
    assert rows[0]["actual_answer"]=="New" and rows[0]["match_count"]==2


def test_incomplete_log_does_not_crash(tmp_path):
    p=tmp_path/"incomplete.log"
    p.write_text("SESSION QUESTION #1\nNo final segment",encoding="utf-8")
    assert parse_qa_log(p)==[]


def test_reference_csv_aliases_and_duplicates(tmp_path):
    path=tmp_path/"reference.csv"
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(["Add-on ID","User Query","Ground Truth (Expected Answer)","Category"])
        w.writerow(["ADD-001","What is the policy?","Document only","Policies"])
    rows=read_reference_csv(path)
    assert rows[0]["id"]=="ADD-001" and rows[0]["expected_answer"]=="Document only"
    with path.open('a',encoding='utf-8',newline='') as f:
        csv.writer(f).writerow(["ADD-001","Other","Other answer","Policies"])
    with pytest.raises(QAReviewError,match="Duplicate"):
        read_reference_csv(path)


def test_export_review_csv_json(tmp_path):
    rows,summary=review(_ref(),[])
    out=tmp_path/"out.csv"; summary_path=tmp_path/"out.json"
    save_review(rows,summary,out,summary_path)
    assert out.exists() and summary_path.exists()
    assert "ADD-001" in out.read_text(encoding='utf-8-sig')
    assert '"automatically_assigned_passes": 0' in summary_path.read_text(encoding='utf-8')


def test_real_reference_has_45_unique_questions_and_no_hardcoded_answers():
    path=Path(__file__).resolve().parents[1]/"qa/reference/additional_45_sample_behavior.csv"
    rows=read_reference_csv(path)
    assert len(rows)==45
    assert len({normalize_question(r["question"]) for r in rows})==45
    assert all(r["expected_answer"] for r in rows)
    assert all(r["id"]==f"ADD-{i:03d}" for i,r in enumerate(rows,1))
