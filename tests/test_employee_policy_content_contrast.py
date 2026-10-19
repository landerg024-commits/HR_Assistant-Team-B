"""Employee policy source-text contrast regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_policy_content_no_longer_uses_st_text() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/policies_page.py"
    ).read_text(encoding="utf-8")

    assert "st.text(policy.content)" not in source
    assert "def _policy_content_html(" in source
    assert "html.escape(" in source
    assert "hr-employee-policy-content" in source
    assert "unsafe_allow_html=True" in source


def test_policy_content_has_stable_keyed_wrapper() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/policies_page.py"
    ).read_text(encoding="utf-8")

    assert 'key=f"employee_policy_content_{policy.id}"' in source
    assert 'key="employee_policy_assistant_answer"' in source
    assert "st.markdown(response.answer)" in source
    assert "st.write(response.answer)" not in source


def test_policy_content_css_forces_light_mode_text() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "EMPLOYEE POLICY CONTENT CONTRAST — v8.8.2",
        1,
    )[1]

    assert ".hr-employee-policy-content" in block
    assert "color: var(--hr-text-primary) !important;" in block
    assert (
        "-webkit-text-fill-color: "
        "var(--hr-text-primary) !important;"
        in block
    )
    assert "line-height: 1.62 !important;" in block
    assert "overflow-wrap: anywhere !important;" in block


def test_policy_st_text_fallback_does_not_target_form_fields() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "EMPLOYEE POLICY CONTENT CONTRAST — v8.8.2",
        1,
    )[1]

    assert '[data-testid="stText"]' in block
    assert '[data-testid="stExpander"] pre' in block
    assert '[data-testid="stTextInput"]' not in block
    assert '[data-testid="stTextArea"]' not in block


def test_runtime_includes_policy_read_only_content() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    function = source.split(
        "const styleReadableContent = () =>",
        1,
    )[1].split(
        "let frameRequested = false;",
        1,
    )[0]

    assert "employee_policy_content_" in function
    assert "employee_policy_assistant_answer" in function
    assert '[data-testid="stText"]' in function
    assert "'p,li,ul,ol,strong,b,em,i,span,pre,'" in function


def test_policy_html_escapes_uploaded_source_text() -> None:
    import importlib.util

    page_path = (
        PROJECT_ROOT
        / "ui/pages/user/policies_page.py"
    )
    source = page_path.read_text(encoding="utf-8")

    assert "html.escape(value or \"\")" in source
    assert '.replace("\\n", "<br>")' in source
