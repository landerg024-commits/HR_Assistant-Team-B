"""Question-agnostic guards and evaluation-only 185-case QA suite."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from scripts.qa_reference_review import read_reference_csv, parse_qa_log, review
from modules.smart_ai.portal_ai import KnowledgeDocument, RetrievedDocument, _grounded_extractive_answer

ROOT = Path(__file__).resolve().parents[1]

def _source(text, *, filename="Handbook A", key="file-a", company=11, score=.8):
    d = KnowledgeDocument(document_id=key, text=text, title=filename,
         company_id=company, role_scope="shared", source_type="policy",
         metadata={"filename":filename, "file_key":key, "version":"1"})
    return RetrievedDocument(d, score)

def _extract(question, *documents):
    return _grounded_extractive_answer(question,list(documents),max_items=6,max_chars=1800)

def _trace(q, *, portal="employee", company="TENANT", user="42"):
    return f"""================================== SESSION QUESTION #1 ==================================
Trace ID : ABC12345
Portal   : {portal}
Log File : logs/chat_assistant/company_{company}/{portal}/user_{user}/QA_Session_test.log
[1] QUESTION
----------------------------------------------------------------------------------------
{q}

[2] DETERMINISTIC / ROUTER ANSWER
----------------------------------------------------------------------------------------
-
[43] FINAL CHAT ANSWER
----------------------------------------------------------------------------------------
The approved record belongs to the signed-in employee.
[44] REQUEST SUMMARY
----------------------------------------------------------------------------------------
Total Request Time : 0.77 sec
Result : GROUNDED-EXTRACTIVE-ANSWER
"""

def test_reference_kept_outside_production_and_has_185_case_metadata():
    rows=read_reference_csv(ROOT/'qa/reference/comprehensive_185_behavior_reference.csv')
    assert len(rows)==185
    assert sum(r['portal_expected']=='Admin' for r in rows)==113
    assert sum(r['portal_expected']=='Employee' for r in rows)==38
    assert sum(r['portal_expected']=='Admin / Employee' for r in rows)==34
    assert any(r['account']=='lgarcia' for r in rows)
    assert all(r['expected_answer'] for r in rows)

def test_one_document_only_for_fast_extraction():
    a=_source('The organization awards a monthly transit subsidy to qualified staff. '
             'Staff may submit claims through the Finance Office.',key='policy-a',score=.95)
    b=_source('All departments use separate equipment maintenance rules. '
             'The procurement head is responsible for replacement parts.',key='policy-b',score=.91)
    ans,meta=_extract('What are the transit subsidy requirements?',a,b)
    assert 'equipment maintenance' not in ans and 'replacement parts' not in ans
    assert meta.get('items',0)>=1

def test_compound_facet_must_be_in_fast_answer_or_defer():
    d=_source('The orientation course requires employees to submit enrollment forms before Monday.',key='policy-a')
    ans,meta=_extract('What are the duration and fees for the orientation course?',d)
    assert ans=='' and meta.get('decision')=='compound-target-incomplete'

def test_reviewer_requires_employee_account_mapping(tmp_path):
    p=tmp_path/'QA_Session_test.log';p.write_text(_trace('Show my own report.'),encoding='utf-8')
    logs=parse_qa_log(p)
    assert logs[0]['user_key']=='42' and logs[0]['company_key']=='TENANT'
    case=[{'id':'T001','question':'Show my own report.','portal_expected':'Employee','account':'login.a','expected_answer':'own only'}]
    rows,summary=review(case,logs)
    assert rows[0]['review_status']=='Needs Account Mapping' and summary['automatically_assigned_passes']==0
    rows,_=review(case,logs,account_user_ids={'login.a':'42'})
    assert rows[0]['review_status']=='Needs Human Review'
    rows,_=review(case,logs,account_user_ids={'login.a':'not-42'})
    assert rows[0]['review_status']=='Not Run / No Exact Match'

def test_reviewer_cannot_merge_multiple_companies(tmp_path):
    ps=[]
    for company in ('A','B'):
        p=tmp_path/f'{company}.log';p.write_text(_trace('What is my balance?',portal='admin',company=company,user='admin1'),encoding='utf-8');ps+=parse_qa_log(p)
    rows,_=review([{'id':'T','question':'What is my balance?','portal_expected':'Admin'}],ps)
    assert rows[0]['review_status']=='Ambiguous Scope - Review Separately'

def test_reviewer_disambiguates_portals(tmp_path):
    p=tmp_path/'A.log';p.write_text(_trace('Show my policy.',portal='employee'),encoding='utf-8')
    rows,_=review([{'id':'T','question':'Show my policy.','portal_expected':'Admin'}],parse_qa_log(p))
    assert rows[0]['review_status']=='Not Run / No Exact Match'

def test_reference_questions_are_not_embedded_as_production_answer_keys():
    rows=read_reference_csv(ROOT/'qa/reference/comprehensive_185_behavior_reference.csv')
    old=read_reference_csv(ROOT/'qa/reference/additional_45_sample_behavior.csv')
    production='\n'.join((ROOT/p).read_text(encoding='utf-8') for p in (
        'modules/smart_ai/portal_ai.py',
        'modules/hr_assistant/hr_assistant.py',
        'modules/smart_ai/prompts/hr_assistant_prompt.py',
    ))
    assert not [r['id'] for r in rows+old if r['question'] in production]
