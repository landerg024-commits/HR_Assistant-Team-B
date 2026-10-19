"""v8.8.234: generalized policy-answer checks, not production QA lookup rules."""
from modules.hr_assistant.query_semantics import validate_deterministic_answer_shape
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, SmartPortalAssistant,
    _question_evidence_profile, _grounded_extractive_answer,
    _explicit_exception_yes_no, _answerability_cue_bonus,
)


def passage(body, *, title='Employee Policy', key='policy:5', scope=1, rank=.8):
    return RetrievedDocument(KnowledgeDocument(
        document_id=f'{key}:1', text=body, title=title, source_type='policy',
        company_id=scope, role_scope='shared',
        metadata={'filename':title+'.docx','section':'Rule','file_key':key,'version':'1'}
    ),rank)


def test_record_answer_must_relate_to_requested_subject():
    ok, why = validate_deterministic_answer_shape('Who is eligible for the advancement award?',
       'employee_profile','Employee record for System Administrator: Employee Number ADMIN-001, Work Email admin@example.com')
    assert not ok and why == 'live-record-topic-mismatch'


def test_compatible_live_own_record_still_works():
    ok,_=validate_deterministic_answer_shape('What is my employee number?',
       'employee_profile','Employee record: 12345')
    assert ok


def test_policy_violation_topic_mismatch_rejected():
    for question in ('What happens if an employee loses a company office key or makes an unauthorized duplicate?',
                     'How long may a personal telephone call last?',
                     'What training must supervisors attend?'):
        ok,_=validate_deterministic_answer_shape(question,'policy_violation',
                'QA-V002 — Unauthorized Absence. Absence without approved leave. Written warning.')
        assert not ok


def test_correct_violation_still_accepted():
    ok,_=validate_deterministic_answer_shape('What is the penalty for unauthorized absence?',
           'policy_violation','Unauthorized Absence. First offense: Written warning.')
    assert ok


def test_case_record_is_not_generic_policy():
    ok,_=validate_deterministic_answer_shape('How are office keys managed?',
           'disciplinary_records','Disciplinary case: unauthorized absence')
    assert not ok


def test_profile_detects_purpose_threshold_consequence_list():
    assert _question_evidence_profile('What is the purpose of the workplace improvement program?')=='purpose'
    assert _question_evidence_profile('What grade must the trainees obtain?')=='threshold'
    assert _question_evidence_profile('What happens when someone misses a punch?')=='consequence'
    assert _question_evidence_profile('What topics are covered in orientation?')=='list'


def test_event_based_when_has_high_answer_cue():
    assert _answerability_cue_bonus('When is the award given?', 'Award will be given after the results are announced.') >= .70
    assert _answerability_cue_bonus('When are awards presented?', 'Recipients are acknowledged during afternoon briefings.') >= .70


def test_explicit_exception_is_yes_not_no():
    source=passage('Qualification criteria: No absences excluding planned vacation leave with pay. No tardiness. Perfect required overtime attendance.',title='Recognition Rules')
    out=_explicit_exception_yes_no('Can an employee still qualify if they take planned vacation leave with pay?', [source])
    assert out and out[0].startswith('YES,') and 'excluding planned vacation leave with pay' in out[0]


def test_exception_not_invented_without_negated_criterion():
    source=passage('Our handbook includes examples excluding planned vacation leave with pay from this document.',title='Handbook')
    assert _explicit_exception_yes_no('Can an employee qualify if they take planned vacation leave with pay?', [source]) is None


def test_exception_cannot_cross_company_docs():
    source=passage('No absences excluding planned vacation leave with pay.',title='Recognition Rules',scope=2)
    other=passage('No tardiness allowed.',title='Leave Rules',scope=1)
    # Extraction caller is tenant filtered, so prove no cross-document
    # antecedent can synthesize a nonexistent exception.
    assert _explicit_exception_yes_no('Can an employee qualify if they take unpaid leave?', [source,other]) is None


def test_complete_labelled_time_schedule_rows():
    doc=passage('Regular break schedules:\nMorning Break 10:00 - 10:15 a.m.\n'
      'Lunch Break 11:30 - 12:30 p.m.\nAfternoon Break 3:00 - 3:15 p.m.\n'
      'Dinner Break 7:00 - 7:45 p.m.\nLate Evening Break 10:00 - 10:15 p.m.\n'
      'The manager may approve other periods.',title='Daily Working Time')
    ans,meta=_grounded_extractive_answer('What are the regular break schedules during the workday?', [doc],max_items=6,max_chars=1800)
    assert meta['decision']=='accepted-complete-timetable' and ans.count('Break')==5
    assert 'Dinner Break' in ans and 'Lunch Break' in ans


def test_dont_mix_unrelated_source_suggestions():
    a=passage('Employees are eligible for a monthly merit increase after one year of continuous service. '
              'This merit increase takes effect in July.', title='Merit',key='policy:5',rank=.9)
    b=passage('After 8 hours overtime, earn 0.50 leave credit. These workers are entitled to a leave credit.',title='Overtime',key='policy:6',rank=.7)
    ans,meta=_grounded_extractive_answer('Who is entitled to a merit increase and when does it take effect?', [a,b],max_items=6,max_chars=1800)
    assert 'merit increase' in ans and 'overtime' not in ans


def test_purpose_uses_actual_document_not_other_doc():
    a=passage('This program aims to improve employee skills and foster professional development. '
       'It supports training and productivity.',title='Skills Policy',key='policy:1')
    b=passage('This awards program promotes office attendance and punctuality.',title='Attendance Recognition',key='policy:2')
    ans,_=_grounded_extractive_answer('What is the purpose of the employee skills program?', [a,b],max_items=5,max_chars=1800)
    assert 'skills' in ans and 'punctuality' not in ans


def test_when_and_when_requires_both_dates_from_one_authorized_document():
    doc=passage('The midyear bonus is paid no later than June 30. The year-end bonus is paid by December 15.',
                title='Bonus Policy')
    ans,meta=_grounded_extractive_answer('When is the midyear bonus paid, and when is the year-end bonus paid?',
                  [doc],max_items=6,max_chars=1800)
    assert 'June 30' in ans and 'December 15' in ans, (ans,meta)


def test_when_and_when_with_missing_second_date_must_abstain():
    doc=passage('The midyear bonus is paid no later than June 30. The year-end bonus is reviewed annually.',title='Bonus Policy')
    ans,meta=_grounded_extractive_answer('When is the midyear bonus paid, and when is the year-end bonus paid?',
                  [doc],max_items=6,max_chars=1800)
    assert not ans and meta['decision']=='temporal-compound-coverage-incomplete'


def test_eligibility_and_effective_date_in_same_policy():
    doc=passage('Employees with at least one year are entitled to a merit increase. The merit increase is effective July every year.',title='Merit Increase')
    ans,meta=_grounded_extractive_answer('Who is entitled to the merit increase, and when does it take effect?',
            [doc],max_items=6,max_chars=1800)
    assert 'one year' in ans and 'July' in ans, (ans,meta)


def test_threshold_rejects_nonnumeric_award_preamble():
    doc=passage('The award program recognizes performance and positive attitudes, but states no qualifying score.',title='Evaluation')
    ans,meta=_grounded_extractive_answer('What grade must an employee obtain to qualify for the award?', [doc],max_items=6,max_chars=1800)
    assert not ans and meta.get('decision') in {'numeric-threshold-not-supported', 'no-candidates','no-selected-evidence'}
