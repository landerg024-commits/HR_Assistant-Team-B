"""Pure tests for refresh-safe navigation value cleaning."""

from ui.navigation_state import _clean_query_value


def test_navigation_query_accepts_safe_value() -> None:
    assert (
        _clean_query_value(
            "Admin Dashboard",
            max_length=100,
        )
        == "Admin Dashboard"
    )


def test_navigation_query_accepts_sequence() -> None:
    assert (
        _clean_query_value(
            ["Employees"],
            max_length=100,
        )
        == "Employees"
    )


def test_navigation_query_rejects_invalid_value() -> None:
    assert _clean_query_value(None, max_length=100) is None
    assert _clean_query_value("", max_length=100) is None
    assert _clean_query_value("x" * 101, max_length=100) is None
