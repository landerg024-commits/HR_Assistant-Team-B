"""Reusable authenticated application top bar with notification bell."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from services.notification_service import NotificationService


def _format_time(value) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo(get_settings().display_timezone)).strftime("%b %d, %I:%M %p")


def _render_notification_bell(current_user: AuthenticatedUser) -> None:
    with SessionFactory() as session:
        service = NotificationService(session)
        unread = service.unread_count(company_id=current_user.company_id, user_id=current_user.user_id)
        recent = service.list_recent(company_id=current_user.company_id, user_id=current_user.user_id, limit=10)

    label = f"🔔 {unread}" if unread else "🔔"
    with st.popover(label, use_container_width=True):
        st.markdown("**Notifications**")
        if not recent:
            st.caption("No notifications yet.")
        else:
            for item in recent:
                marker = "●" if not item.is_read else "○"
                st.markdown(f"**{marker} {item.title}**")
                st.caption(item.message)
                st.caption(_format_time(item.created_at))
                st.divider()
            if unread and st.button("Mark All as Read", use_container_width=True, key="notification_mark_all_read"):
                with SessionFactory() as session:
                    NotificationService(session).mark_all_read(company_id=current_user.company_id, user_id=current_user.user_id)
                st.rerun()


def render_topbar(
    company_name: str,
    current_user: AuthenticatedUser,
    section_name: str = "Employee HR Services",
) -> None:
    """Display company, portal section, identity, and notifications."""

    display_name = current_user.employee_name or current_user.username
    access_label = "Admin" if current_user.clearance == 1 else "User"
    content, bell = st.columns([8.6, 1.4], vertical_alignment="center")
    with content:
        st.markdown(
            f"""
            <div class="hr-topbar">
                <div>
                    <div class="hr-brand">{company_name}</div>
                    <div class="hr-muted">{section_name}</div>
                </div>
                <div class="hr-muted">
                    {display_name} · {access_label}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with bell:
        _render_notification_bell(current_user)
