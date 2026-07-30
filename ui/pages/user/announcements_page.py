"""Employee-facing company announcement archive."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from ui.components.responsive_image import (
    render_responsive_image,
)
from schemas.announcement_schema import (
    ANNOUNCEMENT_CATEGORIES,
)
from services.announcement_service import AnnouncementService


def _display_date(value) -> str:
    """Format publication time for employee cards."""

    if value is None:
        return "Published recently"

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        ZoneInfo(get_settings().display_timezone)
    ).strftime("%b %d, %Y")


def _load_announcements(
    current_user: AuthenticatedUser,
    *,
    limit: int | None = None,
):
    """Load visible announcements and private images."""

    with SessionFactory() as session:
        service = AnnouncementService(session)
        service.reconcile_publications(
            company_id=current_user.company_id
        )
        announcements = service.list_visible(
            company_id=current_user.company_id,
            limit=limit,
        )
        images: dict[int, bytes] = {}

        for announcement in announcements:
            if not announcement.image_storage_path:
                continue

            try:
                images[announcement.id] = (
                    service.read_image(announcement)
                )
            except FileNotFoundError:
                continue

    return announcements, images


def render_announcement_card(
    announcement,
    *,
    image_bytes: bytes | None,
    expanded: bool = False,
) -> None:
    """Render one responsive announcement card."""

    with st.container(border=True):
        st.caption(
            f"{announcement.category} · "
            f"{_display_date(announcement.publish_at)}"
        )
        st.markdown(f"### {announcement.title}")
        st.write(announcement.summary)

        if announcement.is_pinned:
            st.info("Pinned company update")

        if image_bytes:
            render_responsive_image(
                image_bytes,
                max_width=820,
                max_height=420,
            )

        with st.expander(
            "Read Full Announcement",
            expanded=expanded,
        ):
            st.markdown(announcement.content)


def render_employee_announcements_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render searchable active company announcements."""

    st.title("Company Announcements")
    st.caption(
        "Official company information, activities, events, "
        "reminders, and HR updates."
    )

    announcements, images = _load_announcements(
        current_user
    )

    if not announcements:
        st.info(
            "There is no active company announcement at this time."
        )
        return

    filter_left, filter_right = st.columns(2)

    with filter_left:
        selected_category = st.selectbox(
            "Category",
            options=[
                "All Categories",
                *ANNOUNCEMENT_CATEGORIES,
            ],
        )

    with filter_right:
        search_text = st.text_input(
            "Search Announcements",
            placeholder="Search title, summary, or content...",
        )

    normalized_search = search_text.strip().casefold()
    filtered = []

    for announcement in announcements:
        if (
            selected_category != "All Categories"
            and announcement.category
            != selected_category
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

    st.caption(
        f"{len(filtered)} of {len(announcements)} announcement(s) shown."
    )

    if not filtered:
        st.info(
            "No announcement matches the selected filters."
        )
        return

    for announcement in filtered:
        render_announcement_card(
            announcement,
            image_bytes=images.get(
                announcement.id
            ),
        )
