"""Tests for direct script imports."""

import importlib.util
from pathlib import Path


def _load_script(script_name: str):
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / script_name
    )

    spec = importlib.util.spec_from_file_location(
        script_path.stem,
        script_path,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def test_create_database_script_imports() -> None:
    """The create-database script should import from a direct execution context."""

    module = _load_script("create_database.py")

    assert callable(module.main)


def test_check_database_script_imports() -> None:
    """The database-check script should import from a direct execution context."""

    module = _load_script("check_database.py")

    assert callable(module.main)
