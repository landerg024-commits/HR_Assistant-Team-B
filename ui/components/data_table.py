"""Reusable theme-aware wrapped table for administration pages.

Why this exists:
Streamlit's default dataframe grid can keep an internal dark appearance even
when the surrounding application uses the custom light theme. This component
renders safe HTML using the project's design tokens instead.

Security:
Every header and cell value is escaped before rendering.
"""

from html import escape
import re
from typing import Mapping, Sequence

import streamlit as st


def _safe_key(value: str) -> str:
    """Return a CSS-safe identifier fragment."""

    normalized = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        value.strip(),
    ).strip("-")

    return normalized or "table"


def _cell_html(value: object) -> str:
    """Escape one cell and preserve line breaks."""

    if value is None:
        return ""

    return escape(str(value)).replace(
        "\n",
        "<br>",
    )


def render_admin_table(
    rows: Sequence[Mapping[str, object]],
    *,
    key: str,
    min_width: int = 900,
    column_widths: Sequence[str] | None = None,
    compact: bool = False,
    max_height: int | None = None,
) -> None:
    """Render a responsive wrapped table using HR theme variables.

    Args:
        rows: Ordered dictionaries containing table values.
        key: Unique page/table identifier used only for CSS scoping.
        min_width: Minimum table width before horizontal scrolling.
        column_widths: Optional CSS widths matching the column order.
        compact: Use slightly smaller padding for metadata tables.
        max_height: Optional fixed scroll-box height for long tables.
    """

    if not rows:
        return

    table_class = (
        "hr-admin-table-"
        + _safe_key(key)
    )
    shell_class = (
        "hr-admin-table-shell-"
        + _safe_key(key)
    )

    headers = list(rows[0].keys())

    header_html = "".join(
        f"<th>{escape(str(header))}</th>"
        for header in headers
    )

    body_html = "".join(
        "<tr>"
        + "".join(
            f"<td>{_cell_html(row.get(header, ''))}</td>"
            for header in headers
        )
        + "</tr>"
        for row in rows
    )

    width_rules = ""

    if column_widths:
        rules: list[str] = []

        for index, width in enumerate(
            column_widths,
            start=1,
        ):
            rules.append(
                f"""
                .{table_class} th:nth-child({index}),
                .{table_class} td:nth-child({index}) {{
                    width: {escape(str(width))};
                }}
                """
            )

        width_rules = "\n".join(rules)

    vertical_padding = "9px" if compact else "12px"
    horizontal_padding = "11px" if compact else "14px"
    font_size = "0.84rem" if compact else "0.88rem"

    vertical_scroll_rules = ""

    if max_height is not None:
        safe_height = max(160, int(max_height))
        vertical_scroll_rules = f"""
            max-height: {safe_height}px;
            overflow-y: scroll;
            scrollbar-gutter: stable;
            scrollbar-width: auto;
            scrollbar-color: var(--hr-primary) #E5EAF2;
        """

    html = f"""
    <style>
        .{shell_class} {{
            width: 100%;
            max-width: 100%;
            overflow-x: auto;
            {vertical_scroll_rules}
            border: 1px solid var(--hr-border);
            border-radius: 14px;
            background: var(--hr-surface);
            box-shadow: var(--hr-shadow);
        }}

        .{shell_class}::-webkit-scrollbar {{
            width: 12px;
            height: 12px;
        }}

        .{shell_class}::-webkit-scrollbar-track {{
            background: #E5EAF2;
            border-radius: 999px;
        }}

        .{shell_class}::-webkit-scrollbar-thumb {{
            min-height: 44px;
            background: var(--hr-primary);
            border: 2px solid #E5EAF2;
            border-radius: 999px;
        }}

        .{shell_class}::-webkit-scrollbar-thumb:hover {{
            background: var(--hr-primary-hover);
        }}

        .{shell_class}::-webkit-scrollbar-corner {{
            background: #E5EAF2;
        }}

        .{table_class} {{
            width: 100%;
            min-width: {int(min_width)}px;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
            color: var(--hr-text-primary);
            background: var(--hr-surface);
            font-size: {font_size};
        }}

        .{table_class} th {{
            position: sticky;
            top: 0;
            z-index: 2;
            padding: {vertical_padding} {horizontal_padding};
            color: var(--hr-text-primary);
            background: var(--hr-surface-secondary);
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.35;
            font-weight: 700;
        }}

        .{table_class} td {{
            padding: {vertical_padding} {horizontal_padding};
            color: var(--hr-text-secondary);
            background: var(--hr-surface);
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.45;
            transition:
                color 0.14s ease,
                background-color 0.14s ease;
        }}

        .{table_class} th:last-child,
        .{table_class} td:last-child {{
            border-right: 0;
        }}

        .{table_class} tbody tr:last-child td {{
            border-bottom: 0;
        }}

        .{table_class} tbody tr:hover td {{
            color: var(--hr-text-primary);
            background: var(--hr-primary-soft);
        }}

        {width_rules}
    </style>

    <div class="{shell_class}">
        <table class="{table_class}">
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {body_html}
            </tbody>
        </table>
    </div>
    """

    st.markdown(
        html,
        unsafe_allow_html=True,
    )
