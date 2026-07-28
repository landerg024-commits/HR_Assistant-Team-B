import streamlit as st
from ui.components.quick_actions import render_quick_actions


def render_chat_page() -> None:
    main, side = st.columns([3, 1], gap='large')
    with main:
        st.title('Hello! 👋')
        st.caption('How can I help you today?')
        columns = st.columns(4)
        cards = [
            ('Leave Balance', 'Check your leave balance'),
            ('Leave Policy', 'View leave policy details'),
            ('Health Benefits', 'Learn about health benefits'),
            ('Request Document', 'Request HR documents'),
        ]
        for column, (title, text) in zip(columns, cards):
            with column:
                html = f'<div class="hr-card"><div class="hr-title">{title}</div><div class="hr-muted">{text}</div></div>'
                st.markdown(html, unsafe_allow_html=True)
        st.markdown('<br>', unsafe_allow_html=True)
        st.markdown('<div class="hr-placeholder"><b>Chat Assistant Module Placeholder</b><br><br>Policy search, HR answers, and source references will be added in the Policy Q&A module.</div>', unsafe_allow_html=True)
        st.chat_input('Type your question...', disabled=True)
        st.caption('AI responses can make mistakes. Please verify important information with HR.')
    with side:
        render_quick_actions()
        st.subheader('Announcements')
        st.markdown('<div class="hr-card"><div class="hr-title">No announcements yet</div><div class="hr-muted">Announcement management will be added later.</div></div>', unsafe_allow_html=True)
