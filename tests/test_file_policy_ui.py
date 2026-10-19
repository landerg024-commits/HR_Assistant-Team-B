"""Static checks for file-based policy UI integration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_admin_policy_page_uses_file_uploader() -> None:
    source = _read("ui/pages/admin/policies_page.py")

    assert "st.file_uploader(" in source
    assert "create_policy_from_upload(" in source
    assert "Upload and Process Policy" in source


def test_employee_sources_include_filename_and_page() -> None:
    source = _read("ui/pages/user/chat_page.py")

    assert "source.filename" in source
    assert "source.page_number" in source


def test_employee_policy_page_has_authorized_download() -> None:
    source = _read("ui/pages/user/policies_page.py")

    assert "get_policy_download(" in source
    assert "published_only=True" in source
    assert "st.download_button(" in source
