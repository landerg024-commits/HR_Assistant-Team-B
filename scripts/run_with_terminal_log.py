"""Streamlit launcher that retains exactly what the server prints to the terminal.

Run from a project root with ``python scripts/run_with_terminal_log.py`` or use
``Start_AI_HR_Assistant_With_Terminal_Log.bat`` on Windows. This process-wide log
is NOT user/session scoped: multiple users of the server share the output.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import secrets
import subprocess
import sys
import traceback

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "runtime"


def _natural_limit(env_name: str, fallback: int, *, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.environ.get(env_name, str(fallback)))))
    except (ValueError, OverflowError):
        return fallback


class TerminalLog:
    """Single-launch UTF-8 output, with bounded rollover for large QA runs."""

    def __init__(self, log_dir: Path, *, max_bytes: int = 50 * 1024 * 1024) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self.base = log_dir / (
            f"Terminal_Session_{datetime.now().astimezone():%Y%m%dT%H%M%S}_"
            f"{os.getpid()}_{secrets.token_hex(3)}"
        )
        self._part = 1
        self.max_bytes = max_bytes
        self._bytes = 0
        self.paths: list[Path] = []
        self._stream = None
        self._open_next()

    def _open_next(self) -> None:
        path = self.base.with_name(self.base.name + (f"_part{self._part:02d}" if self._part > 1 else "") + ".log")
        self._stream = path.open("x", encoding="utf-8", newline="\n")
        self.paths.append(path)
        self._bytes = 0

    def write(self, line: str) -> None:
        encoded_length = len(line.encode("utf-8", errors="replace"))
        if self._bytes and self._bytes + encoded_length > self.max_bytes:
            self._stream.close()
            self._part += 1
            self._open_next()
        self._stream.write(line)
        self._stream.flush()  # Keep completed lines visible after a crash.
        self._bytes += encoded_length

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


def _retire_old_logs(folder: Path, *, keep: int, exclude: tuple[Path, ...]) -> None:
    """Delete only older terminal-run files. Never touch per-user QA logs."""
    files = sorted(folder.glob("Terminal_Session_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[keep:]:
        if path not in exclude:
            try:
                path.unlink()
            except OSError:
                pass  # Logging must never affect app availability.


def capture(command: list[str], *, root: Path = PROJECT_ROOT,
            log_dir: Path = DEFAULT_LOG_DIR, max_bytes: int | None = None) -> int:
    """Tee combined child stdout/stderr to terminal and one runtime log.

    Returns the child's real exit code; a launcher failure returns nonzero.
    Does not emit command-line arguments or environment values (potential secrets).
    """
    if max_bytes is None:
        max_bytes = _natural_limit("AI_HR_TERMINAL_LOG_MAX_MB", 50, low=1, high=200) * 1024 * 1024
    try:
        sink = TerminalLog(log_dir, max_bytes=max_bytes)
    except OSError as exc:
        print(f"[TERMINAL LOG ERROR] Cannot create runtime log: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2  # Fail visibly, rather than claiming terminal output was logged.

    log_is_writable = True

    def emit(text: str) -> None:
        nonlocal log_is_writable
        if log_is_writable:
            try:
                sink.write(text)
            except OSError as exc:
                log_is_writable = False
                print(f"[TERMINAL LOG ERROR] Logging stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (UnicodeError, OSError):
            pass  # A broken terminal must not stop the log capture.

    child = None
    code = 1
    try:
        emit("=" * 72 + "\n")
        emit("AI HR ASSISTANT — TERMINAL / RUNTIME SESSION\n")
        emit(f"Started: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        emit(f"Log file: {sink.paths[0]}\n")
        emit("Scope: entire Streamlit server process (all connected users)\n")
        emit("Includes: Streamlit output, warnings, errors, tracebacks, app diagnostics\n")
        emit("=" * 72 + "\n")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8:replace"
        # App-level capture must not create a second file when wrapper is used.
        env["AI_HR_TERMINAL_CAPTURE_ACTIVE"] = "1"
        # Streamlit's code watcher introspects lazy Transformers image modules
        # and can print hundreds of spurious missing-torchvision tracebacks.
        # Disable watching only for this Windows/QA packaged launcher. A dev
        # launching Streamlit directly retains its chosen hot-reload behavior.
        env.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
        emit(f"[TERMINAL LOG] Streamlit file watcher: {env['STREAMLIT_SERVER_FILE_WATCHER_TYPE']}\n")
        child = subprocess.Popen(
            command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=None, bufsize=1, text=True, encoding="utf-8", errors="replace", env=env,
        )
        assert child.stdout is not None
        for line in child.stdout:
            emit(line)
        code = child.wait()
    except KeyboardInterrupt:
        emit("\n[TERMINAL LOG] Stop requested (Ctrl+C).\n")
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        code = 130
    except Exception:
        emit("[TERMINAL LOG] Launcher exception:\n" + traceback.format_exc())
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        code = 1
    finally:
        if child is not None and child.stdout is not None:
            child.stdout.close()
        emit(f"\n[TERMINAL LOG] Ended: {datetime.now().astimezone().isoformat(timespec='seconds')} | exit_code={code}\n")
        emit("[TERMINAL LOG] Files: " + ", ".join(str(path) for path in sink.paths) + "\n")
        sink.close()
        keep = _natural_limit("AI_HR_TERMINAL_LOG_RETENTION_FILES", 12, low=1, high=100)
        _retire_old_logs(log_dir, keep=keep, exclude=tuple(sink.paths))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch Streamlit and capture all terminal output to a local log")
    parser.add_argument("streamlit_args", nargs=argparse.REMAINDER, help="Optional flags forwarded to streamlit run app.py")
    args = parser.parse_args(argv)
    extras = args.streamlit_args
    if extras[:1] == ["--"]:
        extras = extras[1:]
    command = [sys.executable, "-u", "-m", "streamlit", "run", str(PROJECT_ROOT / "app.py"), *extras]
    return capture(command)


if __name__ == "__main__":
    raise SystemExit(main())
