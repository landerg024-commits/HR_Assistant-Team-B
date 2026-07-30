"""Administrator announcement publishing workspace."""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from pydantic import ValidationError
import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from schemas.announcement_schema import (
    ANNOUNCEMENT_CATEGORIES,
    AnnouncementInput,
)
from services.announcement_service import AnnouncementService
from ui.components.data_table import render_admin_table
from ui.components.responsive_image import (
    render_responsive_image,
)
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)


def _local_datetime(
    selected_date: date,
    *,
    end_of_day: bool = False,
) -> datetime:
    """Convert a local calendar date into an aware UTC timestamp."""

    local_time = (
        time(23, 59, 59)
        if end_of_day
        else time(0, 0, 0)
    )
    local_value = datetime.combine(
        selected_date,
        local_time,
        tzinfo=ZoneInfo(
            get_settings().display_timezone
        ),
    )

    return local_value.astimezone(timezone.utc)


def _local_date(
    value: datetime | None,
    *,
    fallback: date,
) -> date:
    """Convert a stored UTC timestamp into the display timezone."""

    if value is None:
        return fallback

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        ZoneInfo(get_settings().display_timezone)
    ).date()


def _display_datetime(
    value: datetime | None,
) -> str:
    """Format an announcement date for tables and previews."""

    if value is None:
        return "—"

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        ZoneInfo(get_settings().display_timezone)
    ).strftime("%Y-%m-%d %I:%M %p")


def _announcement_input(
    *,
    current_user: AuthenticatedUser,
    title: str,
    category: str,
    summary: str,
    content: str,
    is_pinned: bool,
    publish_date: date,
    expiry_enabled: bool,
    expiry_date: date,
) -> AnnouncementInput:
    """Build validated values from the admin form."""

    return AnnouncementInput(
        company_id=current_user.company_id,
        title=title,
        category=category,
        summary=summary,
        content=content,
        is_pinned=is_pinned,
        publish_at=_local_datetime(
            publish_date
        ),
        expires_at=(
            _local_datetime(
                expiry_date,
                end_of_day=True,
            )
            if expiry_enabled
            else None
        ),
    )


def _read_image_map(
    current_user: AuthenticatedUser,
    announcements,
) -> dict[int, bytes]:
    """Load available images while handling missing local files safely."""

    images: dict[int, bytes] = {}

    with SessionFactory() as session:
        service = AnnouncementService(session)

        for announcement in announcements:
            if not announcement.image_storage_path:
                continue

            try:
                images[announcement.id] = (
                    service.read_image(announcement)
                )
            except FileNotFoundError:
                continue

    return images


def _render_preview(
    announcement,
    *,
    image_bytes: bytes | None,
) -> None:
    """Render a complete admin preview using the employee layout."""

    with st.container(border=True):
        st.caption(
            f"{announcement.category} · "
            f"{AnnouncementService.display_status(announcement)} · "
            f"{_display_datetime(announcement.publish_at)}"
        )
        st.markdown(f"### {announcement.title}")
        st.write(announcement.summary)

        if announcement.is_pinned:
            st.info(
                "Pinned announcement — this receives priority "
                "on the employee dashboard."
            )

        if image_bytes:
            render_responsive_image(
                image_bytes,
                caption=(
                    announcement.image_original_filename
                    or "Announcement cover image"
                ),
                max_width=900,
                max_height=440,
            )

        with st.expander(
            "Read Full Announcement",
            expanded=True,
        ):
            st.markdown(announcement.content)


def _render_overview(
    current_user: AuthenticatedUser,
    announcements,
) -> None:
    """Render lifecycle metrics, table, and announcement preview."""

    statuses = [
        AnnouncementService.display_status(item)
        for item in announcements
    ]
    metrics = (
        ("Total", len(announcements)),
        (
            "Published",
            statuses.count("Published"),
        ),
        (
            "Scheduled",
            statuses.count("Scheduled"),
        ),
        (
            "Drafts",
            statuses.count("Draft"),
        ),
    )

    for column, (label, value) in zip(
        st.columns(4),
        metrics,
    ):
        with column:
            st.metric(label, value)

    if not announcements:
        st.info(
            "No company announcement has been created yet."
        )
        return

    render_admin_table(
        [
            {
                "Announcement ID": item.public_id,
                "Title": item.title,
                "Category": item.category,
                "Status": (
                    AnnouncementService.display_status(
                        item
                    )
                ),
                "Pinned": (
                    "Yes" if item.is_pinned else "No"
                ),
                "Cover Image": (
                    "Yes"
                    if item.image_storage_path
                    else "No"
                ),
                "Publish Date": _display_datetime(
                    item.publish_at
                ),
                "Expiry": _display_datetime(
                    item.expires_at
                ),
            }
            for item in announcements
        ],
        key="admin-announcement-overview",
        min_width=1350,
        column_widths=(
            "140px",
            "260px",
            "170px",
            "120px",
            "85px",
            "110px",
            "180px",
            "180px",
        ),
    )

    options = {
        item.id: (
            f"{item.public_id} · {item.title}"
        )
        for item in announcements
    }
    selected_id = st.selectbox(
        "Preview Announcement",
        options=list(options),
        format_func=lambda value: options[value],
        key="announcement_preview_selector",
    )
    selected = next(
        item
        for item in announcements
        if item.id == selected_id
    )
    image_map = _read_image_map(
        current_user,
        [selected],
    )

    _render_preview(
        selected,
        image_bytes=image_map.get(selected.id),
    )


def _render_create(
    current_user: AuthenticatedUser,
) -> None:
    """Create a draft or publish/schedule a new post."""

    settings = get_settings()
    today = date.today()

    st.info(
        "Use Company Activity for photos of recent events. "
        "Use Company Announcement, Reminder, HR Update, or "
        "Emergency Notice for formal information dissemination."
    )

    with st.form(
        "create_announcement_form",
        clear_on_submit=False,
    ):
        title = st.text_input(
            "Announcement Title *",
            max_chars=180,
        )
        category = st.selectbox(
            "Category *",
            options=ANNOUNCEMENT_CATEGORIES,
        )
        summary = st.text_area(
            "Short Summary *",
            max_chars=500,
            height=110,
            help=(
                "This appears in the employee dashboard card "
                "and notification center."
            ),
        )
        content = st.text_area(
            "Full Announcement *",
            max_chars=20000,
            height=260,
            help=(
                "Basic Markdown such as headings, bullets, and "
                "numbered steps is supported."
            ),
        )
        cover_image = st.file_uploader(
            "Cover Image (Optional)",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            help=(
                f"Maximum {settings.announcement_upload_max_mb} MB."
            ),
        )

        date_left, date_right = st.columns(2)

        with date_left:
            publish_date = st.date_input(
                "Publish Date",
                value=today,
                min_value=today,
            )

        with date_right:
            expiry_enabled = st.checkbox(
                "Set Expiry Date",
                value=False,
            )
            expiry_date = st.date_input(
                "Expiry Date",
                value=max(
                    today,
                    publish_date,
                ),
                min_value=publish_date,
                disabled=not expiry_enabled,
            )

        is_pinned = st.checkbox(
            "Pin on Employee Dashboard",
            value=False,
            help=(
                "Pinned posts are shown before normal announcements."
            ),
        )

        draft_clicked = st.form_submit_button(
            "Save as Draft",
            use_container_width=True,
        )
        publish_clicked = st.form_submit_button(
            "Publish / Schedule",
            type="primary",
            use_container_width=True,
        )

    if not draft_clicked and not publish_clicked:
        return

    try:
        values = _announcement_input(
            current_user=current_user,
            title=title,
            category=category,
            summary=summary,
            content=content,
            is_pinned=is_pinned,
            publish_date=publish_date,
            expiry_enabled=expiry_enabled,
            expiry_date=expiry_date,
        )

        with st.spinner(
            "Saving company announcement…"
        ):
            with SessionFactory() as session:
                announcement = AnnouncementService(
                    session
                ).create(
                    values,
                    actor_user_id=current_user.user_id,
                    publish=publish_clicked,
                    image_filename=(
                        cover_image.name
                        if cover_image
                        else None
                    ),
                    image_bytes=(
                        cover_image.getvalue()
                        if cover_image
                        else None
                    ),
                    image_mime_type=(
                        cover_image.type
                        if cover_image
                        else None
                    ),
                )

        status = AnnouncementService.display_status(
            announcement
        )
        set_operation_feedback(
            (
                f"{announcement.public_id} saved as "
                f"{status}."
            ),
            namespace="announcements",
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))


def _render_manage(
    current_user: AuthenticatedUser,
    announcements,
) -> None:
    """Edit, publish, archive, or restore an existing post."""

    if not announcements:
        st.info(
            "Create an announcement before opening management controls."
        )
        return

    settings = get_settings()
    today = date.today()
    options = {
        item.id: (
            f"{item.public_id} · "
            f"{item.title} · "
            f"{AnnouncementService.display_status(item)}"
        )
        for item in announcements
    }
    selected_id = st.selectbox(
        "Select Announcement",
        options=list(options),
        format_func=lambda value: options[value],
        key="manage_announcement_selector",
    )
    selected = next(
        item
        for item in announcements
        if item.id == selected_id
    )

    image_map = _read_image_map(
        current_user,
        [selected],
    )
    existing_image = image_map.get(selected.id)

    if existing_image:
        render_responsive_image(
            existing_image,
            caption=(
                selected.image_original_filename
                or "Current cover image"
            ),
            max_width=520,
            max_height=320,
        )

    publish_date_default = _local_date(
        selected.publish_at,
        fallback=today,
    )
    expiry_enabled_default = (
        selected.expires_at is not None
    )
    expiry_date_default = _local_date(
        selected.expires_at,
        fallback=max(
            today,
            publish_date_default,
        ),
    )

    with st.form(
        f"manage_announcement_form_{selected.id}"
    ):
        title = st.text_input(
            "Announcement Title *",
            value=selected.title,
            max_chars=180,
        )
        category = st.selectbox(
            "Category *",
            options=ANNOUNCEMENT_CATEGORIES,
            index=ANNOUNCEMENT_CATEGORIES.index(
                selected.category
                if selected.category
                in ANNOUNCEMENT_CATEGORIES
                else ANNOUNCEMENT_CATEGORIES[0]
            ),
        )
        summary = st.text_area(
            "Short Summary *",
            value=selected.summary,
            max_chars=500,
            height=110,
        )
        content = st.text_area(
            "Full Announcement *",
            value=selected.content,
            max_chars=20000,
            height=260,
        )
        replacement_image = st.file_uploader(
            "Replace Cover Image",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            help=(
                f"Maximum {settings.announcement_upload_max_mb} MB."
            ),
        )
        remove_image = st.checkbox(
            "Remove Current Cover Image",
            value=False,
            disabled=not bool(
                selected.image_storage_path
            ),
        )

        date_left, date_right = st.columns(2)

        with date_left:
            publish_date = st.date_input(
                "Publish Date",
                value=publish_date_default,
            )

        with date_right:
            expiry_enabled = st.checkbox(
                "Set Expiry Date",
                value=expiry_enabled_default,
            )
            expiry_date = st.date_input(
                "Expiry Date",
                value=max(
                    expiry_date_default,
                    publish_date,
                ),
                min_value=publish_date,
                disabled=not expiry_enabled,
            )

        is_pinned = st.checkbox(
            "Pin on Employee Dashboard",
            value=selected.is_pinned,
        )

        save_clicked = st.form_submit_button(
            "Save Changes",
            use_container_width=True,
        )
        publish_clicked = st.form_submit_button(
            "Publish / Schedule",
            type="primary",
            use_container_width=True,
        )

    st.divider()
    delete_confirmed = st.checkbox(
        "I understand that Delete moves this announcement to Archive.",
        value=False,
        key=f"confirm_delete_announcement_{selected.id}",
        help=(
            "The announcement is retained in the database and can be "
            "restored later from the Archive tab."
        ),
    )
    delete_clicked = st.button(
        "Delete Announcement",
        use_container_width=True,
        disabled=not delete_confirmed,
        key=f"delete_announcement_{selected.id}",
    )

    if not any(
        (
            save_clicked,
            publish_clicked,
            delete_clicked,
        )
    ):
        return

    try:
        values = _announcement_input(
            current_user=current_user,
            title=title,
            category=category,
            summary=summary,
            content=content,
            is_pinned=is_pinned,
            publish_date=publish_date,
            expiry_enabled=expiry_enabled,
            expiry_date=expiry_date,
        )

        with st.spinner(
            "Updating company announcement…"
        ):
            with SessionFactory() as session:
                service = AnnouncementService(
                    session
                )

                if delete_clicked:
                    announcement = service.move_to_archive(
                        company_id=current_user.company_id,
                        announcement_id=selected.id,
                        actor_user_id=current_user.user_id,
                    )
                else:
                    announcement = service.update(
                        announcement_id=selected.id,
                        values=values,
                        actor_user_id=current_user.user_id,
                        publish=publish_clicked,
                        replacement_filename=(
                            replacement_image.name
                            if replacement_image
                            else None
                        ),
                        replacement_bytes=(
                            replacement_image.getvalue()
                            if replacement_image
                            else None
                        ),
                        replacement_mime_type=(
                            replacement_image.type
                            if replacement_image
                            else None
                        ),
                        remove_image=remove_image,
                    )

        feedback_message = (
            f"{announcement.public_id} moved to Archive. "
            "It is no longer displayed to employees and was not "
            "permanently deleted."
            if delete_clicked
            else (
                f"{announcement.public_id} updated. "
                f"Status: "
                f"{AnnouncementService.display_status(announcement)}."
            )
        )
        set_operation_feedback(
            feedback_message,
            namespace="announcements",
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))


def _render_archive(
    current_user: AuthenticatedUser,
    archived_announcements,
) -> None:
    """Display soft-deleted announcements and allow draft restoration."""

    st.caption(
        "Deleted announcements are retained here. They are hidden from "
        "employees and can be restored as drafts."
    )

    if not archived_announcements:
        st.info(
            "The announcement Archive is empty."
        )
        return

    render_admin_table(
        [
            {
                "Announcement ID": item.public_id,
                "Title": item.title,
                "Category": item.category,
                "Archived At": _display_datetime(
                    item.archived_at
                ),
                "Original Publish Date": _display_datetime(
                    item.publish_at
                ),
            }
            for item in archived_announcements
        ],
        key="archived-announcement-table",
        min_width=1000,
        column_widths=(
            "150px",
            "300px",
            "180px",
            "190px",
            "190px",
        ),
    )

    options = {
        item.id: (
            f"{item.public_id} · {item.title}"
        )
        for item in archived_announcements
    }
    selected_id = st.selectbox(
        "Select Archived Announcement",
        options=list(options),
        format_func=lambda value: options[value],
        key="archived_announcement_selector",
    )
    selected = next(
        item
        for item in archived_announcements
        if item.id == selected_id
    )
    image_map = _read_image_map(
        current_user,
        [selected],
    )

    _render_preview(
        selected,
        image_bytes=image_map.get(selected.id),
    )

    if st.button(
        "Restore to Draft",
        type="primary",
        use_container_width=True,
        key=f"restore_archived_announcement_{selected.id}",
    ):
        try:
            with st.spinner(
                "Restoring announcement as draft…"
            ):
                with SessionFactory() as session:
                    restored = AnnouncementService(
                        session
                    ).restore_archived(
                        company_id=current_user.company_id,
                        announcement_id=selected.id,
                        actor_user_id=current_user.user_id,
                    )

            set_operation_feedback(
                (
                    f"{restored.public_id} restored as Draft. "
                    "Review and publish it when ready."
                ),
                namespace="announcements",
            )
            st.rerun()

        except ValueError as error:
            st.error(str(error))


def render_admin_announcements_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render the company-wide announcement publishing module."""

    st.title("Announcements")
    st.caption(
        "Publish formal information, recent company activities, "
        "events, reminders, and urgent notices to the Employee Portal."
    )
    render_operation_feedback(
        namespace="announcements"
    )

    with SessionFactory() as session:
        service = AnnouncementService(session)
        service.reconcile_publications(
            company_id=current_user.company_id
        )
        announcements = service.list_for_admin(
            current_user.company_id
        )

    active_announcements = [
        item
        for item in announcements
        if item.status != "archived"
    ]
    archived_announcements = [
        item
        for item in announcements
        if item.status == "archived"
    ]

    (
        overview_tab,
        create_tab,
        manage_tab,
        archive_tab,
    ) = st.tabs(
        [
            "Overview",
            "Create Announcement",
            "Manage Announcements",
            f"Archive ({len(archived_announcements)})",
        ]
    )

    with overview_tab:
        _render_overview(
            current_user,
            active_announcements,
        )

    with create_tab:
        _render_create(current_user)

    with manage_tab:
        _render_manage(
            current_user,
            active_announcements,
        )

    with archive_tab:
        _render_archive(
            current_user,
            archived_announcements,
        )
