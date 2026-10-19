"""General UI transition coverage, without changing the HR or AI engine."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'ui/components/loading_transition.py').read_text(encoding='utf-8')


def test_detects_streamlit_partial_main_content_loss():
    assert 'const mainSnapshot = () =>' in SOURCE
    assert 'const evaluateWorkspace = () =>' in SOURCE
    assert 'awaitingGap = true;' in SOURCE
    assert 'new MutationObserver(onDomChange)' in SOURCE
    assert 'kind === "content-gap"' in SOURCE
    assert 'setTimeout(show, 70)' in SOURCE
    assert 'setTimeout(show, 220)' in SOURCE
    assert 'setTimeout(hide, 10000)' in SOURCE
    assert 'prefers-reduced-motion: reduce' in SOURCE


def test_covers_more_navigation_without_blocking_forms():
    assert "quick_action_button_" in SOURCE
    assert "st-key-open_notification_" in SOURCE
    assert "'[data-testid=\"stSidebar\"] button'" in SOURCE
    assert 'stFormSubmitButton' not in SOURCE
    assert 'aria-hidden' in SOURCE
    assert 'old?.dispose?.();' in SOURCE


def test_ui_only_version_and_same_base():
    assert 'app_version: str = "0.8.8.237"' in (ROOT / 'config/settings.py').read_text(encoding='utf-8')
    assert 'APP_VERSION=0.8.8.237' in (ROOT / '.env.example').read_text(encoding='utf-8')
    assert 'signal_page_ready()' in (ROOT / 'ui/layouts/admin_layout.py').read_text(encoding='utf-8')
    assert 'signal_page_ready()' in (ROOT / 'ui/layouts/user_layout.py').read_text(encoding='utf-8')
    for forbidden in ('SessionFactory', 'Groq', 'Ollama', 'Qdrant', 'QA_Session', 'expected_answer'):
        assert forbidden not in SOURCE


def test_javascript_syntax_and_browser_interactions(tmp_path):
    tree = ast.parse(SOURCE)
    js = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == '_LOADING_TRANSITION_SCRIPT'
            for target in node.targets
        ):
            js = ast.literal_eval(node.value).replace('<script>', '').replace('</script>', '')
            break
    assert js
    js_path = tmp_path / 'loader.js'
    js_path.write_text(js, encoding='utf-8')
    check = subprocess.run(['node', '--check', str(js_path)], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    test = subprocess.run(
        ['node', str(ROOT / 'tests/_v88237_loading_dom_sim.js'), str(js_path)],
        capture_output=True, text=True,
    )
    assert test.returncode == 0, test.stderr
    assert 'PASS:' in test.stdout
