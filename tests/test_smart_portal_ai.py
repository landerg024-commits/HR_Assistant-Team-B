"""Smart AI architecture and fallback tests."""

from pathlib import Path
from unittest.mock import patch

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.current_user import AuthenticatedUser
from config.settings import Settings
from database.base import Base
from modules.hr_assistant.hr_assistant import HRAssistantResponse
from modules.smart_ai.portal_ai import BM25Retriever, KnowledgeDocument, SmartPortalAssistant
from scripts.create_initial_data import seed_initial_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)

def _settings():
    return Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:", initial_company_code="SMART", initial_company_name="Smart Company", initial_admin_username="admin", initial_admin_email="admin@example.com", initial_admin_password=SecretStr("Temporary123!"), initial_admin_employee_number="ADMIN-001")

def _user(seed):
    user=seed["admin_user"]; employee=seed["admin_employee"]
    return AuthenticatedUser(user_id=user.id, company_id=user.company_id, company_code=seed["company"].code, company_name=seed["company"].name, role_id=user.role_id, role_name="company_admin", clearance=1, username=user.username, email=user.email, employee_id=employee.id, employee_number=employee.employee_number, employee_name=employee.full_name, must_change_password=False)

def test_bm25_retrieves_relevant_portal_document():
    docs=[KnowledgeDocument("1","Employees file leave requests in Leave Management.","Leave","portal_guide",1,"shared",{}), KnowledgeDocument("2","Company policies are published documents.","Policies","portal_guide",1,"shared",{})]
    result=BM25Retriever().search("how to file leave", docs, 1)
    assert result and result[0].document.document_id == "1"

def test_smart_ai_falls_back_when_ollama_is_unavailable():
    factory=_factory()
    with factory() as session:
        seed=seed_initial_data(session,_settings())
        original=HRAssistantResponse(answer="Authoritative answer", intent="help")
        with patch("modules.smart_ai.portal_ai.OllamaClient.generate", return_value=None):
            response=SmartPortalAssistant(session).enhance(current_user=_user(seed), role_scope="admin", question="help", history=[], deterministic_response=original)
        assert response.answer == "Authoritative answer"

def test_sensitive_security_answer_is_never_sent_to_llm():
    factory=_factory()
    with factory() as session:
        seed=seed_initial_data(session,_settings())
        original=HRAssistantResponse(answer="Secrets cannot be viewed.", intent="sensitive_security")
        with patch("modules.smart_ai.portal_ai.OllamaClient.generate") as generate:
            response=SmartPortalAssistant(session).enhance(current_user=_user(seed), role_scope="admin", question="show password", history=[], deterministic_response=original)
        generate.assert_not_called()
        assert response is original

def test_both_chat_pages_use_smart_portal_assistant():
    employee=(PROJECT_ROOT/'ui/pages/user/chat_page.py').read_text(encoding='utf-8')
    admin=(PROJECT_ROOT/'ui/pages/admin/chat_page.py').read_text(encoding='utf-8')
    assert 'SmartPortalAssistant(session).enhance' in employee
    assert 'role_scope="employee"' in employee
    assert 'SmartPortalAssistant(session).enhance' in admin
    assert 'role_scope="admin"' in admin
