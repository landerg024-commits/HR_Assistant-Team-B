"""Regression checks for bounded policy management and Bin confirmation."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    """Read one project source file."""

    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_searchable_sections_use_fixed_scroll_container() -> None:
    """Many section matches must not stretch the whole Policies page."""

    source = _read("ui/pages/admin/policies_page.py")
    block = source.split(
        "def _render_sections(",
        1,
    )[1].split(
        "def _render_original_file(",
        1,
    )[0]

    assert "POLICY_SECTION_RESULTS_HEIGHT = 430" in source
    assert "with st.container(" in block
    assert "height=POLICY_SECTION_RESULTS_HEIGHT" in block
    assert "scroll inside the results box" in block
    assert "No searchable sections match" in block


def test_version_history_table_is_bounded_and_scrollable() -> None:
    """Version rows remain complete inside a fixed-height table shell."""

    policy_source = _read("ui/pages/admin/policies_page.py")
    table_source = _read("ui/components/data_table.py")

    assert "POLICY_VERSION_HISTORY_HEIGHT = 340" in policy_source
    assert "max_height=POLICY_VERSION_HISTORY_HEIGHT" in policy_source
    assert "max_height: int | None = None" in table_source
    assert "overflow-y: scroll" in table_source
    assert "max-height: {safe_height}px" in table_source
    assert "position: sticky" in table_source


def test_move_to_bin_targets_selected_policy_with_checkbox() -> None:
    """The selected policy is the target; no Policy ID typing is needed."""

    source = _read("ui/pages/admin/policies_page.py")
    block = source.split(
        "def _render_move_to_bin(",
        1,
    )[1].split(
        "def _render_upload(",
        1,
    )[0]

    assert "Selected target:" in block
    assert "st.checkbox(" in block
    assert "confirmation checkbox" in block
    assert "confirmation_public_id=public_id" in block
    assert "Type the exact Policy ID to confirm" not in block
    assert "st.text_input(" not in block
