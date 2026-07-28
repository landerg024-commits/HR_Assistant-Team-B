import streamlit as st


def render_placeholder_page(page_name: str) -> None:
    st.title(page_name)
    html = f'<div class="hr-placeholder"><b>{page_name}</b><br><br>This page will be implemented in its assigned module.</div>'
    st.markdown(html, unsafe_allow_html=True)
