"""Static checks for the administrator policy-content viewer."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    """Read one project source file."""

    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_admin_page_has_content_viewer_tabs() -> None:
    """The selected policy must expose all management views."""

    source = _read(
        "ui/pages/admin/policies_page.py"
    )

    assert '"Extracted Content"' in source
    assert '"Searchable Sections"' in source
    assert '"Original File"' in source
    assert '"Move to Bin"' in source


def test_admin_page_downloads_extracted_text() -> None:
    """Complete extracted text must be downloadable."""

    source = _read(
        "ui/pages/admin/policies_page.py"
    )

    assert "Download Complete Extracted Text" in source
    assert 'mime="text/plain"' in source


def test_admin_page_supports_section_search() -> None:
    """Administrators must be able to find content in indexed sections."""

    source = _read(
        "ui/pages/admin/policies_page.py"
    )

    assert '"Find in Sections"' in source
    assert "section_search in section.text.lower()" in source


def test_service_exposes_company_scoped_admin_view() -> None:
    """The UI must use the validated service method."""

    source = _read(
        "ui/pages/admin/policies_page.py"
    )

    assert "get_admin_policy_view(" in source
    assert "company_id=current_user.company_id" in source
