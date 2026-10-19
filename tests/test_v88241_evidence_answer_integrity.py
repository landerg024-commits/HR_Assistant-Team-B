"""Generic adversarial routing, evidence and diagnostic behavior (no QA answer keys)."""
from __future__ import annotations
from pathlib import Path

from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, SmartPortalAssistant,
    _record_intent_matches_request, _grounded_extractive_answer,
    _passage_diagnostic, _record_answer_relevance,
    UNDETERMINED_ANSWER,
)


def src(document_id, content, *, section='Chapter Three', company=7, role='shared', pid=10):
    return KnowledgeDocument(
        document_id=document_id, text=content, title='Training Handbook',
        source_type='policy', company_id=company, role_scope=role,
        metadata={'policy_id': pid, 'filename': 'training_handbook.docx',
                  'file_key': 'training_handbook', 'section': section,
                  'version': '1.0', 'chunk_index': 1},
    )


def test_record_family_needs_entity_request_not_incidental_violation_words():
    assert not _record_intent_matches_request(
        'What happens when a worker breaches the inventory storage rules?', 'policy_violation')
    assert not _record_intent_matches_request(
        'Which actions violate the break period instructions?', 'policy_violation')
    assert not _record_intent_matches_request(
        'What consequence applies to unauthorized use of an office item?', 'policy_violation')
    assert _record_intent_matches_request('List active violation codes', 'policy_violation')
    assert _record_intent_matches_request('What severity does code QA-V009 have?', 'policy_violation')
    assert _record_intent_matches_request('Show my disciplinary cases', 'disciplinary_records')
    assert not _record_intent_matches_request('What is the purpose of the company bonus plan?', 'employee_profile')
    assert not _record_intent_matches_request('Who qualifies for a certification program?', 'employee_lookup')
    assert _record_intent_matches_request('Show record for employee number 999', 'employee_profile')


def test_bilingual_safe_source_recovery_is_same_company_file_role_only():
    seed = RetrievedDocument(src('seed', 'This introduction covers employee growth.'), .06)
    good = src('good', 'All engineers shall attend a three-day planning seminar.', section='Eligibility')
    alien = src('alien', 'All engineers shall attend a four-day event.', company=88)
    forbidden = src('private', 'All engineers shall attend a five-day event.', role='admin')
    unrelated = KnowledgeDocument('other', 'All engineers shall attend a ten-day event.',
                                  'Elsewhere', 'policy', 7, 'shared',
                                  {'file_key': 'other', 'filename':'other.docx'})
    recovered = SmartPortalAssistant._recover_authorized_policy_evidence(
        query='How many days is the engineers training seminar?',
        retrieved=[seed], documents=[seed.document, good, alien, forbidden, unrelated],
        company_id=7, role_scope='employee',
    )
    ids = {item.document.document_id for item in recovered}
    assert 'alien' not in ids and 'private' not in ids and 'other' not in ids
    assert 'seed' in ids


def test_verifiable_policy_sources_only_when_metadata_has_real_policy_id():
    legitimate = src('a', 'The training workshop is required.')
    counterfeit = KnowledgeDocument('b','Unattributed text','Internet','portal_help',7,'shared',{})
    output = SmartPortalAssistant._retrieved_policy_sources([
        RetrievedDocument(legitimate,.1), RetrievedDocument(counterfeit,.09)])
    assert len(output) == 1
    assert output[0].policy_id == 10
    assert output[0].filename == 'training_handbook.docx'


def test_bare_heading_is_not_a_complete_list_answer():
    item = src('a', 'The following training categories apply:\n- Program introduction.',
               section='Staff Classes')
    result, meta = _grounded_extractive_answer(
        'List training categories for employees', [RetrievedDocument(item,.1)],
        max_items=4, max_chars=800)
    assert not result or 'following training categories apply:' not in result.lower()


def test_extractive_numeric_and_clock_answer_type_safety():
    item = src('a', 'Employees have scheduled breaks as arranged by the supervisor.')
    answer, meta = _grounded_extractive_answer(
        'What times are breaks scheduled?', [RetrievedDocument(item,.1)],
        max_items=4, max_chars=800)
    assert not answer
    assert meta.get('decision') in {'no-selected-evidence','missing-requested-time-evidence','source-subsection-target-missing'}


def test_yes_no_semantic_contradiction_abstains_instead_of_false_binary():
    assert SmartPortalAssistant._normalize_yes_no_answer(
        'NO. Workers can still participate under the approved exception.') == UNDETERMINED_ANSWER
    assert SmartPortalAssistant._normalize_yes_no_answer(
        'NO. The application explicitly excludes the activity from disqualification.') == UNDETERMINED_ANSWER
    assert SmartPortalAssistant._normalize_yes_no_answer(
        'YES. Members can apply after approval.').startswith('**YES.')
    assert SmartPortalAssistant._normalize_yes_no_answer(
        'NO. The rule prohibits this for visitors.').startswith('**NO.')


def test_passage_metrics_do_not_confuse_heading_and_body():
    doc=src('a','Approved equipment must be registered to the site office.',section='Safety and Registration')
    m=_passage_diagnostic('What equipment needs registration?',doc)
    assert m['body_overlap'] >= 1
    assert m['section'] == 'Safety and Registration'
    assert 0 <= m['body_coverage'] <= 1


def test_benchmark_mode_and_file_override_are_only_evaluation_options():
    contents=(Path(__file__).parents[1] / 'scripts' / 'rag_ab_benchmark.py').read_text(encoding='utf-8')
    assert '--reranker' in contents
    assert '--source-map' in contents
    assert 'best_passage_body_coverage=' in contents
    assert 'SMART_AI_QDRANT_DIR' in contents
