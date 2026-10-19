"""Groq/local/hybrid .env routing without touching company data or real network."""
from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest
from pydantic import SecretStr, ValidationError

from config.chat_assistant_settings import ChatAssistantSettings
from modules.smart_ai.groq_llm import GroqClient
from modules.smart_ai.portal_ai import SmartPortalAssistant, KnowledgeDocument, RetrievedDocument
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from services.runtime_connection_service import (
    RuntimeServiceResponseError, RuntimeServiceUnavailableError,
    classify_runtime_connection_issue,
)
from modules.smart_ai import portal_ai


def test_simple_mode_setting_is_validated(monkeypatch):
    monkeypatch.delenv('SMART_AI_LLM_MODE', raising=False)
    assert ChatAssistantSettings(_env_file=None).llm_mode == 'local'
    for mode in ('local', 'groq', 'hybrid'):
        monkeypatch.setenv('SMART_AI_LLM_MODE', mode)
        assert ChatAssistantSettings(_env_file=None).llm_mode == mode
    monkeypatch.setenv('SMART_AI_LLM_MODE', 'cloudandlocal')
    with pytest.raises(ValidationError):
        ChatAssistantSettings(_env_file=None)


def test_groq_secrets_are_excluded_from_settings_repr(monkeypatch):
    monkeypatch.setenv('SMART_AI_GROQ_API_KEY', 'secret-value-for-test')
    settings = ChatAssistantSettings(_env_file=None)
    assert settings.groq_api_key.get_secret_value() == 'secret-value-for-test'
    assert 'secret-value-for-test' not in repr(settings)


def test_groq_client_without_key_does_not_make_network_call(monkeypatch):
    from modules.smart_ai import groq_llm
    client = GroqClient()
    client.settings = SimpleNamespace(groq_api_key=SecretStr(''), groq_model='qwen/qwen3.8-27b')
    monkeypatch.setattr(groq_llm.request, 'urlopen', lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError('no network')))
    with pytest.raises(RuntimeServiceUnavailableError):
        client.generate('private evidence that should not be sent')


def test_groq_client_success_uses_official_endpoint_and_no_unsafe_logs(monkeypatch):
    import json
    from modules.smart_ai import groq_llm
    client = GroqClient()
    client.settings = SimpleNamespace(
        groq_api_key=SecretStr('TEST-PRIVATE-KEY'), groq_model='qwen/qwen3.8-27b',
        groq_timeout_seconds=6, standard_max_tokens=320, quality_max_tokens=480,
        temperature=0.0,
    )
    def urlopen(req, timeout):
        assert req.full_url == 'https://api.groq.com/openai/v1/chat/completions'
        assert timeout == 6
        assert req.headers['Authorization'] == 'Bearer TEST-PRIVATE-KEY'
        payload = json.loads(req.data)
        assert payload['model'] == 'qwen/qwen3.8-27b'
        assert payload['messages'][1]['content'] == 'authorized evidence only'
        assert payload['max_completion_tokens'] == 320
        return io.BytesIO(b'{"choices":[{"message":{"content":"Verified local policy answer."}}]}')
    monkeypatch.setattr(groq_llm.request, 'urlopen', urlopen)
    assert client.generate('authorized evidence only') == 'Verified local policy answer.'


def test_groq_http_error_does_not_leak_remote_error_body(monkeypatch):
    from modules.smart_ai import groq_llm
    client = GroqClient()
    client.settings = SimpleNamespace(
        groq_api_key=SecretStr('TEST-PRIVATE-KEY'), groq_model='qwen/qwen3.8-27b',
        groq_timeout_seconds=5, standard_max_tokens=320, temperature=0,
    )
    def failure(*_a, **_kw):
        raise HTTPError(groq_llm.GROQ_CHAT_URL, 429, 'rate limited', {}, io.BytesIO(b'secret-value-and-private-evidence'))
    monkeypatch.setattr(groq_llm.request, 'urlopen', failure)
    with pytest.raises(RuntimeServiceResponseError) as info:
        client.generate('private evidence')
    assert info.value.status_code == 429
    assert 'secret-value-and-private-evidence' not in str(info.value)
    assert 'TEST-PRIVATE-KEY' not in str(info.value)
    issue = classify_runtime_connection_issue(info.value, service_hint='groq')
    assert issue.code == 'groq_request_failed'


def test_preflight_only_checks_selected_providers():
    assistant = SmartPortalAssistant.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(enabled=True, llm_mode='groq')
    assistant.groq = SimpleNamespace(check_available=Mock())
    assistant.ollama = SimpleNamespace(check_available=Mock())
    assert assistant.preflight_connection_issue(role_scope='admin') is None
    assistant.groq.check_available.assert_called_once()
    assistant.ollama.check_available.assert_not_called()
    assistant.settings.llm_mode = 'local'
    assert assistant.preflight_connection_issue(role_scope='admin') is None
    assistant.ollama.check_available.assert_called_once()


def _fake_assistant(monkeypatch, mode, *, groq_result=None, groq_error=None):
    from modules.smart_ai import portal_ai
    assistant = SmartPortalAssistant.__new__(SmartPortalAssistant)
    assistant.session = None
    assistant.settings = SimpleNamespace(
        enabled=True, llm_mode=mode,
        groq_model='qwen/qwen3.8-27b', groq_timeout_seconds=5,
        terminal_debug_enabled=False, terminal_debug_log_enabled=False,
        history_messages=4, min_question_tokens=3, quality_min_question_tokens=14,
        quality_min_retrieved_documents=3, context_window=4096,
        evidence_excerpt_chars=650, ollama_timeout_retry_enabled=False,
        ollama_timeout_seconds=180, ollama_model='qwen2.5:7b',
        quality_ollama_model='qwen2.5:7b', standard_max_tokens=320,
        grounded_extractive_fast_path_enabled=False,
    )
    doc = KnowledgeDocument('id', 'Long service awards are listed in published company HR policy.', 'Service Policy',
        'policy', 1, 'shared', {'filename':'Service Policy.docx','policy_id':1, 'file_key':'servicepolicy'})
    assistant.retriever = SimpleNamespace(search=lambda *_a, **_k: [RetrievedDocument(doc, .9)])
    local = Mock(return_value='Answer from local policy.')
    cloud = Mock(return_value=groq_result)
    if groq_error is not None:
        cloud.side_effect = groq_error
    assistant.ollama = SimpleNamespace(generate=local)
    assistant.groq = SimpleNamespace(generate=cloud)
    monkeypatch.setattr(portal_ai.PortalKnowledgeBuilder,'build',lambda *_a, **_k: [])
    def run():
        return assistant.enhance(
            current_user=SimpleNamespace(company_id=1,user_id=1), role_scope='admin',
            question='Explain the published long service award company policy and coverage.',
            history=[], deterministic_response=HRAssistantResponse(answer='No direct verified answer.',intent='policy')
        )
    return run, cloud, local


def test_local_never_calls_groq(monkeypatch):
    run, cloud, local = _fake_assistant(monkeypatch,'local')
    r=run()
    assert local.called
    cloud.assert_not_called()
    assert 'local policy' in r.answer


def test_groq_only_never_calls_ollama_on_success(monkeypatch):
    run, cloud, local = _fake_assistant(monkeypatch,'groq',groq_result='Answer from cloud policy.')
    r=run()
    assert cloud.called
    local.assert_not_called()
    assert 'cloud policy' in r.answer


def test_groq_only_never_falls_back_to_ollama_on_error(monkeypatch):
    run, cloud, local = _fake_assistant(monkeypatch,'groq',groq_error=RuntimeServiceUnavailableError('groq'))
    r=run()
    assert cloud.called
    local.assert_not_called()
    assert r.runtime_warning_code == 'groq_unavailable'


def test_hybrid_primary_cloud_when_available(monkeypatch):
    run, cloud, local = _fake_assistant(monkeypatch,'hybrid',groq_result='Answer from cloud policy.')
    r=run()
    assert cloud.called
    local.assert_not_called()
    assert 'cloud policy' in r.answer


def test_hybrid_ollama_only_after_cloud_failure(monkeypatch):
    run, cloud, local = _fake_assistant(monkeypatch,'hybrid',groq_error=RuntimeServiceResponseError('groq', status_code=429))
    r=run()
    assert cloud.called and local.called
    assert 'local policy' in r.answer


def test_preflight_hybrid_missing_groq_key_uses_local(monkeypatch):
    assistant = SmartPortalAssistant.__new__(SmartPortalAssistant)
    assistant.settings = SimpleNamespace(enabled=True, llm_mode='hybrid')
    assistant.groq = SimpleNamespace(check_available=Mock(side_effect=RuntimeServiceUnavailableError('groq')))
    assistant.ollama = SimpleNamespace(check_available=Mock())
    assert assistant.preflight_connection_issue(role_scope='employee') is None
    assistant.ollama.check_available.assert_called_once()
