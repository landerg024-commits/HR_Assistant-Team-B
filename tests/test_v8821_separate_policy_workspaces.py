"""Regression checks for policy workspaces after peer-tab promotion."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")


def test_upload_and_management_remain_separate_workspaces() -> None:
    """The v8.8.21 separation remains after becoming peer tabs."""

    page_block = _source().split(
        "def render_admin_policies_page",
        1,
    )[1]

    assert "policies_tab, upload_tab, manage_tab, bin_tab = st.tabs([" in page_block
    assert '"Upload Policy File"' in page_block
    assert '"Manage Existing Policy"' in page_block

    upload_block = page_block.split(
        "with upload_tab:",
        1,
    )[1].split(
        "with manage_tab:",
        1,
    )[0]
    manage_block = page_block.split(
        "with manage_tab:",
        1,
    )[1].split(
        "with bin_tab:",
        1,
    )[0]

    assert "_render_upload(" in upload_block
    assert "_render_manage(" not in upload_block
    assert "_render_manage(" in manage_block
    assert "_render_upload(" not in manage_block


def test_manage_workspace_no_longer_contains_policy_list_table() -> None:
    """The active list belongs only to the read-only Policies tab."""

    page_block = _source().split(
        "def render_admin_policies_page",
        1,
    )[1]
    manage_block = page_block.split(
        "with manage_tab:",
        1,
    )[1].split(
        "with bin_tab:",
        1,
    )[0]

    assert "_render_manage(" in manage_block
    assert "_render_policy_table(" not in manage_block
