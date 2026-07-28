"""Central design tokens for the HR Assistant UI.

All pages and reusable components must use these shared theme values.
"""

LIGHT_THEME: dict[str, str] = {
    "background": "#F7F9FC",
    "surface": "#FFFFFF",
    "surface_secondary": "#F3F5FA",
    "text_primary": "#10172A",
    "text_secondary": "#5C6680",
    "primary": "#4338E8",
    "primary_hover": "#372FD0",
    "primary_soft": "#EEF0FF",
    "border": "#E3E7F0",
    "success": "#18B66A",
    "warning": "#F5A623",
    "danger": "#E05252",
    "shadow": "0 8px 30px rgba(24, 36, 74, 0.08)",
}

DARK_THEME: dict[str, str] = {
    "background": "#0E1320",
    "surface": "#171D2C",
    "surface_secondary": "#202738",
    "text_primary": "#F7F8FC",
    "text_secondary": "#AAB3C8",
    "primary": "#7770FF",
    "primary_hover": "#8A84FF",
    "primary_soft": "#292852",
    "border": "#30384A",
    "success": "#31C77A",
    "warning": "#F5B942",
    "danger": "#F16A6A",
    "shadow": "0 10px 32px rgba(0, 0, 0, 0.30)",
}
