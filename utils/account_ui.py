"""Small account panel; search and navigation do not depend on authentication."""

import streamlit as st

from utils.auth import NOTICE_KEY, authenticate, current_account, logout, sync_profile


def submit_account():
    email = st.session_state.get("auth_email", "")
    password = st.session_state.get("auth_password", "")
    signup = st.session_state.get("auth_mode") == "Sign up"
    # Callbacks run before widget rendering, so the password can be cleared safely.
    st.session_state["auth_password"] = ""
    authenticate(st.session_state, email, password, signup=signup)


def render_account():
    account = current_account(st.session_state)
    with st.sidebar:
        with st.expander("Account", expanded=account is not None):
            notice = st.session_state.get(NOTICE_KEY)
            if notice:
                level, message = notice
                getattr(st, level)(message)
            if account is not None:
                st.caption("Signed in as")
                st.text(account.email)
                if not account.profile_ready:
                    st.button("Retry profile setup", key="auth_retry_profile",
                              on_click=sync_profile, args=(st.session_state,))
                st.button("Log out", key="auth_logout", on_click=logout,
                          args=(st.session_state,))
            else:
                st.caption("An account is optional. Browse and search as a guest.")
                st.radio("Account action", ["Log in", "Sign up"], key="auth_mode",
                         horizontal=True, label_visibility="collapsed")
                with st.form("auth_form", clear_on_submit=True, enter_to_submit=False):
                    st.text_input("Email", key="auth_email")
                    st.text_input("Password", type="password", key="auth_password")
                    st.form_submit_button(st.session_state.auth_mode,
                                          on_click=submit_account)
