"""v8.8.232 regression: direct Streamlit and VS Code runtimes create terminal logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def _run_native(tmp_path, *, extra_env=None, code=None):
    script = code or textwrap.dedent('''
        from scripts import native_terminal_capture as c
        c.DEFAULT_LOG_DIR = __import__("pathlib").Path(__import__("os").environ["UNIT_LOG_DIR"])
        first = c.ensure_native_runtime_capture()
        second = c.ensure_native_runtime_capture()
        assert first is second
        assert first is not None
        import warnings
        import logging
        print("DIRECT STANDARD OUTPUT")
        print("DIRECT ERROR OUTPUT", file=__import__("sys").stderr)
        warnings.warn("DIRECT PYTHON WARNING", RuntimeWarning)
        logging.warning("DIRECT LOGGER WARNING")
        c._atexit_close()
    ''')
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["UNIT_LOG_DIR"] = str(tmp_path)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, env=env, timeout=12)


def test_direct_streamlit_native_tee_captures_stdout_stderr_warnings_and_logging(tmp_path):
    proc = _run_native(tmp_path)
    assert proc.returncode == 0, proc.stderr
    logs = list(tmp_path.glob("Terminal_Session_*.log"))
    assert len(logs) == 1
    log = logs[0].read_text(encoding="utf-8")
    assert "DIRECT STREAMLIT" in log
    for phrase in ("DIRECT STANDARD OUTPUT", "DIRECT ERROR OUTPUT", "DIRECT PYTHON WARNING", "DIRECT LOGGER WARNING"):
        assert phrase in log
    assert "DIRECT STANDARD OUTPUT" in proc.stdout
    assert "DIRECT ERROR OUTPUT" in proc.stderr
    assert "DIRECT LOGGER WARNING" in log


def test_no_duplicate_when_full_wrapper_active(tmp_path):
    proc = _run_native(tmp_path, extra_env={"AI_HR_TERMINAL_CAPTURE_ACTIVE": "1"}, code='''
from scripts import native_terminal_capture as c
assert c.ensure_native_runtime_capture() is None
''')
    assert proc.returncode == 0, proc.stderr
    assert not list(tmp_path.iterdir())


def test_direct_native_logging_opt_out(tmp_path):
    proc = _run_native(tmp_path, extra_env={"AI_HR_NATIVE_RUNTIME_LOG_ENABLED": "false"}, code='''
from scripts import native_terminal_capture as c
assert c.ensure_native_runtime_capture() is None
''')
    assert proc.returncode == 0, proc.stderr
    assert not list(tmp_path.iterdir())


def test_native_captures_parallel_python_threads_without_creating_multiple_logs(tmp_path):
    proc = _run_native(tmp_path, code='''
from scripts import native_terminal_capture as c
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
c.DEFAULT_LOG_DIR = Path(os.environ["UNIT_LOG_DIR"])
with ThreadPoolExecutor(max_workers=6) as pool:
    captures = list(pool.map(lambda _: c.ensure_native_runtime_capture(), range(15)))
assert all(x is captures[0] for x in captures)
with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(lambda n: print(f"PARALLEL LINE {n}"), range(15)))
c._atexit_close()
''')
    assert proc.returncode == 0, proc.stderr
    files = list(tmp_path.glob("Terminal_Session_*.log"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    for i in range(15):
        assert f"PARALLEL LINE {i}" in content


def test_vscode_configurations_and_app_entrypoint():
    vscode = ROOT / ".vscode"
    launches = json.loads((vscode / "launch.json").read_text(encoding="utf-8"))
    tasks = json.loads((vscode / "tasks.json").read_text(encoding="utf-8"))
    assert len(launches["configurations"]) == 2
    assert any(c.get("program", "").endswith("run_with_terminal_log.py") for c in launches["configurations"])
    assert any(c.get("module") == "streamlit" for c in launches["configurations"])
    assert any(t.get("group", {}).get("isDefault") for t in tasks["tasks"])
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app.index("ensure_native_runtime_capture()") < app.index("import streamlit as st")
    assert 'fileWatcherType = "none"' in (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")


def test_wrapper_marks_capture_active_in_child():
    from scripts.run_with_terminal_log import capture
    script = (
        "import os; print('marker='+str(os.environ.get('AI_HR_TERMINAL_CAPTURE_ACTIVE')));"
        "print('wrapper stdout visible')"
    )
    code = capture([sys.executable, "-c", script], root=ROOT, log_dir=ROOT / "logs" / "test_v88232_isolated")
    try:
        assert code == 0
        paths = list((ROOT / "logs" / "test_v88232_isolated").glob("Terminal_Session_*.log"))
        assert paths
        content = paths[-1].read_text(encoding="utf-8")
        assert "marker=1" in content
        assert "wrapper stdout visible" in content
    finally:
        for path in (ROOT / "logs" / "test_v88232_isolated").glob("*"):
            path.unlink()
        (ROOT / "logs" / "test_v88232_isolated").rmdir()
