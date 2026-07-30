"""Employee landing dashboard with full-width company announcements."""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from schemas.announcement_schema import (
    ANNOUNCEMENT_CATEGORIES,
)
from ui.pages.user.announcements_page import (
    _load_announcements,
    render_announcement_card,
)


def _filter_announcements(
    announcements,
    *,
    category: str,
    search_text: str,
):
    """Filter active announcements inside the dashboard."""

    normalized_search = search_text.strip().casefold()
    filtered = []

    for announcement in announcements:
        if (
            category != "All Categories"
            and announcement.category != category
        ):
            continue

        searchable = (
            f"{announcement.title} "
            f"{announcement.summary} "
            f"{announcement.content}"
        ).casefold()

        if (
            normalized_search
            and normalized_search not in searchable
        ):
            continue

        filtered.append(announcement)

    return filtered


def _target_announcement_id() -> int | None:
    """Return a safe announcement ID opened from a notification."""

    raw_value = st.query_params.get(
        "announcement_id"
    )

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def render_employee_dashboard_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render active company announcements across the dashboard width."""

    display_name = (
        current_user.employee_name
        or current_user.username
    )

    st.title(f"Welcome, {display_name}")
    st.caption(
        "Official company updates are available from this dashboard. "
        "Other HR services remain accessible from the sidebar."
    )

    announcements, images = _load_announcements(
        current_user
    )

    st.markdown("## Company Announcements")

    filter_left, filter_right = st.columns(
        [1.0, 2.0]
    )

    with filter_left:
        selected_category = st.selectbox(
            "Category",
            options=[
                "All Categories",
                *ANNOUNCEMENT_CATEGORIES,
            ],
            key="dashboard_announcement_category",
        )

    with filter_right:
        search_text = st.text_input(
            "Search",
            placeholder=(
                "Search company announcements and activities..."
            ),
            key="dashboard_announcement_search",
        )

    filtered = _filter_announcements(
        announcements,
        category=selected_category,
        search_text=search_text,
    )
    target_id = _target_announcement_id()
    target = next(
        (
            item
            for item in announcements
            if item.id == target_id
        ),
        None,
    )

    if target is not None:
        filtered = [
            target,
            *(
                item
                for item in filtered
                if item.id != target.id
            ),
        ]
        st.info(
            "Opened from Notifications"
        )

    st.caption(
        f"{len(filtered)} active announcement(s)"
    )

    if not filtered:
        st.info(
            "There is no active announcement matching the "
            "selected filters."
        )
        return

    pinned = [
        item
        for item in filtered
        if item.is_pinned
    ]
    regular = [
        item
        for item in filtered
        if not item.is_pinned
    ]

    if pinned:
        st.markdown("### Featured")
        for announcement in pinned:
            render_announcement_card(
                announcement,
                image_bytes=images.get(
                    announcement.id
                ),
                expanded=False,
            )

    if regular:
        st.markdown("### Latest Updates")
        for announcement in regular:
            render_announcement_card(
                announcement,
                image_bytes=images.get(
                    announcement.id
                ),
                expanded=False,
            )
