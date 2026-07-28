"""Apply the centralized light or dark UI theme."""

import streamlit as st

from ui.theme.design_tokens import DARK_THEME, LIGHT_THEME


_REQUIRED_DEFAULTS: dict[str, str] = {
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


def _get_theme_tokens() -> dict[str, str]:
    """Return complete tokens for the selected theme.

    Defaults are merged first so one missing theme value can never crash
    the entire application.
    """

    selected_theme = (
        DARK_THEME
        if st.session_state.get("theme", "light") == "dark"
        else LIGHT_THEME
    )

    return {
        **_REQUIRED_DEFAULTS,
        **selected_theme,
    }


def apply_theme() -> None:
    """Apply global styles and keep the sidebar permanently expanded."""

    tokens = _get_theme_tokens()

    css = f"""
    <style>
    :root {{
        --hr-bg: {tokens["background"]};
        --hr-surface: {tokens["surface"]};
        --hr-surface-secondary: {tokens["surface_secondary"]};
        --hr-text-primary: {tokens["text_primary"]};
        --hr-text-secondary: {tokens["text_secondary"]};
        --hr-primary: {tokens["primary"]};
        --hr-primary-hover: {tokens["primary_hover"]};
        --hr-primary-soft: {tokens["primary_soft"]};
        --hr-border: {tokens["border"]};
        --hr-success: {tokens["success"]};
        --hr-warning: {tokens["warning"]};
        --hr-danger: {tokens["danger"]};
        --hr-shadow: {tokens["shadow"]};
    }}

    html,
    body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {{
        background: var(--hr-bg);
        color: var(--hr-text-primary);
    }}

    [data-testid="stHeader"] {{
        background: transparent;
    }}

    /* Permanent sidebar */
    section[data-testid="stSidebar"] {{
        position: fixed !important;
        inset: 0 auto 0 0 !important;

        width: 285px !important;
        min-width: 285px !important;
        max-width: 285px !important;
        height: 100vh !important;

        margin-left: 0 !important;
        transform: translateX(0) !important;
        visibility: visible !important;

        background: var(--hr-surface) !important;
        border-right: 1px solid var(--hr-border) !important;

        overflow-y: auto !important;
        overflow-x: hidden !important;

        z-index: 999 !important;
        transition: none !important;
    }}

    section[data-testid="stSidebar"][aria-expanded="false"],
    section[data-testid="stSidebar"][aria-expanded="true"] {{
        left: 0 !important;
        margin-left: 0 !important;
        transform: translateX(0) !important;

        width: 285px !important;
        min-width: 285px !important;
        max-width: 285px !important;
    }}

    section[data-testid="stSidebar"] > div,
    [data-testid="stSidebarContent"] {{
        width: 285px !important;
        min-width: 285px !important;
        max-width: 285px !important;
    }}

    /* Hide sidebar collapse/open controls across Streamlit versions. */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarHeader"] button,
    button[data-testid="stBaseButton-headerNoPadding"],
    button[kind="header"],
    button[aria-label="Close sidebar"],
    button[aria-label="Open sidebar"],
    button[title="Close sidebar"],
    button[title="Open sidebar"] {{
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        pointer-events: none !important;
    }}

    /* Keep content beside the fixed sidebar. */
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stMain"] {{
        margin-left: 285px !important;
        width: calc(100% - 285px) !important;
        max-width: calc(100% - 285px) !important;
    }}

    .block-container {{
        max-width: 1500px;
        padding: 1.2rem 2rem 2rem;
    }}

    .hr-topbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;

        margin-bottom: 20px;
        padding: 16px 20px;

        background: var(--hr-surface);
        border: 1px solid var(--hr-border);
        border-radius: 18px;
        box-shadow: var(--hr-shadow);
    }}

    .hr-card {{
        min-height: 112px;
        padding: 18px;

        background: var(--hr-surface);
        border: 1px solid var(--hr-border);
        border-radius: 14px;
        box-shadow: var(--hr-shadow);
    }}

    .hr-placeholder {{
        padding: 34px;

        color: var(--hr-text-secondary);
        text-align: center;

        background: var(--hr-surface);
        border: 1px dashed var(--hr-border);
        border-radius: 18px;
        box-shadow: var(--hr-shadow);
    }}

    .hr-brand {{
        color: var(--hr-primary);
        font-size: 1.25rem;
        font-weight: 750;
    }}

    .hr-card-title,
    .hr-title {{
        margin-bottom: 8px;
        color: var(--hr-text-primary);
        font-weight: 700;
    }}

    .hr-card-text,
    .hr-muted {{
        color: var(--hr-text-secondary);
    }}

    div.stButton > button {{
        color: var(--hr-text-primary);
        background: var(--hr-surface);
        border: 1px solid var(--hr-border);
        border-radius: 12px;
    }}

    div.stButton > button:hover {{
        color: var(--hr-primary);
        border-color: var(--hr-primary);
    }}

    div[data-testid="stChatInput"] {{
        background: var(--hr-surface);
        border-radius: 16px;
    }}

    @media (max-width: 900px) {{
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        [data-testid="stSidebarContent"] {{
            width: 250px !important;
            min-width: 250px !important;
            max-width: 250px !important;
        }}

        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stMain"] {{
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            max-width: calc(100% - 250px) !important;
        }}
    }}
    </style>
    """

    st.markdown(css, unsafe_allow_html=True)
