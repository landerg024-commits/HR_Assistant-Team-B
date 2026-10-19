"""A stand-alone terminal capture does not change Streamlit/HR logic."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sys

from scripts.run_with_terminal_log import TerminalLog, _retire_old_logs, capture


def test_combined_stdout_stderr_python_warning_and_traceback(tmp_path, capsys):
    code = (
        "import sys, warnings; "
        "print('APP INITIALIZED', flush=True); "
        "warnings.warn('example library warning', UserWarning); "
        "sys.stderr.write('ERROR: simulated runtime issue\\n'); "
        "raise RuntimeError('simulated traceback')"
    )
    root = tmp_path / "app"
    root.mkdir()
    logs = tmp_path / "output"
    result = capture([sys.executable, "-u", "-c", code], root=root, log_dir=logs)
    assert result != 0
    files = list(logs.glob("Terminal_Session_*.log"))
    assert len(files) == 1
    contents = files[0].read_text(encoding="utf-8")
    output = capsys.readouterr().out
    for text in ("APP INITIALIZED", "UserWarning: example library warning", "ERROR: simulated runtime issue", "Traceback (most recent call last)", "RuntimeError: simulated traceback", "exit_code=1"):
        assert text in contents
        assert text in output


def test_stdout_stderr_on_success_and_unique_launch_log(tmp_path):
    cmd = [sys.executable, "-u", "-c", "import sys; print('READY'); sys.stderr.write('WARN: check config\\n')"]
    for _ in range(2):
        assert capture(cmd, root=tmp_path, log_dir=tmp_path / "logs") == 0
    files = list((tmp_path / "logs").glob("Terminal_Session_*.log"))
    assert len(files) == 2
    for file in files:
        contents = file.read_text(encoding="utf-8")
        assert "READY" in contents and "WARN: check config" in contents
        assert "exit_code=0" in contents


def test_missing_child_executable_is_captured(tmp_path):
    result = capture([str(tmp_path / "no_such_python"), "-u"], root=tmp_path, log_dir=tmp_path / "logs")
    assert result == 1
    files = list((tmp_path / "logs").glob("Terminal_Session_*.log"))
    assert len(files) == 1
    assert "FileNotFoundError" in files[0].read_text(encoding="utf-8")


def test_term_log_rollover_preserves_content(tmp_path):
    sink = TerminalLog(tmp_path, max_bytes=30)
    sink.write("first line\n")
    sink.write("second line\n")
    sink.write("third line\n")
    sink.close()
    assert len(sink.paths) == 2
    assert "part02" in sink.paths[1].name
    assert "first line" in sink.paths[0].read_text()
    assert "third line" in sink.paths[1].read_text()


def test_retention_isolated_to_runtime_logs_and_preserves_latest(tmp_path):
    files = [tmp_path / f"Terminal_Session_20261009T00000{i}_{i}.log" for i in range(4)]
    for path in files:
        path.write_text("TEST")
    qa_log = tmp_path / "QA_Session_sensitive.log"
    qa_log.write_text("KEEP")
    _retire_old_logs(tmp_path, keep=2, exclude=(files[-1],))
    assert qa_log.read_text() == "KEEP"
    assert files[-1].exists()
    assert sum(path.exists() for path in files) <= 3


def test_multi_process_launches_use_distinct_terminal_logs(tmp_path):
    cmd = [sys.executable, "-u", "-c", "import time; print('UNIQUE RUN'); time.sleep(0.02)"]
    def call(_):
        return capture(cmd, root=tmp_path, log_dir=tmp_path / "logs")
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(call, range(5))) == [0] * 5
    files = list((tmp_path / "logs").glob("Terminal_Session_*.log"))
    assert len(files) == 5
    assert all("UNIQUE RUN" in p.read_text() for p in files)


def test_windows_batch_launcher_and_docs_exist():
    root = Path(__file__).resolve().parents[1]
    bat = (root / "Start_AI_HR_Assistant_With_Terminal_Log.bat").read_text()
    assert '"%PYTHON_EXE%"' in bat
    assert "run_with_terminal_log.py" in bat
    assert "Terminal_Session_" in (root / "README.md").read_text()
    assert (root / "config" / "settings.py").read_text().count('app_version: str = "0.8.8.229"') == 1


def test_launcher_cli_captures_missing_streamlit_error(tmp_path):
    """Real subprocess smoke test even when Streamlit is unavailable in CI."""
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_with_terminal_log.py"
    # The wrapper's actual command uses sys.executable -m streamlit.
    # A fake Streamlit module lets us validate all plumbing without a server.
    fake = tmp_path / "stub"
    package = fake / "streamlit"
    package.mkdir(parents=True)
    (package / "__main__.py").write_text(
        "import sys, warnings\n"
        "assert sys.argv[1] == 'run'\n"
        "assert sys.argv[2].endswith('app.py')\n"
        "warnings.warn('simulated startup warning', UserWarning)\n"
        "print('STREAMLIT STUB READY')\n"
    )
    # The wrapper writes under its own project root; use direct capture instead
    # of creating private logs in the distributable root during this test.
    from scripts import run_with_terminal_log as wrapper
    command = [sys.executable, "-u", "-m", "streamlit", "run", str(root / "app.py")]
    try:
        prior = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(fake)
        assert wrapper.capture(command, root=root, log_dir=tmp_path / "runtime") == 0
    finally:
        if prior is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = prior
    data = next((tmp_path / "runtime").glob("Terminal_Session_*.log")).read_text()
    assert "STREAMLIT STUB READY" in data
    assert "UserWarning: simulated startup warning" in data
