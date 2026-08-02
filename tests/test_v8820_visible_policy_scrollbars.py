"""Regression checks for visible policy-management scrollbars."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_searchable_sections_has_stable_scrollbar_target() -> None:
    source = _read("ui/pages/admin/policies_page.py")
    block = source.split("def _render_sections(", 1)[1].split(
        "def _render_original_file(", 1
    )[0]

    assert 'f"policy_section_results_"' in block
    assert "height=POLICY_SECTION_RESULTS_HEIGHT" in block


def test_policy_scroll_boxes_define_visible_scrollbar_track_and_thumb() -> None:
    theme = _read("ui/theme/theme_loader.py")

    assert "VISIBLE POLICY SCROLLBARS — v8.8.20" in theme
    assert 'div[class*="st-key-policy_section_results_"]' in theme
    assert 'div[class*="st-key-policy_content_"] textarea' in theme
    assert 'div[class*="st-key-editable_policy_content_"] textarea' in theme
    assert "::-webkit-scrollbar-track" in theme
    assert "::-webkit-scrollbar-thumb" in theme
    assert "width: 12px !important" in theme
    assert "scrollbar-color: var(--hr-primary) #E5EAF2 !important" in theme
    assert "overflow-y: scroll !important" in theme


def test_bounded_admin_tables_use_visible_scrollbars() -> None:
    source = _read("ui/components/data_table.py")

    assert "overflow-y: scroll" in source
    assert "scrollbar-width: auto" in source
    assert ".{shell_class}::-webkit-scrollbar-track" in source
    assert ".{shell_class}::-webkit-scrollbar-thumb" in source


def test_editable_policy_content_has_a_scrollbar_css_key() -> None:
    source = _read("ui/pages/admin/policies_page.py")

    assert 'key=f"editable_policy_content_{policy.id}"' in source
