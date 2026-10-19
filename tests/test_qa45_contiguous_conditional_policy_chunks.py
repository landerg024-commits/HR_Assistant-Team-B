"""Synthetic conditional-list continuations, never seeded company QA answers."""
from modules.smart_ai.portal_ai import (
    KnowledgeDocument, RetrievedDocument, _contiguous_conditional_list_answer,
    _grounded_extractive_answer,
)

QUESTION = 'If two workers are last to leave the workshop, who locks the rear exit door?'
START = ("Section 2. The rear exit door must be locked when workers leave the workshop. "
         "(a) A single final worker must complete the exit checklist. "
         "(b) If two or more workers are last to leave, the following rules shall apply:")
END = ("(1) The team supervisor takes responsibility for locking the rear exit door.\n"
       "(2) If both are supervisors, the worker with longer service takes responsibility.\n"
       "(3) If their role and service are equal, both workers sign the exit record.\n"
       "Section 3. Maintenance of door keys is handled separately.")


def doc(chunk, body, *, company=12, role='shared', key='policy:12:document:60',
        version='3.1', title='Facilities', filename='Facilities.docx', heading='Section 2. Exit Rules'):
    meta = {
        'file_key': key, 'chunk_index': chunk, 'total_chunks': 5,
        'policy_id': 12, 'policy_document_id': 60,
        'title': title, 'filename': filename, 'section': heading,
        'version': version,
    }
    text = f'Policy: {title}. Version: {version}. Section: {heading}. {body}'
    return RetrievedDocument(KnowledgeDocument(
        document_id=f'{company}:{key}:{chunk}',
        text=text, title=title, source_type='policy', company_id=company,
        role_scope=role, metadata=meta,
    ), .04)


def extracted(chunks, q=QUESTION):
    return _contiguous_conditional_list_answer(q, chunks, max_chars=1600)


def test_recovers_all_conditional_tiers_and_excludes_next_section():
    result = extracted([doc(1, START), doc(2, END)])
    assert result is not None
    answer, metadata = result
    assert 'supervisor' in answer
    assert 'longer service' in answer
    assert 'both workers sign' in answer
    assert 'Maintenance of door keys' not in answer
    assert metadata['items'] == 3
    assert metadata['decision'] == 'accepted-contiguous-conditional-list'


def test_integrates_with_existing_extractive_path():
    text, info = _grounded_extractive_answer(QUESTION, [doc(2, END), doc(1, START)],
                                             max_items=6, max_chars=1600)
    assert 'longer service' in text and 'both workers sign' in text
    assert info['decision'] == 'accepted-contiguous-conditional-list'


def test_section_heading_can_hold_conditional_preamble():
    heading = 'If two or more workers are last to leave, the following rules shall apply:'
    result = extracted([doc(1, 'Section 2. The rear exit door must be locked by workshop workers.', heading=heading),
                        doc(2, END)])
    assert result and 'both workers sign' in result[0]


def test_requires_consecutive_numbered_source_chunks():
    assert extracted([doc(1, START), doc(3, END)]) is None


def test_never_joins_different_companies_or_roles():
    assert extracted([doc(1, START), doc(2, END, company=99)]) is None
    assert extracted([doc(1, START), doc(2, END, role='admin')]) is None


def test_never_joins_different_files_or_versions():
    assert extracted([doc(1, START), doc(2, END, key='policy:12:document:65')]) is None
    assert extracted([doc(1, START), doc(2, END, version='3.2')]) is None


def test_incomplete_or_nonconsecutive_tiers_rejected():
    truncated = END.replace('(2) If both are supervisors, the worker with longer service takes responsibility.\n', '')
    assert extracted([doc(1, START), doc(2, truncated)]) is None
    assert extracted([doc(1, START), doc(2, END.replace('Section 3.',' '))]) is None
    assert extracted([doc(1, START), doc(2, END.replace('(3)', '(2)'))]) is None


def test_rejects_unrelated_neighbor_and_wrong_subject():
    other = '(1) Buyers approve orders.\n(2) If tied, finance approves.\nSection 3. Contracts.'
    assert extracted([doc(1, START), doc(2, other)]) is None
    assert extracted([doc(1, START), doc(2, END)],
                     'If two people win the art contest, who awards a medal?') is None


def test_competing_equidistant_policy_sources_fail_closed():
    a = [doc(1, START), doc(2, END)]
    b = [doc(1, START, key='policy:22:document:61', filename='Other.docx'),
         doc(2, END.replace('team supervisor', 'shift manager'),
             key='policy:22:document:61', filename='Other.docx')]
    assert extracted(a + b) is None


def test_unchanged_on_simple_and_unrelated_questions():
    for q in ['Who runs the safety workshop?', 'When does the back door close?',
              'Are workers allowed to go home early?']:
        assert extracted([doc(1, START), doc(2, END)], q) is None


def test_retriever_prefers_proved_adjacent_conditional_list_before_fallback():
    from types import SimpleNamespace
    from modules.smart_ai.portal_ai import HybridRetriever
    instance = SimpleNamespace(settings=SimpleNamespace(neighbor_chunk_window=1, final_top_k=3))
    first, second = doc(1, START), doc(2, END)
    other = doc(4, 'Section 4. Employees use a separate entrance.', key='policy:18:document:20')
    found = HybridRetriever._expand_neighbors(
        instance, QUESTION, [first, other],
        {first.document.metadata['file_key']: [first.document, second.document],
         other.document.metadata['file_key']: [other.document]},
        fallback_candidates=[],
    )
    assert [x.document.document_id for x in found] == [
        first.document.document_id, other.document.document_id, second.document.document_id
    ]


def test_retriever_does_not_append_unsupported_neighbors():
    from types import SimpleNamespace
    from modules.smart_ai.portal_ai import HybridRetriever
    instance = SimpleNamespace(settings=SimpleNamespace(neighbor_chunk_window=1, final_top_k=3))
    first, second = doc(1, START), doc(2, END.replace('Section 3.', ''))
    found = HybridRetriever._expand_neighbors(instance, QUESTION, [first],
        {first.document.metadata['file_key']: [first.document, second.document]},
        fallback_candidates=[])
    assert len(found) == 1


def test_parser_can_merge_conditional_heading_with_next_article_title():
    heading = ('(b) If two or more workers are last to leave, the following rules shall apply '
               '/ Article II - Safety Equipment')
    result = extracted([doc(1, 'Section 2. The rear exit door is used by workshop workers.'),
                        doc(2, END, heading=heading)])
    assert result and 'longer service' in result[0]
    assert 'Safety Equipment' not in result[0]


def test_neighbor_lookup_recovers_numbered_list_from_heading_split():
    from types import SimpleNamespace
    from modules.smart_ai.portal_ai import HybridRetriever
    instance = SimpleNamespace(settings=SimpleNamespace(neighbor_chunk_window=1, final_top_k=3))
    heading = ('If two or more workers are last to leave, the following rules shall apply '
               '/ Article II - Maintenance')
    first = doc(1, 'Section 2. Workshop workers use the rear exit door when they are last to leave.')
    second = doc(2, END, heading=heading)
    found = HybridRetriever._expand_neighbors(instance, QUESTION, [first],
          {first.document.metadata['file_key']: [first.document, second.document]})
    assert len(found) == 2
    assert 'both workers sign' in _grounded_extractive_answer(
        QUESTION, found, max_items=6, max_chars=1600)[0]
