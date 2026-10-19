"""Process-wide terminal output capture when Streamlit is launched directly.

Streamlit runs app.py again for each browser interaction. Keep the capture in this
normal imported module (rather than in app.py globals) so every rerun and every
user shares exactly ONE runtime log per Python server process.

When the full-output runner is in use, it sets AI_HR_TERMINAL_CAPTURE_ACTIVE=1;
the wrapper already logs child stdout/stderr and a second native log is not made.
Direct `streamlit run app.py` can capture only output AFTER app.py executes; the
VS Code full-output configuration uses the wrapper for server startup/errors.
"""

from __future__ import annotations

import atexit
from datetime import datetime
import logging
import os
from pathlib import Path
import sys
from threading import RLock
from typing import TextIO

from scripts.run_with_terminal_log import DEFAULT_LOG_DIR, TerminalLog, _natural_limit, _retire_old_logs

_CAPTURE_LOCK = RLock()
_CAPTURE: "NativeCapture | None" = None


class _Tee:
    """Transparent stdout/stderr proxy: always retain console output."""

    def __init__(self, source: TextIO, sink: TerminalLog, lock: RLock):
        self._source = source
        self._sink = sink
        self._lock = lock

    def write(self, data: str) -> int:
        if not isinstance(data, str):
            data = str(data)
        with self._lock:
            result = self._source.write(data)
            try:
                self._sink.write(data)
            except (OSError, ValueError):
                # Logging must never break Chat Assistant or traceback output.
                pass
        return len(data) if result is None else result

    def flush(self) -> None:
        with self._lock:
            self._source.flush()
            try:
                self._sink._stream.flush()
            except (OSError, ValueError, AttributeError):
                pass

    def isatty(self) -> bool:
        return bool(self._source.isatty())

    @property
    def encoding(self):
        return getattr(self._source, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._source, "errors", "replace")

    def fileno(self) -> int:
        return self._source.fileno()

    def writable(self) -> bool:
        return True

    def __getattr__(self, name):
        return getattr(self._source, name)


class _LogToFile(logging.Handler):
    """Capture Python logging records even if their existing handlers bypass stderr."""

    def __init__(self, sink: TerminalLog, lock: RLock):
        super().__init__(logging.WARNING)
        self.sink = sink
        self.lock_sink = lock
        self.setFormatter(logging.Formatter("[PYTHON LOG] %(asctime)s %(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self.lock_sink:
                self.sink.write(self.format(record) + "\n")
        except (OSError, ValueError):
            pass


class NativeCapture:
    def __init__(self, log_dir: Path):
        self._lock = RLock()
        self.sink = TerminalLog(log_dir, max_bytes=_natural_limit(
            "AI_HR_TERMINAL_LOG_MAX_MB", 50, low=1, high=200
        ) * 1024 * 1024)
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.tee_stdout = _Tee(sys.stdout, self.sink, self._lock)
        self.tee_stderr = _Tee(sys.stderr, self.sink, self._lock)
        self.handler = _LogToFile(self.sink, self._lock)
        self._closed = False
        sys.stdout = self.tee_stdout
        sys.stderr = self.tee_stderr
        logging.getLogger().addHandler(self.handler)
        self._emit_header()

    def _emit_header(self) -> None:
        # Go to terminal as well as the file, without containing private args.
        print("=" * 72)
        print("AI HR ASSISTANT — TERMINAL / RUNTIME SESSION (DIRECT STREAMLIT)")
        print(f"Started: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        print(f"Log file: {self.sink.paths[0]}")
        print("Scope: whole Streamlit server process; output after first app.py run")
        print("Startup output before app.py requires the full-output launcher / VS Code task")
        print("=" * 72)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if sys.stdout is self.tee_stdout:
                sys.stdout = self.old_stdout
            if sys.stderr is self.tee_stderr:
                sys.stderr = self.old_stderr
            logging.getLogger().removeHandler(self.handler)
            self.handler.close()
            try:
                self.sink.write(f"\n[TERMINAL LOG] Direct capture closed: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
            except (OSError, ValueError):
                pass
            self.sink.close()


def _atexit_close() -> None:
    with _CAPTURE_LOCK:
        if _CAPTURE is not None:
            _CAPTURE.close()


def ensure_native_runtime_capture() -> NativeCapture | None:
    """Start one log on the first app execution; safe across Streamlit reruns."""
    global _CAPTURE
    if os.environ.get("AI_HR_TERMINAL_CAPTURE_ACTIVE") == "1":
        return None
    if os.environ.get("AI_HR_NATIVE_RUNTIME_LOG_ENABLED", "true").strip().lower() in {
        "0", "false", "no", "off"
    }:
        return None
    with _CAPTURE_LOCK:
        if _CAPTURE is not None and not _CAPTURE._closed:
            return _CAPTURE
        try:
            _CAPTURE = NativeCapture(DEFAULT_LOG_DIR)
            keep = _natural_limit("AI_HR_TERMINAL_LOG_RETENTION_FILES", 12, low=1, high=100)
            _retire_old_logs(DEFAULT_LOG_DIR, keep=keep, exclude=tuple(_CAPTURE.sink.paths))
        except OSError as exc:
            print(f"[TERMINAL LOG ERROR] Native logging unavailable: {type(exc).__name__}", file=sys.stderr)
            _CAPTURE = None
            return None
        atexit.register(_atexit_close)
        return _CAPTURE
