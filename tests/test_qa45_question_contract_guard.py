"""Synthetic, evaluation-only QA category protections; no actual answer keys."""

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _explicit_question_contract_shape,
    _grounded_extractive_answer,
)


def policy(text, *, filename='Service Recognition.docx', section='Coverage',
           company=21, group='recognized:1', chunk=1, role='shared'):
    doc = KnowledgeDocument(
        document_id=f'{company}:{group}:{chunk}', text=text,
        title=filename.removesuffix('.docx'), source_type='policy',
        company_id=company, role_scope=role,
        metadata={'filename': filename, 'section': section, 'file_key': group,
                  'chunk_index': chunk, 'total_chunks': 4},
    )
    return RetrievedDocument(doc, 0.04)


def extract(question, documents):
    return _grounded_extractive_answer(question, documents, max_items=6, max_chars=1800)


COVERAGE = (
    'Article I - Coverage of Service Recognition\n'
    'Service Recognition is implemented to the following:\n'
    '1. Employees who passed a certification examination.\n'
    '2. Employees who are given awards or citations by clients.\n'
    'Awards given by clients are processed when:\n'
    'A. The client informs leadership about the commendation.\n'
    'B. The client directly granted the employee a certificate of award.\n'
)


def test_classifies_three_risk_shapes_without_case_specific_identifiers():
    assert _explicit_question_contract_shape(
        'If a client directly grants a certificate, can an employee receive Service Recognition?'
    ) == 'conditional_yes_no'
    assert _explicit_question_contract_shape(
        'When and where are Service Recognition awards presented?'
    ) == 'event_time_place'
    assert _explicit_question_contract_shape(
        'When is the spring incentive paid, and when is the autumn incentive paid?'
    ) == 'parallel_dates'
    assert _explicit_question_contract_shape('What is the approval process?') is None


def test_conditional_premise_is_proven_by_member_and_condition_same_chunk():
    query = 'If a client directly grants an employee a certificate of award, can the employee receive Service Recognition?'
    text, meta = extract(query, [policy(COVERAGE)])
    assert text.startswith('Yes.')
    assert 'awards or citations by clients' in text
    assert 'client directly granted' in text
    assert 'certification examination' not in text
    assert meta['decision'] == 'accepted-conditional-coverage-proof'


def test_conditional_does_not_use_unrelated_eligibility_evidence():
    query = 'If a client directly grants an employee a certificate of award, can the employee receive Service Recognition?'
    irrelevant = policy(
        'Service Recognition is implemented to the following:\n'
        '1. Employees who pass a certification examination.\n'
        '2. Employees who earn the highest annual score.',
    )
    text, meta = extract(query, [irrelevant])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_false_or_negative_premise_does_not_assert_yes():
    query = 'If a client does not grant a certificate, can an employee receive Service Recognition?'
    text, meta = extract(query, [policy(COVERAGE)])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_conditional_does_not_join_two_companies_or_separate_policies():
    query = 'If a client directly grants an employee a certificate of award, can the employee receive Service Recognition?'
    member = policy('Service Recognition is implemented to the following:\n'
                    '1. Employees who receive awards or citations by clients.')
    condition = policy('B. The client directly granted the employee a certificate of award.',
                       company=22, group='recognized:2')
    text, meta = extract(query, [member, condition])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


EVENT = (
    'Article III - Implementation\n'
    'Section 1. Awards are presented during afternoon briefings.\n'
    'Section 2. People in Tier A will be additionally acknowledged at the annual celebration party.\n'
)


def test_event_time_and_place_preserves_both_event_clauses():
    query = 'When and where are Service Recognition awards presented?'
    text, meta = extract(query, [policy(EVENT, section='Implementation')])
    assert 'during afternoon briefings' in text
    assert 'at the annual celebration party' in text
    assert meta['decision'] == 'accepted-explicit-event-time-place'


def test_event_time_and_place_does_not_return_award_timing_unrelated_to_place():
    query = 'When and where are Service Recognition awards presented?'
    text, meta = extract(query, [policy(
        'The awards shall be given after examination results have been announced.'
    )])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_event_answer_not_sourced_from_unrelated_document():
    query = 'When and where are Service Recognition awards presented?'
    text, meta = extract(query, [policy(
        'The awards are presented during a staff meeting.',
        filename='Other Handbook.docx', group='other:1')])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


SPRING = (
    'Section 2. Spring Incentive\n'
    'The company determines the spring incentive at its discretion.\n'
    'It is paid to staff not later than May 19.\n'
)
AUTUMN = (
    'Section 3. Autumn Incentive\n'
    'The autumn incentive is based on past performance.\n'
    'It is paid to staff not later than October 27.\n'
)
PAIRED_Q = 'When is the spring incentive paid, and when is the autumn incentive paid?'


def test_parallel_dates_require_both_named_deadlines_from_same_document():
    text, meta = extract(PAIRED_Q, [
        policy(SPRING, filename='Staff Benefits.docx', section='Spring Incentive', chunk=1, group='staff:1'),
        policy(AUTUMN, filename='Staff Benefits.docx', section='Autumn Incentive', chunk=2, group='staff:1'),
    ])
    assert 'May 19' in text and 'October 27' in text
    assert 'past performance' not in text
    assert meta['decision'] == 'accepted-parallel-topic-deadlines'


def test_parallel_dates_reject_borrowed_unrelated_months_and_one_sided_answers():
    text, meta = extract(PAIRED_Q, [
        policy('The spring incentive performance window ends in May.',
               filename='Staff Benefits.docx', section='Spring Incentive', group='staff:1'),
        policy(AUTUMN, filename='Staff Benefits.docx', section='Autumn Incentive',
               group='staff:1', chunk=2),
    ])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_parallel_deadlines_do_not_join_tenants_or_distinct_documents():
    text, meta = extract(PAIRED_Q, [
        policy(SPRING, filename='Staff Benefits.docx', section='Spring Incentive', group='staff:1'),
        policy(AUTUMN, filename='Staff Benefits.docx', section='Autumn Incentive',
               group='staff:2', company=22, chunk=2),
    ])
    assert not text
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_fast_path_for_unrelated_simple_duration_preserved():
    query = 'How long may a personal break last?'
    document = policy('Employees may take a personal break for five (5) minutes.',
                      filename='Office Rules.docx', section='Personal break')
    text, meta = extract(query, [document])
    assert 'five (5) minutes' in text
    assert meta['decision'] != 'explicit-question-contract-unproven'


def test_event_contract_does_not_confuse_attending_a_party_with_award_ceremony():
    q = 'When and where are Service Recognition awards presented?'
    source = policy(
        'Section 1. Award winners may attend a staff celebration party.\n'
        'Section 2. The official recognition dates will be announced later.'
    )
    answer, meta = extract(q, [source])
    assert not answer
    assert meta['decision'] == 'explicit-question-contract-unproven'


def test_event_does_not_merge_unrelated_celebration_in_same_chunk():
    q = 'When and where are Service Recognition awards presented?'
    source = policy(
        'Section 1. The awards are presented during afternoon briefings.\n'
        'Section 2. The department separately holds a party at the auditorium.'
    )
    answer, meta = extract(q, [source])
    assert 'during afternoon briefings' in answer
    assert 'auditorium' not in answer
    assert meta['decision'] == 'accepted-explicit-event-time-place'


def test_pluralized_named_policy_title_keeps_event_fast_path():
    q = 'When and where are Service Recognition awards presented?'
    entry = policy('Awards are presented during afternoon briefings.',
                   filename='Service Recognitions.docx', section='Implementation')
    answer, meta = extract(q, [entry])
    assert 'afternoon briefings' in answer
    assert meta['decision'] == 'accepted-explicit-event-time-place'


def test_conditional_rewording_keeps_direct_same_clause_proof():
    q = ('If a client gives an employee a certificate of award directly, '
         'can the employee qualify for Service Recognition?')
    answer, meta = extract(q, [policy(COVERAGE)])
    assert answer.startswith('Yes.')
    assert 'client directly granted' in answer
    assert meta['decision'] == 'accepted-conditional-coverage-proof'
