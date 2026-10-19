"""Synthetic policy-evidence tests; never encode actual company QA expected answers."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _grounded_extractive_answer,
    _structurally_complete_policy_evidence,
)


def item(body, *, filename='Skills Recognition.docx', group='p1', company=10,
         section='Recognition Policy', source='policy', chunk=1):
    doc = KnowledgeDocument(
        f'company:{company}:{group}:{chunk}', body, filename.removesuffix('.docx'),
        source, company, 'shared', {'filename': filename,
                                   'title': filename.removesuffix('.docx'),
                                   'section': section, 'file_key': group,
                                   'chunk_index': chunk, 'total_chunks': 4},
    )
    return RetrievedDocument(doc, 0.04)


def answer(question, docs):
    return _grounded_extractive_answer(question, docs, max_items=6, max_chars=1800)


COVER = (
    'Article I - Coverage of the Skills Recognition.\n'
    'The Skills Recognition applies to the following:\n'
    '1. Employees who passed the professional certification test.\n'
    '2. Employees who received awards from external organizations.\n'
    'Recognition of external awards is governed by the following conditions: '
    'a signed certificate must be reviewed by Compliance.\n'
)
TABLE = (
    'Article II - Award Classification\n'
    'LEVEL | CLASSIFICATION | PRIZE\n'
    '1 | High score in the certification examination | 10 units\n'
    '2 | - Employees who earned 94 or above in the in-house language class | 5 units\n'
)


def test_coverage_includes_each_membership_and_related_classification():
    q = 'Who is eligible for the Skills Recognition program?'
    result, meta = answer(q, [item(COVER, chunk=2), item(TABLE, chunk=3)])
    assert 'passed the professional certification test' in result
    assert 'received awards from external organizations' in result
    assert 'certificate must be reviewed by Compliance' in result
    assert 'earned 94 or above' in result
    assert '5 units' not in result
    assert meta['decision'] == 'accepted-authorized-coverage-and-classification'
    assert meta['sources'] == ['Skills Recognition.docx']


def test_no_join_across_distinct_source_policy_or_company():
    q = 'Who is eligible for the Skills Recognition program?'
    # The only classification line is in a different source/company.
    answer_text, meta = _structurally_complete_policy_evidence(
        q, [item(COVER, chunk=2), item(TABLE, company=20, group='p2', chunk=3)],
        max_chars=1800,
    ) or ('', {})
    assert not answer_text
    assert not meta


def test_general_eligibility_question_does_not_trigger_named_source_fast_path():
    assert _structurally_complete_policy_evidence(
        'Who is eligible for company programs?',
        [item(COVER, chunk=2), item(TABLE, chunk=3)], max_chars=1800,
    ) is None


def test_coverage_without_enumeration_fails_closed():
    source = item('Coverage of Skills Recognition: All employees may participate.', chunk=2)
    assert _structurally_complete_policy_evidence(
        'Who is eligible for Skills Recognition?', [source], max_chars=1800,
    ) is None


def test_post_trigger_immediate_follow_up_stays_in_one_chunk():
    q = 'When is the Skills Recognition given to an employee?'
    text = (
        'Article III - Implementation\n'
        'Section 1. The recognition shall be given after the results have been announced to the People Department.\n'
        'Section 2. The People Department shall then notify the Program Director and advise Accounts to release the certificate.\n'
        'Section 3. The ceremony happens during annual meetings.\n'
    )
    result, meta = answer(q, [item(text, chunk=4)])
    assert 'after the results' in result
    assert 'shall then notify' in result
    assert 'annual meetings' not in result
    assert meta['decision'] == 'accepted-linked-after-then-procedure'


def test_unrelated_next_step_is_not_spliced_from_another_chunk():
    q = 'When is the Skills Recognition given to an employee?'
    a = item('The recognition is given after approval is announced.', chunk=1)
    b = item('The other program shall then notify Finance of its own budget.', group='p2', chunk=2)
    assert _structurally_complete_policy_evidence(q, [a, b], max_chars=1800) is None


def test_compound_duration_and_approval_from_single_authorized_section():
    q = 'How long can an employee use the call facility, and what is required for off-site usage?'
    text = (
        'Section 4. Call facility guidelines:\n'
        'a. Duration of time not more than five (5) minutes.\n'
        'b. For off-site usage, employees are required to log the date and name of requester.\n'
        'Approval of the Operations Department is necessary before the off-site request.\n'
        'Section 5. Staff uniform policy.\n'
    )
    result, meta = answer(q, [item(text, filename='Operations Guide.docx', section='Call facility guidelines')])
    assert 'five (5) minutes' in result
    assert 'required to log the date' in result
    assert 'Approval of the Operations Department' in result
    assert 'Staff uniform policy' not in result
    assert meta['decision'] == 'accepted-coherent-duration-and-requirement'


def test_compound_answer_requires_approval_and_duration_locally():
    q = 'How long can an employee use the call facility, and what is required for off-site usage?'
    a = item('a. No more than five (5) minutes. b. Required to log every event.', section='Call facility guidelines')
    b = item('Approval of a completely different program is required.', group='p2')
    assert _structurally_complete_policy_evidence(q, [a, b], max_chars=1800) is None


def test_no_source_overrun_on_large_coverage_body():
    q = 'Who is eligible for the Skills Recognition program?'
    too_large = item(COVER + ('Additional obligations are documented. ' * 200),chunk=2)
    assert _structurally_complete_policy_evidence(q, [too_large, item(TABLE,chunk=3)], max_chars=1800) is None
