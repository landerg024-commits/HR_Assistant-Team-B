"""Unseen synthetic policy tests; no company-specific answer keys or QA IDs."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _verified_coordinated_effectivity_clauses,
    _grounded_extractive_answer,
)


def evidence(content, *, filename="Workplace Allowance.docx", section="Chapter III / Part 1 / Part 2", company=77, key="doc:77:17", chunk=3, version="1.0", role="shared"):
    meta = {"title": filename[:-5], "filename": filename, "section": section,
            "file_key": key, "chunk_index": chunk, "total_chunks": 8, "version": version}
    return RetrievedDocument(KnowledgeDocument(
        document_id=f"{key}:{chunk}", text=f"Policy: {meta['title']}. Version: {version}. Section: {section}. {content}",
        title=meta["title"], source_type="policy", company_id=company, role_scope=role, metadata=meta,
    ), 0.04)

ALLOWANCE = ("The prior quarterly grant is released by December 15. "
             "Article III - Travel Allowance Section 1. The travel allowance is effective every September, "
             "to support employees who commute by rail. Staff who completed nine months of service "
             "are eligible for the travel allowance. "
             "Regular workers receive ten days of annual leave. "
             "Section 2. Travel allowance amounts vary depending on available funding and require "
             "management approval under the approved budget. "
             "Additional annual leave is forfeited at year-end. "
             "Article IV - Childcare Grant Section 1. Childcare grant is effective in April. "
             "Employees with dependents are eligible for the grant.")


def test_policy_section_multiprong_evidence_is_verbatim_and_no_topic_contamination():
    q = "Who is eligible for the travel allowance, and when does it take effect?"
    ans = _verified_coordinated_effectivity_clauses(q, [evidence(ALLOWANCE)], max_chars=1800)
    assert ans
    text, meta = ans
    assert 'September' in text and 'nine months of service' in text
    assert 'available funding' in text and 'approved budget' in text
    for excluded in ('December 15', 'annual leave', 'Childcare grant', 'April'):
        assert excluded not in text
    assert meta['decision'] == 'accepted-coordinated-source-effectivity'


def test_same_policy_evidence_works_for_paraphrase_and_changed_values():
    altered = ALLOWANCE.replace('September', 'November').replace('nine months', 'four months').replace('available funding', 'department revenue')
    q = 'Which staff receive the travel allowance and when is it effective?'
    ans, _ = _verified_coordinated_effectivity_clauses(q, [evidence(altered)], max_chars=1800)
    assert 'November' in ans and 'four months' in ans and 'department revenue' in ans
    assert 'September' not in ans


def test_whole_extractive_path_uses_same_source_proof():
    ans, meta = _grounded_extractive_answer('Who is eligible for the travel allowance, and when does it take effect?', [evidence(ALLOWANCE)], max_items=6, max_chars=1800)
    assert meta['decision'] == 'accepted-coordinated-source-effectivity'
    assert 'nine months' in ans and 'management approval' in ans


def test_reject_missing_recipient_or_missing_date_or_unrelated_dates():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    for bad in (
        'Article III - Travel Allowance. Travel allowance takes effect in September. Charges vary by budget.',
        'Article III - Travel Allowance. Staff who completed nine months are eligible for travel allowance. No date has been set.',
        'Travel allowance is given to staff who completed nine months. Article IV - Childcare Grant. Childcare grants are effective in April.',
    ):
        assert _verified_coordinated_effectivity_clauses(q,[evidence(bad)],max_chars=1800) is None


def test_reject_policy_subject_mismatch_and_unrelated_questions():
    q = 'Who is eligible for the equipment subsidy, and when does it take effect?'
    assert _verified_coordinated_effectivity_clauses(q,[evidence(ALLOWANCE)],max_chars=1800) is None
    assert _verified_coordinated_effectivity_clauses('Who handles travel approvals?',[evidence(ALLOWANCE)],max_chars=1800) is None


def test_reject_conflicting_equally_complete_policy_sources():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    a = evidence(ALLOWANCE)
    b = evidence(ALLOWANCE.replace('September','October'),filename='Alternate Work Policies.docx',company=78,key='doc:78:33')
    assert _verified_coordinated_effectivity_clauses(q,[a,b],max_chars=1800) is None


def test_reject_truncation_and_source_budget_limit():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    assert _verified_coordinated_effectivity_clauses(q,[evidence(ALLOWANCE)],max_chars=120) is None


def test_do_not_splice_two_different_chunks_or_policies_to_fake_completeness():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    date_only=evidence('Article III - Travel Allowance. The travel allowance is effective every September.',chunk=3)
    recipient_only=evidence('Article III - Travel Allowance. Staff who worked nine months qualify for travel allowance.',chunk=4)
    assert _verified_coordinated_effectivity_clauses(q,[date_only, recipient_only],max_chars=1800) is None


def test_conflicting_policy_source_rejected_even_when_more_clauses_in_first():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    a = evidence(ALLOWANCE)
    b = evidence('Article III - Travel Allowance. Travel allowance starts in January. Staff with eight months of service are eligible for the travel allowance.', filename='Revised Travel Policy.docx', key='doc:77:99')
    assert _verified_coordinated_effectivity_clauses(q,[a,b],max_chars=1800) is None


def test_adjacent_budget_pronoun_is_preserved_but_other_benefit_excluded():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    varied = ALLOWANCE.replace('under the approved budget. ', 'under the approved budget. It is also subject to quarterly management review. ')
    answer, meta = _verified_coordinated_effectivity_clauses(q,[evidence(varied)],max_chars=1800)
    assert 'quarterly management review' in answer
    assert 'Childcare grant' not in answer
    assert meta['covered_facets'] == ['recipient','effective_date']


def test_different_article_same_file_cannot_supply_missing_effective_date():
    q = 'Who is eligible for the travel allowance, and when does it take effect?'
    sample = ('Article III - Travel Allowance. Staff with eight months of service are eligible for travel allowance. '
              'Article IV - Annual Transport Grant. The annual transport grant becomes effective in June.')
    assert _verified_coordinated_effectivity_clauses(q,[evidence(sample)],max_chars=1800) is None
