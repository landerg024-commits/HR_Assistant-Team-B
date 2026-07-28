"""Administrator dashboard with company-scoped summary metrics."""

import streamlit as st
from sqlalchemy import func, select
from authentication.current_user import AuthenticatedUser
from database.session import SessionFactory
from models.employee import Employee
from models.user import User


def render_admin_dashboard_page(current_user: AuthenticatedUser) -> None:
    """Display company-scoped user and employee totals."""
    st.title('Admin Dashboard')
    st.caption('Secure administration access is active.')

    with SessionFactory() as session:
        user_count = session.scalar(
            select(func.count(User.id)).where(User.company_id == current_user.company_id)
        ) or 0
        active_user_count = session.scalar(
            select(func.count(User.id)).where(
                User.company_id == current_user.company_id,
                User.is_active.is_(True),
            )
        ) or 0
        employee_count = session.scalar(
            select(func.count(Employee.id)).where(
                Employee.company_id == current_user.company_id
            )
        ) or 0

    columns = st.columns(4)
    metrics = (
        ('Employees', employee_count),
        ('User Accounts', user_count),
        ('Active Accounts', active_user_count),
        ('Role', ("Admin" if current_user.clearance == 1 else "User")),
    )
    for column, (label, value) in zip(columns, metrics):
        with column:
            st.metric(label, value)

    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hr-placeholder">'
        '<strong>Employee Master Record Active</strong><br><br>'
        'Use Employees to manage employee information, departments, '
        'training, login accounts, employment status, and clearance.'
        '</div>',
        unsafe_allow_html=True,
    )
