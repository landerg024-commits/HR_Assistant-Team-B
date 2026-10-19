"""Synthetic, general policy-source tests; evaluation reference not loaded."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _grounded_extractive_answer,
    _bounded_linked_policy_clauses,
)


def policy(text, name='Facilities Rules.docx', section='Section 1', company=4,
           group='policy:4:document:1', source='policy'):
    doc = KnowledgeDocument(
        document_id=f'{company}:{group}:1', text=text, title=name.rsplit('.', 1)[0],
        source_type=source, company_id=company, role_scope='shared',
        metadata={'filename': name, 'section': section, 'file_key': group},
    )
    return RetrievedDocument(doc, .03)


def answer(question, data, limit=1500):
    return _grounded_extractive_answer(question, data, max_items=6, max_chars=limit)


WORKSHOP = '''Section 4. Safety Certification Courses
(a) All laboratory technicians are required to attend Safety Certification Courses, arranged by the Training Team.
(b) Instructors shall evaluate each participant's safety skills by conducting an individual equipment demonstration.
(c) Scores from the evaluation are considered when assigning laboratory duties.
Section 5. Non-Technical Soft Skills
(a) The office team attends a different presentation.
(b) Participants evaluate speakers using feedback surveys.'''


def test_two_facet_actor_and_evaluation_from_one_named_subsection():
    q = 'Who is required to attend Safety Certification Courses, and how are participants evaluated?'
    txt, info = answer(q, [policy(WORKSHOP, section='Section 4. Safety Certification Courses')])
    assert 'laboratory technicians' in txt
    assert 'individual equipment demonstration' in txt
    assert 'office team' not in txt
    assert 'Scores from the evaluation' not in txt
    assert info['decision'] == 'accepted-bounded-linked-clauses'


def test_actor_and_evaluation_ignores_unrelated_neighbor():
    q = 'Who is required to attend Safety Certification Courses, and how are participants evaluated?'
    text = '''Section 4. Safety Certification Courses
(a) All laboratory technicians are required to attend Safety Certification Courses.
(b) Training programs are planned for next quarter.
Section 5. Social Skills
(a) Department employees are required to join soft skills classes.
(b) Trainers evaluate office skills in a role-play exercise.'''
    assert _bounded_linked_policy_clauses(q, [policy(text)], max_chars=1500) is None


def test_actor_eval_not_joined_across_documents_or_tenants():
    q = 'Who is required to attend Safety Certification Courses, and how are participants evaluated?'
    a = policy('(a) Laboratory technicians are required to attend Safety Certification Courses.')
    b = policy('(b) Trainers evaluate participants by inspecting equipment.', name='Separate.docx', company=99)
    assert _bounded_linked_policy_clauses(q, [a, b], max_chars=1500) is None


PRIORITY = '''Section 2. Exit Requirements
(a) The last staff member shall close the facility.
(b) If two or more workers are the last to exit the workplace, the following rules apply: (1) The highest-ranking worker takes responsibility for closing. (2) If of the same grade, the longest-serving worker is responsible. (3) If both rank and tenure are equal, everyone must sign the exit checklist.
Section 3. Car Parking
Cars are parked on the lower level.'''


def test_conditional_priority_preserves_all_tiers():
    q = 'If two workers are the last to leave the workplace, who is responsible for closing?'
    txt, info = answer(q, [policy(PRIORITY, section='Section 2. Exit Requirements')])
    assert 'highest-ranking' in txt and 'longest-serving' in txt and 'everyone must sign' in txt
    assert 'Car Parking' not in txt
    assert info['items'] == 3


def test_incomplete_tier_chain_fails_closed():
    q = 'If two workers are the last to leave the workplace, who is responsible for closing?'
    source = PRIORITY.replace('(2) If of the same grade, the longest-serving worker is responsible. ', '')
    assert _bounded_linked_policy_clauses(q, [policy(source)], max_chars=1500) is None


def test_competing_documents_same_priority_fail_closed():
    q = 'If two workers are the last to leave the workplace, who is responsible for closing?'
    a = policy(PRIORITY)
    b = policy(PRIORITY.replace('highest-ranking','longest-serving'), name='Different Rules.docx', group='other')
    assert _bounded_linked_policy_clauses(q, [a,b], max_chars=1500) is None


ENTRY = '''Section 1. Main Loading Gate
The main loading gate is used by visitors from 8:00 AM to 7:00 PM.
The Safety Department closes the loading gate at 7:00 PM unless authorized couriers remain inside.
Section 2. Rear Gate
The rear gate is reserved for employees after hours.'''


def test_time_and_exception_from_same_local_rule():
    q = 'When should the main loading gate be used for visitors?'
    txt, info = answer(q, [policy(ENTRY, section='Section 1. Main Loading Gate')])
    assert '8:00 AM to 7:00 PM' in txt
    assert 'unless authorized couriers' in txt
    assert 'rear gate' not in txt
    assert info['decision'] == 'accepted-bounded-linked-clauses'


def test_time_exception_not_borrowed_from_adjacent_section():
    q = 'When should the main loading gate be used for visitors?'
    source = '''Section 1. Main Loading Gate
The main loading gate is used by visitors from 8:00 AM to 7:00 PM.
Section 2. Rear Gate
The rear gate closes at 5:00 PM unless night-shift staff have authorization.'''
    assert _bounded_linked_policy_clauses(q, [policy(source)], max_chars=1500) is None


def test_source_roles_and_length_restrictions():
    q = 'When should the main loading gate be used for visitors?'
    assert _bounded_linked_policy_clauses(q, [policy(ENTRY, source='live_employee')], max_chars=1500) is None
    assert _bounded_linked_policy_clauses(q, [policy(ENTRY)], max_chars=50) is None


def test_unrelated_questions_remain_on_existing_path():
    assert _bounded_linked_policy_clauses('How long is a laboratory course?', [policy(WORKSHOP)], max_chars=1500) is None
    assert _bounded_linked_policy_clauses('Can employees claim the award?', [policy(WORKSHOP)], max_chars=1500) is None

CYCLE = '''Article II - Rotating Shift Pattern
Section 1. Employees can start the morning shift between 7:30 a.m. and 9:00 a.m. in fifteen-minute increments, with no grace period. The end of the shift adjusts accordingly.
Example: Time In / Time Out
7:31am 4:45pm (official start time 7:45am)
8:29am 5:30pm (official start time 8:30am)
Section 2. Rotating shifts are not assigned on weekends.'''


def test_named_policy_explanation_includes_worked_example_and_exception():
    q = 'How does the Rotating Shift Pattern policy work for employees who arrive late?'
    txt, info = answer(q, [policy(CYCLE, section='Article II Rotating Shift Pattern')])
    assert 'fifteen-minute increments' in txt
    assert '8:29am 5:30pm' in txt
    assert 'no grace period' in txt
    assert 'weekends' not in txt
    assert info['decision'] == 'accepted-bounded-linked-clauses'


def test_named_policy_example_without_section_boundary_not_claimed_complete():
    q = 'How does the Rotating Shift Pattern policy work for employees who arrive late?'
    fragment = CYCLE.split('Section 2.')[0]
    assert _bounded_linked_policy_clauses(q, [policy(fragment)], max_chars=1500) is None


def test_named_policy_requires_matching_article_subject():
    q = 'How does the Special Shift Pattern policy work for employees who arrive late?'
    assert _bounded_linked_policy_clauses(q, [policy(CYCLE)], max_chars=1500) is None


def test_actor_eval_rejects_different_subsection_even_with_correct_metadata_title():
    q = 'Who is required to attend Safety Certification Courses, and how are participants evaluated?'
    text = '''Section 4. Safety Certification Courses
(a) Laboratory technicians are required to attend Safety Certification Courses.
(b) The trainer prepares the safety presentation.
Section 5. Safety Certification of Office Personnel
(a) Office personnel are required to attend the office certification course.
(b) Trainers evaluate participants using office role-play.'''
    assert _bounded_linked_policy_clauses(q, [policy(text, section='Section 4. Safety Certification Courses')], max_chars=1800) is None


def test_actor_eval_does_not_treat_taken_into_consideration_as_attendance():
    q = 'Who is required to attend Safety Certification Courses, and how are participants evaluated?'
    source = '''Section 4. Safety Certification Courses
(a) Laboratory technicians are required to attend Safety Certification Courses.
(b) Instructors evaluate participants through a technical demonstration.
(c) The participant ratings shall also be taken into consideration.
(d) The instructors evaluate any appeals after the course.'''
    txt, _ = answer(q, [policy(source)])
    assert 'Laboratory technicians' in txt and 'technical demonstration' in txt
    assert 'taken into consideration' not in txt
