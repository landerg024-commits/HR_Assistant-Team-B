import streamlit as st


def render_quick_actions() -> None:
    st.subheader('Quick Actions')
    actions = [
        ('Apply for Leave', 'Submit a new leave request'),
        ('Check Leave Balance', 'View your leave entitlement'),
        ('Request Document', 'Request an HR document'),
        ('Raise a Concern', 'Report an issue or concern'),
    ]
    for title, text in actions:
        html = f'<div class="hr-card" style="min-height:auto;margin-bottom:12px"><div class="hr-title">{title}</div><div class="hr-muted">{text}</div></div>'
        st.markdown(html, unsafe_allow_html=True)
