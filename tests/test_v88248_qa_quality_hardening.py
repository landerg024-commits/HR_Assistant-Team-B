"""v8.8.248: generic QA failure-mode tests using synthetic, tenant-scoped sources.

These aren't reference QA answers and don't become production answer keys.
"""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, SmartPortalAssistant,
    _answerability_cue_bonus, _grounded_extractive_answer,
)
from config.chat_assistant_settings import ChatAssistantSettings


def source(title, text, section='Rule', company=18, role='shared', idx=1):
    document = KnowledgeDocument(
        f'{company}:policy:{idx}', text, title, 'policy', company, role,
        {'title': title, 'filename': title + '.docx', 'policy_id': idx,
         'section': section, 'chunk_index': 1, 'total_chunks': 1,
         'file_key': f'policy:{idx}:document:{idx}'},
    )
    return RetrievedDocument(document, .041)


def extract(question, rows, max_items=6):
    return _grounded_extractive_answer(
        question, rows, max_items=max_items, max_chars=1800,
    )


def test_parenthetical_numerals_are_real_duration_evidence():
    q = 'How long may a personal telephone call last?'
    assert _answerability_cue_bonus(q, 'Personal calls may not exceed five (5) minutes.') == 1
    assert _answerability_cue_bonus(q, 'Employees can request assistance with calls.') == 0


def test_relative_award_deadline_is_temporal_evidence():
    q = 'When is the service recognition given?'
    assert _answerability_cue_bonus(q, 'The recognition is given after the results are announced.') >= .7
    assert _answerability_cue_bonus(q, 'Service recognition is important to the company.') < .7


def test_fact_cue_candidate_can_win_over_nonanswer_heading():
    q = 'When is the service recognition given?'
    a = source('Service Recognition', 'The service recognition award is given to good employees.', idx=10)
    b = source('Service Recognition', 'Service recognition shall be distributed after the results are announced.', idx=11)
    out = SmartPortalAssistant._retrieval_relevance_snapshot(
        query=q, retrieved=[a,b], require_answer_cue=True, min_answer_cue=.70,
    )
    assert out['accepted'] is True
    assert out['source'] == 'Service Recognition.docx'
    assert out['answer_cue'] >= .70


def test_unrelated_duration_evidence_cannot_pass_relevance_guard():
    q = 'How long may a personal telephone call last?'
    a = source('Office Policy', 'The company hosts a five (5) minute coffee break.', idx=12)
    result = SmartPortalAssistant._retrieval_relevance_snapshot(
        query=q, retrieved=[a], require_answer_cue=True, min_answer_cue=.70,
    )
    assert not result['accepted']


def test_eligibility_extract_must_state_condition_not_program_purpose():
    q = 'Who is eligible for the Talent Recognition Award?'
    a = source('Talent Recognition Award',
               'Our talent recognition award program aims to motivate qualified employees. '
               'The company makes announcements for recognized staff members.', idx=20)
    answer, meta = extract(q, [a])
    assert not answer
    assert meta['decision'] == 'eligibility-conditions-not-proven'


def test_enumerated_eligibility_cannot_silently_drop_sibling_items():
    q = 'Who is eligible for the Talent Recognition Award?'
    a = source('Talent Recognition Award',
               'Eligibility is limited to the following:\n'
               '1. Employees who completed the Talent Recognition Award training.\n'
               '2. Employees who received an external certificate.\n'
               '3. Employees who obtained the top qualifying examination score.',
               section='Coverage and Eligibility', idx=21)
    answer, meta = extract(q, [a], max_items=1)
    assert not answer
    assert meta['decision'] in {'enumerated-criteria-incomplete', 'source-subsection-target-missing'}


def test_unrelated_synthetic_tenant_document_not_promoted():
    q = 'When is the service recognition given?'
    a = source('Finance Policy', 'After the results are announced, the payment is released.', company=19, idx=31)
    out = SmartPortalAssistant._retrieval_relevance_snapshot(
        query=q, retrieved=[a], require_answer_cue=True, min_answer_cue=.70)
    assert not out['accepted']


def test_ollama_primary_timeout_unchanged_bounded_fallback_slightly_longer():
    settings = ChatAssistantSettings(_env_file=None)
    assert settings.ollama_timeout_seconds == 180
    assert settings.grounded_direct_fact_ollama_timeout_seconds == 30


def test_generated_claim_citation_tracks_supported_policy_not_first_result():
    a = source('Annual Leave',
               'Annual leave requests require approval at least five working days in advance.', idx=40)
    b = source('Merit Increase',
               'A merit increase of zero percent is possible when an employee receives a poor performance appraisal.', idx=41)
    answer = 'An employee may receive a zero percent merit increase after a poor performance appraisal.'
    selected = SmartPortalAssistant._answer_supported_policy_source(
        answer=answer,
        query='Can an employee receive a zero percent merit increase?',
        retrieved=[a, b], fallback_sources=[],
    )
    assert selected and selected[0].filename == 'Merit Increase.docx'
    assert selected[0].policy_id == 41


def test_generated_claim_does_not_invent_a_source_if_none_supports_it():
    source_doc = source('Office Keys', 'The building entrance closes at sunset.', idx=42)
    selected = SmartPortalAssistant._answer_supported_policy_source(
        answer='The annual bonus has a forty percent merit adjustment.',
        query='What is the annual bonus merit adjustment?',
        retrieved=[source_doc], fallback_sources=[],
    )
    assert selected == []


def test_direct_fact_evidence_budget_preserves_source_labels_and_top_order(monkeypatch):
    assistant = SmartPortalAssistant(None)
    monkeypatch.setattr(assistant.settings, 'evidence_excerpt_chars', 1200)
    docs = [source('Asset Rule', f'Employees must sign the authorized asset register. {"asset " * 180}', idx=i)
            for i in range(10, 15)]
    normal = assistant._build_evidence_context(query='Who signs the register?', retrieved=docs)
    bounded = assistant._build_evidence_context(
        query='Who signs the register?', retrieved=docs, excerpt_chars=540, max_documents=4,
    )
    assert len(bounded) < len(normal)
    assert '[Evidence 1 | Source: Asset Rule.docx' in bounded
    assert '[Evidence 5 |' not in bounded


def test_temporal_briefing_event_counts_without_numeric_date():
    q = 'When and where is recognition given?'
    assert _answerability_cue_bonus(q, 'Recognition is presented during the afternoon briefing.') >= .70
    assert _answerability_cue_bonus(q, 'Recognition motivates employees.') < .70


def test_awol_and_disciplinary_consequences_are_factual_cues():
    q = 'What happens if the employee does not report an absence?'
    assert _answerability_cue_bonus(q, 'It will be treated as AWOL.') == 1.0
    assert _answerability_cue_bonus(q, 'The employee is subject to disciplinary action.') == 1.0
