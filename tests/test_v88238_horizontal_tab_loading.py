"""UI-only horizontal-tab loading coverage; no HR or answer logic changes."""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "ui/components/loading_transition.py").read_text(encoding="utf-8")


def test_native_and_project_owned_horizontal_tabs_use_scoped_overlay():
    assert 'target.closest(\'[data-testid="stTabs"] button[role="tab"]\')' in SOURCE
    assert 'beginTab(nativeRoot, nativeBar, nativeTab, "native")' in SOURCE
    assert 'beginTab(segmentRoot, segmentBar, segment, "segmented")' in SOURCE
    assert 'closest?.(\'[class*="_active_tab"]\')' in SOURCE
    assert 'const tabOverlayId = "ai-hr-horizontal-tab-loading"' in SOURCE
    assert 'const top = bar.bottom + 5' in SOURCE
    assert 'if (tabPending) return;' in SOURCE  # no whole-workspace flicker for tabs
    assert 'host.setTimeout(showTab, 125)' in SOURCE
    assert 'host.setTimeout(hideTab, 10000)' in SOURCE


def test_no_chat_and_application_logic_change():
    assert 'app_version: str = "0.8.8.238"' in (ROOT / 'config/settings.py').read_text()
    assert 'APP_VERSION=0.8.8.238' in (ROOT / '.env.example').read_text()
    for term in ('SessionFactory', 'Qdrant', 'Groq', 'Ollama', 'expected_answer', 'QA_Session'):
        assert term not in SOURCE
    assert 'data-testid="stSidebar"' in SOURCE
    assert 'signal_page_ready()' in (ROOT / 'ui/layouts/user_layout.py').read_text()
    assert 'signal_page_ready()' in (ROOT / 'ui/layouts/admin_layout.py').read_text()


def test_node_syntax_and_dom_behavior(tmp_path):
    assert shutil.which("node"), "Node.js required for UI controller simulation"
    tree = ast.parse(SOURCE)
    js = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_LOADING_TRANSITION_SCRIPT"
                for target in node.targets)
    ).replace('<script>', '').replace('</script>', '')
    js_path = tmp_path / 'loading.js'
    js_path.write_text(js, encoding='utf-8')
    for command in (
        ['node', '--check', str(js_path)],
        ['node', str(ROOT / 'tests/_v88238_horizontal_tabs_dom_sim.js'), str(js_path)],
    ):
        proc = subprocess.run(command, capture_output=True, text=True, timeout=12)
        assert proc.returncode == 0, proc.stderr or proc.stdout
