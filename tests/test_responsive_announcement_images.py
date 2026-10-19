"""Announcement image aspect-ratio and size regression tests."""

from io import BytesIO
from pathlib import Path

from PIL import Image

from ui.components.responsive_image import (
    prepare_responsive_image,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _image_bytes(
    width: int,
    height: int,
) -> bytes:
    image = Image.new(
        "RGB",
        (width, height),
        "white",
    )
    buffer = BytesIO()
    image.save(
        buffer,
        format="PNG",
    )
    return buffer.getvalue()


def test_wide_image_is_bounded_without_distortion() -> None:
    prepared = prepare_responsive_image(
        _image_bytes(2000, 1000),
        max_width=800,
        max_height=400,
    )

    assert prepared is not None
    assert prepared.size == (800, 400)


def test_tall_image_is_bounded_without_distortion() -> None:
    prepared = prepare_responsive_image(
        _image_bytes(1000, 2000),
        max_width=800,
        max_height=400,
    )

    assert prepared is not None
    assert prepared.size == (200, 400)


def test_small_image_is_not_enlarged() -> None:
    prepared = prepare_responsive_image(
        _image_bytes(240, 120),
        max_width=800,
        max_height=400,
    )

    assert prepared is not None
    assert prepared.size == (240, 120)


def test_invalid_image_returns_none() -> None:
    prepared = prepare_responsive_image(
        b"not-an-image",
        max_width=800,
        max_height=400,
    )

    assert prepared is None


def test_admin_and_employee_use_shared_responsive_renderer() -> None:
    admin_source = (
        PROJECT_ROOT
        / "ui/pages/admin/announcements_page.py"
    ).read_text(encoding="utf-8")
    employee_source = (
        PROJECT_ROOT
        / "ui/pages/user/announcements_page.py"
    ).read_text(encoding="utf-8")

    assert "render_responsive_image(" in admin_source
    assert "render_responsive_image(" in employee_source
    assert "use_container_width=True" not in (
        admin_source.split(
            "def _render_preview(",
            1,
        )[1].split(
            "def _render_overview(",
            1,
        )[0]
    )
    assert "use_container_width=True" not in (
        employee_source.split(
            "def render_announcement_card(",
            1,
        )[1].split(
            "def render_employee_announcements_page(",
            1,
        )[0]
    )
