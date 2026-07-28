"""Company accent-color derivation utilities.

This module has no Streamlit dependency, allowing services and tests to
derive accessible theme colors without loading the UI runtime.
"""

import re

from core.constants import DEFAULT_COMPANY_THEME_COLOR


_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_theme_color(
    value: str | None,
) -> str:
    """Return a safe uppercase six-digit hex color."""

    candidate = (value or "").strip()

    if not _HEX_COLOR_PATTERN.fullmatch(candidate):
        return DEFAULT_COMPANY_THEME_COLOR

    return candidate.upper()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert one normalized hex color to RGB values."""

    normalized = normalize_theme_color(value)

    return (
        int(normalized[1:3], 16),
        int(normalized[3:5], 16),
        int(normalized[5:7], 16),
    )


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB values to a normalized hex color."""

    return "#{:02X}{:02X}{:02X}".format(
        *(max(0, min(255, channel)) for channel in rgb)
    )


def _mix_hex(
    first: str,
    second: str,
    second_weight: float,
) -> str:
    """Blend two colors using a weight from zero to one."""

    weight = max(0.0, min(1.0, second_weight))
    first_rgb = _hex_to_rgb(first)
    second_rgb = _hex_to_rgb(second)

    return _rgb_to_hex(
        tuple(
            round(
                first_channel * (1.0 - weight)
                + second_channel * weight
            )
            for first_channel, second_channel in zip(
                first_rgb,
                second_rgb,
            )
        )
    )


def _relative_luminance(value: str) -> float:
    """Return WCAG relative luminance for one hex color."""

    channels = []

    for channel in _hex_to_rgb(value):
        normalized = channel / 255.0
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = channels

    return (
        0.2126 * red
        + 0.7152 * green
        + 0.0722 * blue
    )


def _contrast_ratio(
    first: str,
    second: str,
) -> float:
    """Return WCAG contrast ratio between two colors."""

    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)

    return (lighter + 0.05) / (darker + 0.05)


def _best_foreground(background: str) -> str:
    """Choose readable white or dark text for a color surface."""

    dark_text = "#10172A"
    white_text = "#FFFFFF"

    if (
        _contrast_ratio(background, white_text)
        >= _contrast_ratio(background, dark_text)
    ):
        return white_text

    return dark_text


def _accessible_accent_text(
    accent: str,
    soft_surface: str,
) -> str:
    """Darken a light accent until text contrast is readable."""

    candidate = accent

    for step in range(13):
        if _contrast_ratio(candidate, soft_surface) >= 4.5:
            return candidate

        candidate = _mix_hex(
            accent,
            "#000000",
            min(0.78, (step + 1) * 0.065),
        )

    return "#10172A"


def build_accent_palette(
    primary_color: str | None,
) -> dict[str, str]:
    """Derive accessible company-theme colors from one selected color."""

    primary = normalize_theme_color(primary_color)
    luminance = _relative_luminance(primary)

    primary_hover = (
        _mix_hex(primary, "#000000", 0.16)
        if luminance >= 0.18
        else _mix_hex(primary, "#FFFFFF", 0.14)
    )
    primary_soft = _mix_hex(primary, "#FFFFFF", 0.90)
    primary_text = _accessible_accent_text(
        primary,
        primary_soft,
    )
    red, green, blue = _hex_to_rgb(primary)

    return {
        "primary": primary,
        "primary_hover": primary_hover,
        "primary_soft": primary_soft,
        "primary_text": primary_text,
        "on_primary": _best_foreground(primary),
        "on_primary_hover": _best_foreground(primary_hover),
        "primary_rgb": f"{red}, {green}, {blue}",
    }
