"""Static integration tests for Policy Q&A routes."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_admin_policy_route_is_functional() -> None:
    source = _read("ui/layouts/admin_layout.py")

    assert 'elif page == "Policies":' in source
    assert "render_admin_policies_page(current_user)" in source


def test_employee_company_policies_route_is_functional() -> None:
    source = _read("ui/layouts/user_layout.py")

    assert 'current_page == "Company Policies"' in source
    assert "render_employee_policies_page(current_user)" in source


def test_chat_page_uses_policy_assistant() -> None:
    source = _read("ui/pages/user/chat_page.py")

    assert "PolicyAssistant" in source
    assert "company_id=current_user.company_id" in source


def test_policy_feature_flag_is_enabled() -> None:
    source = _read("config/feature_flags.py")

    assert '"policy_qa": True' in source
