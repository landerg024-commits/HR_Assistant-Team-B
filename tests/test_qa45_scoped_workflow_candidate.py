"""Evaluation-only, synthetic policy workflows; no customer answers or fixtures."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument,
    _scoped_workflow_question, _question_evidence_profile,
    _grounded_extractive_answer,
)


def evidence(text, *, name='Operations Handbook.docx', section='Section 6: Workflows',
             company=10, group='policy-A', suffix='1', continuation=False, source='policy'):
    doc = KnowledgeDocument(
        document_id=f'{company}:{group}:{suffix}', text=text,
        title=name.removesuffix('.docx'), source_type=source,
        company_id=company, role_scope='shared',
        metadata={'filename': name, 'file_key': group, 'section': section,
                  'continuation_after': int(continuation), 'version': '1'},
    )
    return RetrievedDocument(doc, .05)


POLICIES = '''Section 6: On-Site Safety Exercises
(a) Off-Site Safety Exercises
1. Facilities Managers arrange the exercises at external sites.
2. The Regional Director approves the external exercise calendar.
3. External participants submit attendance sheets to Safety.
(b) On-Site Safety Exercises
1. Area Supervisors organize the on-site exercises with the Safety team.
2. The exercise coordinator prepares the schedule for department review and the Director approves it.
3. Participants evaluate the exercise and the facilitator reports results to the department head.
Section 7: Overnight Trips
1. Drivers submit the travel plan.
2. Supervisors approve the trip.
'''


def answer(question, docs):
    return _grounded_extractive_answer(question, docs, max_items=6, max_chars=1800)


def test_passive_multi_action_query_maps_to_procedure():
    q = 'How are On-Site Safety Exercises organized and approved?'
    assert _question_evidence_profile(q) == 'procedure'
    assert _scoped_workflow_question(q) == ('On-Site Safety Exercises', ('organize', 'approve'))


def test_named_workflow_returns_all_numbered_steps_and_excludes_neighbor():
    q = 'How are On-Site Safety Exercises organized and approved?'
    response, meta = answer(q, [evidence(POLICIES)])
    assert 'Area Supervisors organize' in response
    assert 'Director approves it' in response
    assert 'Participants evaluate' in response
    assert 'Off-Site Safety Exercises' not in response
    assert 'Overnight Trips' not in response
    assert meta['decision'] == 'accepted-scoped-numbered-workflow'
    assert meta['items'] == 3
    assert meta['sources'] == ['Operations Handbook.docx']


def test_negative_qualifier_distinguishes_sibling_subsections():
    q = 'How are Off-Site Safety Exercises arranged and approved?'
    output, info = answer(q, [evidence(POLICIES)])
    assert 'Facilities Managers arrange' in output
    assert 'Regional Director approves' in output
    assert 'Area Supervisors organize' not in output
    assert info['decision'] == 'accepted-scoped-numbered-workflow'


def test_wrong_named_subsection_fails_closed():
    q = 'How are Satellite Safety Exercises organized and approved?'
    output, info = answer(q, [evidence(POLICIES)])
    assert output == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_no_approval_step_fails_closed_without_unrelated_join():
    text = ('(b) On-Site Safety Exercises\n'
            '1. Area Supervisors organize each session.\n'
            '2. Participants evaluate their session.\n'
            'Section 7. On-Site Safety Certificates\n'
            '1. The Director approves the certificate.\n')
    result, info = answer('How are On-Site Safety Exercises organized and approved?', [evidence(text)])
    assert result == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_incomplete_numbering_fails_closed():
    text = ('(b) On-Site Safety Exercises\n'
            '1. Area Supervisors organize the exercises.\n'
            '3. The Director approves the event.\n')
    result, info = answer('How are On-Site Safety Exercises organized and approved?', [evidence(text)])
    assert result == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_continuation_after_fails_closed_even_with_first_steps():
    text = ('(b) On-Site Safety Exercises\n'
            '1. Area Supervisors organize exercises.\n'
            '2. The Director approves the planned exercises.\n')
    result, info = answer('How are On-Site Safety Exercises organized and approved?', [evidence(text, continuation=True)])
    assert result == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_cross_company_chunks_not_merged_as_single_workflow():
    a = evidence('(b) On-Site Safety Exercises\n1. Safety Staff organize drills.', company=10)
    b = evidence('2. The Director approves drills.\n3. Participants evaluate drills.', company=20, group='B')
    result, info = answer('How are On-Site Safety Exercises organized and approved?', [a,b])
    assert result == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_no_cross_document_assembly_even_when_same_company():
    a = evidence('(b) On-Site Safety Exercises\n1. Safety Staff organize drills.', group='A')
    b = evidence('(b) On-Site Safety Exercises\n2. The Director approves drills.\n3. Participants evaluate drills.', group='B')
    result, info = answer('How are On-Site Safety Exercises organized and approved?', [a,b])
    assert result == ''
    assert info['decision'] == 'scoped-workflow-evidence-incomplete'


def test_only_policy_source_can_prove_workflow():
    result, meta = answer('How are On-Site Safety Exercises organized and approved?', [evidence(POLICIES, source='live_employee')])
    assert result == ''
    assert meta['decision'] == 'scoped-workflow-evidence-incomplete'


def test_no_truncation_of_long_procedure():
    text = ('(b) On-Site Safety Exercises\n'
            '1. Area Supervisors organize ' + 'complex drills ' * 100 + '\n'
            '2. The Director approves ' + 'planning records ' * 100 + '\n')
    result, meta = answer('How are On-Site Safety Exercises organized and approved?', [evidence(text)])
    assert not result
    assert meta['decision'] == 'scoped-workflow-evidence-incomplete'


def test_unrelated_normal_questions_not_converted_to_scoped_workflows():
    for q in ('How long is the annual briefing?', 'What are the requirements for attendance?',
              'How do I request leave?', 'When does the training start?',
              'How are managers classified?'):
        assert _scoped_workflow_question(q) is None
