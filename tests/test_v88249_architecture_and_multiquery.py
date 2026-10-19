"""Architecture safeguards, synthetic sources only; no benchmark answer keys."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _grounded_extractive_answer,
    _coordinated_verbatim_facts,
)


def _doc(text, *, company_id=12, source_type='policy', chunk=1, section='Rules'):
    d = KnowledgeDocument(
        f'{company_id}:p:1:chunk:{chunk}', text, 'Skills Seminar', source_type,
        company_id, 'shared', {'filename':'Skills Seminar.docx', 'section': section,
                               'file_key': f'policy:1:document:1',
                               'chunk_index':chunk,'total_chunks':2},
    )
    return RetrievedDocument(d, .04)


def test_same_chunk_who_and_duration_are_returned_verbatim():
    question = 'Who must attend the Skills Seminar, and how long does it usually take?'
    evidence = _doc(
        'Our training program supports the Skills Seminar.\n'
        'All Design Technician I and administrative staff shall undergo the Skills Seminar.\n'
        'The seminar usually takes one day (8 hours).', section='Skills Seminar')
    answer, meta = _grounded_extractive_answer(question,[evidence],max_items=6,max_chars=1200)
    assert 'administrative staff shall undergo' in answer
    assert 'one day (8 hours)' in answer
    assert meta['decision']=='accepted-same-chunk-coordinated-facts'


def test_cross_chunk_fact_splicing_is_not_allowed():
    question = 'Who must attend the Skills Seminar, and how long does it usually take?'
    a=_doc('All Design Technician I and administrative staff shall undergo the Skills Seminar.',section='Skills Seminar',chunk=1)
    b=_doc('The separate manager program takes one day (8 hours).',section='Manager Course',chunk=2)
    assert _coordinated_verbatim_facts(question,[a,b],max_chars=1200) is None


def test_unrelated_duration_in_same_chunk_does_not_pass():
    question = 'Who must attend the Skills Seminar, and how long does it usually take?'
    a=_doc('Staff shall undergo the Skills Seminar. Our unrelated cafeteria break takes eight minutes.',section='Skills Seminar')
    assert _coordinated_verbatim_facts(question,[a],max_chars=1200) is None


def test_compound_title_without_second_question_does_not_split():
    q='Who must attend the Leadership and Workplace Skills Seminar?'
    evidence=_doc('All Design Technician I staff shall undergo the Leadership and Workplace Skills Seminar. The course takes 8 hours.')
    assert _coordinated_verbatim_facts(q,[evidence],max_chars=1200) is None


def test_wrong_source_type_cannot_trigger():
    q='Who must attend the Skills Seminar, and how long does it usually take?'
    e=_doc('All Design Technician I staff shall undergo the Skills Seminar. The course takes 8 hours.',source_type='private_employee')
    assert _coordinated_verbatim_facts(q,[e],max_chars=1200) is None

from config.chat_assistant_settings import ChatAssistantSettings
from modules.smart_ai.portal_ai import _adaptive_subqueries, _merge_adaptive_bm25_candidates


def test_multiquery_only_for_explicit_independent_interrogatives():
    query='Who must attend the Skills and Safety Seminar, and how long does it take?'
    variants=_adaptive_subqueries(query)
    assert len(variants)==2
    assert 'Skills and Safety Seminar' in variants[0]
    assert 'Skills and Safety Seminar' in variants[1]
    assert _adaptive_subqueries('Who is eligible for the Skills and Safety Award?') == []
    assert _adaptive_subqueries('What is the Skills and Safety Seminar policy?') == []


def test_multiquery_disabled_by_default():
    settings=ChatAssistantSettings(_env_file=None)
    assert settings.adaptive_multi_query_enabled is False
    assert settings.ollama_timeout_seconds==180
    assert settings.grounded_direct_fact_ollama_timeout_seconds==30


def test_multiquery_cannot_import_cross_company_or_unselected_chunks():
    q='Who must attend the Skills Seminar, and how long does it take?'
    first=_doc('All staff must attend the Skills Seminar.', company_id=12, chunk=1)
    good=_doc('The Skills Seminar takes one day (8 hours) and all staff must attend.',company_id=12,chunk=2)
    outside=_doc('The Skills Seminar takes two days and all staff must attend.',company_id=13,chunk=5)
    base=[first]
    merged=_merge_adaptive_bm25_candidates(q,base,[[outside,good]],allowed_document_ids={first.document.document_id,good.document.document_id})
    assert {x.document.document_id for x in merged}=={first.document.document_id,good.document.document_id}
    assert all(x.document.company_id==12 for x in merged)


def test_multiquery_cannot_import_unrelated_chunk():
    q='Who must attend the Skills Seminar, and how long does it take?'
    first=_doc('All staff must attend the Skills Seminar.',chunk=1)
    unrelated=_doc('Employees may borrow the office key during the evening.',chunk=4)
    merged=_merge_adaptive_bm25_candidates(q,[first],[[unrelated]],allowed_document_ids={first.document.document_id,unrelated.document.document_id})
    assert len(merged)==1
