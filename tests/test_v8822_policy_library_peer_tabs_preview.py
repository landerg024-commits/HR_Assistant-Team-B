"""Regression checks for the four peer policy tabs and on-demand preview."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_policy_page_has_four_peer_tabs_in_requested_order() -> None:
    source = _read("ui/pages/admin/policies_page.py")
    page_block = source.split(
        "def render_admin_policies_page",
        1,
    )[1]

    assert "policies_tab, upload_tab, manage_tab, bin_tab = st.tabs([" in page_block

    policies_index = page_block.index('"Policies"')
    upload_index = page_block.index('"Upload Policy File"')
    manage_index = page_block.index('"Manage Existing Policy"')
    bin_index = page_block.index('f"Bin ({len(bin_policies)})"')

    assert policies_index < upload_index < manage_index < bin_index


def test_policies_tab_contains_only_library_and_on_demand_preview() -> None:
    source = _read("ui/pages/admin/policies_page.py")
    page_block = source.split(
        "def render_admin_policies_page",
        1,
    )[1]
    policies_block = page_block.split(
        "with policies_tab:",
        1,
    )[1].split(
        "with upload_tab:",
        1,
    )[0]

    assert "_render_policy_library(" in policies_block
    assert "_render_upload(" not in policies_block
    assert "_render_manage(" not in policies_block

    library_block = source.split(
        "def _render_policy_library(",
        1,
    )[1].split(
        "def _render_manage(",
        1,
    )[0]

    assert 'key="policy-list"' in library_block
    assert '"Preview Selected Policy"' in library_block
    assert "_POLICY_LIBRARY_PREVIEW_STATE_KEY" in library_block
    assert "_render_detected_headings(view.sections)" in library_block
    assert "_render_full_section_preview(view.sections)" in library_block
    assert "_render_overview(" not in library_block
    assert "_render_edit_policy_details(" not in library_block
    assert "_render_move_to_bin(" not in library_block


def test_policy_list_table_is_fixed_height_and_scrollable() -> None:
    policy_source = _read("ui/pages/admin/policies_page.py")
    table_source = _read("ui/components/data_table.py")

    assert "POLICY_LIBRARY_TABLE_HEIGHT = 390" in policy_source
    assert "max_height=POLICY_LIBRARY_TABLE_HEIGHT" in policy_source
    assert "overflow-y: scroll" in table_source
    assert "scrollbar-gutter: stable" in table_source
    assert "position: sticky" in table_source
