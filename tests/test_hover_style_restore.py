"""Static tests for restored hover styling."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_secondary_button_hover_uses_soft_accent() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert (
        "div.stButton > button:not(:disabled):hover"
        in source
    )
    assert (
        "background: var(--hr-primary-soft) !important"
        in source
    )
    assert (
        "border-color: var(--hr-primary) !important"
        in source
    )


def test_primary_hover_keeps_white_text() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert (
        'button[kind="primary"]:not(:disabled):hover'
        in source
    )
    assert (
        "background: var(--hr-primary-hover) !important"
        in source
    )
    assert (
        "-webkit-text-fill-color: #FFFFFF !important"
        in source
    )


def test_tabs_have_soft_hover_and_selected_state() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert (
        '[data-testid="stTabs"] button[role="tab"]:hover'
        in source
    )
    assert (
        'button[role="tab"][aria-selected="true"]'
        in source
    )
    assert "var(--hr-primary-soft)" in source


def test_expander_hover_is_scoped_and_theme_aware() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert (
        '[data-testid="stExpander"] details > summary:hover'
        in source
    )
    assert "background: var(--hr-primary-soft)" in source


def test_admin_table_hover_uses_soft_accent() -> None:
    source = _read("ui/components/data_table.py")

    assert "tbody tr:hover td" in source
    assert "background: var(--hr-primary-soft)" in source
    assert "color: var(--hr-text-primary)" in source


def test_employee_table_hover_matches_admin_tables() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert (
        ".employee-master-table tbody tr:hover td"
        in source
    )
    assert "background: var(--hr-primary-soft)" in source
    assert "color: var(--hr-text-primary)" in source


def test_hover_styles_do_not_use_transform_or_layout_shift() -> None:
    source = _read("ui/theme/theme_loader.py")

    hover_section = source.split(
        "BUTTONS",
        1,
    )[1].split(
        "RESPONSIVE WIDTH",
        1,
    )[0]

    assert "transform:" not in hover_section
    assert "margin:" not in hover_section
