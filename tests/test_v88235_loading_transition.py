"""v8.8.235 — loading feedback without changing HR/RAG behavior."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_both_portals_emit_ready_after_module_render() -> None:
    for rel in ("ui/layouts/admin_layout.py", "ui/layouts/user_layout.py"):
        source = read(rel)
        assert "from ui.components.loading_transition import signal_page_ready" in source
        assert source.rstrip().endswith("signal_page_ready()")


def test_auth_pages_signal_ready_before_return() -> None:
    source = read("app.py")
    for view in (
        "render_forgot_password_layout",
        "render_reset_password_layout",
        "render_login_layout",
        "render_password_change_layout",
    ):
        start = source.index("        " + view + "(")
        end = source.index("        return", start)
        assert "signal_page_ready()" in source[start:end]
    assert "render_admin_layout(settings, current_user)" in source
    assert "render_user_layout(settings, current_user)" in source


def test_loader_uses_debounce_accessibility_and_failsafe() -> None:
    source = read("ui/components/loading_transition.py")
    assert 'setTimeout(show, 220)' in source
    assert 'setTimeout(hide, 10000)' in source
    assert 'aria-live' in source
    assert 'prefers-reduced-motion: reduce' in source
    assert 'root.querySelector' in source
    assert 'data-testid="stSidebar"' in source
    assert 'pointer-events: none' in source
    assert 'doc.body.appendChild(overlay)' in source
    assert 'window.parent.__aiHrLoadingTransitionController?.ready?.();' in source


def test_no_production_answer_or_database_touch() -> None:
    source = read("ui/components/loading_transition.py")
    assert 'from ui.components.browser_bridge import render_browser_bridge' in source
    for forbidden in ("SessionFactory", "Qdrant", "Groq", "Ollama", "SELECT ", "QA_Session", "expected_answer"):
        assert forbidden not in source


def test_theme_keeps_persistent_non_white_background() -> None:
    source = read("ui/theme/theme_loader.py")
    assert "_synchronize_theme_with_browser(" in source
    # Install early in app.py, before potentially slow runtime initialization.
    app = read("app.py")
    assert "install_loading_transition()" in app
    assert app.index("install_loading_transition()") < app.index("initialize_runtime_schema()", app.index("def main("))
    assert 'tokens["background"]' in source
    conf = read(".streamlit/config.toml")
    assert 'backgroundColor = "#F7F9FC"' in conf


def test_only_presentation_and_version_updated() -> None:
    assert 'app_version: str = "0.8.8.235"' in read("config/settings.py")
    assert "APP_VERSION=0.8.8.235" in read(".env.example")
    assert 'fileWatcherType = "none"' in read('.streamlit/config.toml')
