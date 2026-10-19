"""Regression tests for negative legacy leave-balance UI handling."""

import ast
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"


def _load_safe_value_function():
    """Load only the pure helper without importing Streamlit."""

    module = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    function_node = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_nonnegative_editor_value"
    )
    isolated_module = ast.Module(
        body=[function_node],
        type_ignores=[],
    )
    namespace = {"Decimal": Decimal}
    exec(compile(isolated_module, str(PAGE_PATH), "exec"), namespace)
    return namespace["_nonnegative_editor_value"]


def test_negative_balance_uses_streamlit_safe_zero_default() -> None:
    safe_value = _load_safe_value_function()
    assert safe_value(Decimal("-32.00")) == 0.0


def test_nonnegative_balance_keeps_its_exact_default() -> None:
    safe_value = _load_safe_value_function()
    assert safe_value(Decimal("15.50")) == 15.5
    assert safe_value(Decimal("0.00")) == 0.0


def test_credit_editor_uses_safe_default_and_warning() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")

    assert "value=_nonnegative_editor_value(current_remaining)" in source
    assert "if current_remaining < 0:" in source
    assert "legacy negative leave balance was detected" in source
