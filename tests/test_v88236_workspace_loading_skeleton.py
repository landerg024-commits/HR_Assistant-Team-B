"""v8.8.236 screenshot-reported full workspace/loading bounds regression."""
from pathlib import Path
import subprocess
import ast

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'ui/components/loading_transition.py').read_text(encoding='utf-8')


def test_loader_fills_workspace_without_white_modal():
    assert 'ai-hr-loading-workspace' in SOURCE
    assert 'ai-hr-loading-columns' in SOURCE
    assert 'ai-hr-loading-metrics' in SOURCE
    assert '.ai-hr-loading-card' not in SOURCE
    assert 'background: rgba(247, 249, 252, .97)' not in SOURCE
    assert 'background: #F7F9FC' in SOURCE


def test_geometry_uses_visible_sidebar_and_pinned_header():
    assert 'sidebarRect ? sidebarRect.right : 0' in SOURCE
    assert 'mainRect ? mainRect.left : 0' in SOURCE
    assert 'bannerRect ? bannerRect.bottom + 3 : 0' in SOURCE
    assert 'Math.max(' in SOURCE
    assert 'st-key-hr_global_topbar_shell' in SOURCE


def test_form_submits_not_treated_as_sidebar_navigation():
    assert '''target.closest('[data-testid="stSidebar"] button')''' in SOURCE
    assert "'[data-testid=\"stFormSubmitButton\"] button'" not in SOURCE
    assert 'setTimeout(show, 220)' in SOURCE
    assert 'setTimeout(hide, 10000)' in SOURCE
    assert 'prefers-reduced-motion: reduce' in SOURCE
    assert 'pointer-events: none' in SOURCE


def test_no_hr_ai_changes_and_version():
    for forbidden in ('SessionFactory','Qdrant','Ollama','Groq','QA_Session','expected_answer'):
        assert forbidden not in SOURCE
    assert 'app_version: str = "0.8.8.236"' in (ROOT/'config/settings.py').read_text(encoding='utf-8')
    assert 'APP_VERSION=0.8.8.236' in (ROOT/'.env.example').read_text(encoding='utf-8')
    assert 'signal_page_ready()' in (ROOT/'ui/layouts/admin_layout.py').read_text(encoding='utf-8')
    assert 'signal_page_ready()' in (ROOT/'ui/layouts/user_layout.py').read_text(encoding='utf-8')


def test_javascript_compiles_with_node(tmp_path):
    tree=ast.parse(SOURCE)
    script=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_LOADING_TRANSITION_SCRIPT' for t in node.targets):
            script=ast.literal_eval(node.value)
    assert script
    path=tmp_path/'loader.js'
    path.write_text(script.replace('<script>','').replace('</script>',''),encoding='utf-8')
    result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
