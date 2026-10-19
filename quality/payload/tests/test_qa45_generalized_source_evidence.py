"""Synthetic QA: no production policy text, case IDs, or fixed answer keys."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _verified_multi_condition_sanctions,
    _verified_source_statement_or_examples, _fast_answer_covers_coordinated_when,
    _grounded_extractive_answer,
)


def doc(body, *, section, filename='Safety & Facilities.docx', company=11,
        key='policy:11:document:35', version='2.0', chunk=3, role='shared'):
    meta = {'file_key': key, 'section': section, 'filename': filename,
            'title': filename[:-5], 'version': version,
            'chunk_index': chunk, 'total_chunks': 9}
    return RetrievedDocument(KnowledgeDocument(
        document_id=f'{key}:{chunk}',
        text=f"Policy: {meta['title']}. Version: {version}. Section: {section}. {body}",
        title=meta['title'], source_type='policy', company_id=company,
        role_scope=role, metadata=meta,
    ), .044)


PURPOSE = ('Safety & Facilities\nPolicy Statement\nOur central policy rests on the '
           'importance of secure shared workplaces and safe everyday work. We '
           'invest in practical protection practices, respect individual needs, '
           'and support professional development of every team member.')
NESTED = ('2.0 Purpose\nThe purpose of this separate workflow is to establish '
          'a framework of inspections, maintenance ticket scheduling, and '
          'measuring repairs.\n3.0 Scope\nThese inspections cover storage.')
DEFINITION = ('Definition of Warehouse Safety Violations\n'
              'Warehouse staff must maintain safe handling outside break periods. '
              'Examples of safety violations include blocking fire exits, stacking '
              'hazardous items in walkways, using equipment while unauthorized, '
              'and disabling warning alarms. Every worker must respect emergency exits.')
CONSEQUENCES = '''Section 6. If an access badge is misplaced, the employee must inform their supervisor and pay for replacement.
Section 7. Unauthorized duplication of access badges constitutes serious misconduct and may trigger disciplinary action.
Section 8. Disciplinary Action
Violations of badge custody rules carry the following penalties:
1st Offense: Written Warning
2nd Offense: 1-day Suspension
3rd Offense: 3-day Suspension
Article IV - Staff Parking
This section governs parking allocation separately.'''


def test_named_top_level_policy_statement_takes_precedence_over_nested_purpose():
    q = "What is the purpose of the company's Safety & Facilities policy?"
    result = _verified_source_statement_or_examples(q, [
        doc(NESTED, section='2.0 Purpose / 3.0 Scope', chunk=8),
        doc(PURPOSE, section='Policy Statement', chunk=1)], max_chars=1800)
    assert result
    assert 'safe everyday work' in result[0]
    assert 'ticket scheduling' not in result[0]
    assert result[1]['decision'] == 'accepted-source-policy-statement'


def test_policy_statement_no_improper_policy_topic_replacement():
    q = 'What is the purpose of the company recycling policy?'
    assert _verified_source_statement_or_examples(q, [doc(PURPOSE, section='Policy Statement')], max_chars=1800) is None


def test_definition_examples_extracted_from_matching_section():
    q = 'What activities are considered violations of warehouse safety policy?'
    out = _verified_source_statement_or_examples(q, [
        doc('Disciplinary rules for overtime breaches are reviewed annually.', section='Policy Statement', chunk=1),
        doc(DEFINITION, section='Definition of Warehouse Safety Violations', chunk=2)], max_chars=1800)
    assert out and 'blocking fire exits' in out[0]
    assert 'warning alarms' in out[0]
    assert out[1]['decision'] == 'accepted-source-definition-examples'


def test_definition_guard_on_wrong_subject_and_truncated_example():
    assert _verified_source_statement_or_examples('What activities violate cybersecurity policy?', [
        doc(DEFINITION, section='Definition of Warehouse Safety Violations')], max_chars=1800) is None
    assert _verified_source_statement_or_examples(
        'What activities violate warehouse safety policy?',
        [doc(DEFINITION[:50], section='Definition of Warehouse Safety Violations')], max_chars=1800) is None


def test_full_consequence_including_numbered_sanctions():
    q = 'What happens if a worker misplaces an access badge or makes an unauthorized duplicate?'
    out = _verified_multi_condition_sanctions(q, [doc(CONSEQUENCES, section='Section 6 / Section 7 / Section 8')], max_chars=1800)
    assert out
    assert '1st Offense' in out[0] and '3rd Offense' in out[0]
    assert 'Staff Parking' not in out[0]
    assert out[1]['decision'] == 'accepted-complete-source-sanctions'


def test_consequence_rejects_missing_penalty_tiers_and_separate_sources():
    q = 'What happens if a worker misplaces an access badge or makes an unauthorized duplicate?'
    assert _verified_multi_condition_sanctions(q, [doc(CONSEQUENCES.replace('2nd Offense: 1-day Suspension\n', ''), section='Section 6 / Section 7 / Section 8')], max_chars=1800) is None
    assert _verified_multi_condition_sanctions(q, [doc(CONSEQUENCES.replace('Unauthorized duplication of access badges', 'Parking space abuse'), section='Section 6 / Section 7 / Section 8')], max_chars=1800) is None


def test_consequence_rejects_missing_conditions_even_if_penalties_present():
    q = 'What happens if a worker misplaces an access badge or makes an unauthorized duplicate?'
    assert _verified_multi_condition_sanctions(q, [doc(CONSEQUENCES.replace('If an access badge is misplaced', 'If a delivery is late'), section='Section 6 / Section 7 / Section 8')], max_chars=1800) is None


def test_ambiguous_equal_score_different_companies_rejected():
    q = 'What happens if a worker misplaces an access badge or makes an unauthorized duplicate?'
    assert _verified_multi_condition_sanctions(q, [
        doc(CONSEQUENCES, section='Section 6 / Section 7 / Section 8'),
        doc(CONSEQUENCES, section='Section 6 / Section 7 / Section 8', company=13, key='policy:13:document:88'),
    ], max_chars=1800) is None


def test_multi_facet_effectivity_requires_actor_and_temporal_proof():
    q = 'Who qualifies for the annual allowance, and when does it take effect?'
    assert not _fast_answer_covers_coordinated_when(q, 'Regular employees qualify after one year of service.')
    assert not _fast_answer_covers_coordinated_when(q, 'Employees who qualify get a November bonus for earlier work.')
    assert _fast_answer_covers_coordinated_when(q, 'Regular employees qualify for the annual allowance. It takes effect on July 1.')


def test_non_effective_question_should_not_be_changed():
    assert _fast_answer_covers_coordinated_when('Who is the coordinator?', 'The manager.')


def test_generic_fast_path_integration_for_definition_examples():
    q = 'What activities are considered violations of warehouse safety policy?'
    answer, meta = _grounded_extractive_answer(q, [doc(DEFINITION, section='Definition of Warehouse Safety Violations')], max_items=6, max_chars=1800)
    assert 'warning alarms' in answer
    assert meta['decision'] == 'accepted-source-definition-examples'
