"""Session-local authentication. No credentials are persisted or globally cached."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


ACCOUNT_KEY = "auth_account"
NOTICE_KEY = "auth_notice"
PRIVATE_KEYS = (ACCOUNT_KEY, NOTICE_KEY, "auth_email", "auth_password", "auth_mode")


@dataclass
class Account:
    # SDK objects contain tokens: exclude them from diagnostic representations.
    client: Any = field(repr=False)
    session: Any = field(repr=False)
    user_id: str
    email: str
    profile_ready: bool = False


def create_auth_client():
    """Read only the publishable credential, and create a fresh client per login."""
    import streamlit as st
    from supabase import ClientOptions, create_client

    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("Invalid authentication configuration")
    if not isinstance(key, str) or not key.startswith("sb_publishable_"):
        raise ValueError("A Supabase publishable key is required")
    return create_client(
        url, key,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )


def current_account(state):
    """Refresh on reruns through the SDK; it retains rotated tokens in memory."""
    account = state.get(ACCOUNT_KEY)
    if account is None:
        return None
    try:
        session = account.client.auth.get_session()
        if session is None or session.user.id != account.user_id:
            raise ValueError("Session unavailable")
        account.session = session
        account.email = session.user.email or ""
    except Exception:
        # Never display backend exception strings: they can contain credentials.
        clear_private_state(state)
        state[NOTICE_KEY] = ("warning", "Your session is unavailable. Please log in again.")
        return None
    return account


def clear_private_state(state):
    for key in list(state):
        if key.startswith("library_"):
            state.pop(key, None)
    for key in PRIVATE_KEYS:
        state.pop(key, None)


def ensure_profile(account):
    """Create or touch the authenticated user's profile without replacing metadata."""
    # Omitted columns retain their values on conflict. On insert, created_at
    # uses its database default and display_name remains nullable.
    account.client.table("profiles").upsert(
        {"user_id": account.user_id,
         "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="user_id",
    ).execute()


def sync_profile(state):
    account = state.get(ACCOUNT_KEY)
    if account is None:
        return
    try:
        ensure_profile(account)
        account.profile_ready = True
        state.pop(NOTICE_KEY, None)
    except Exception:
        account.profile_ready = False
        state[NOTICE_KEY] = (
            "warning", "You are signed in, but profile setup is unavailable. Please retry."
        )


def authenticate(state, email, password, *, signup=False):
    """Accept identity only from the provider response, never from a widget UID."""
    if state.get(ACCOUNT_KEY) is not None:
        return
    state.pop(NOTICE_KEY, None)
    email = email.strip()
    if not email or not password:
        state[NOTICE_KEY] = ("error", "Enter your email and password.")
        return
    try:
        client = create_auth_client()
        credentials = {"email": email, "password": password}
        response = (client.auth.sign_up(credentials) if signup
                    else client.auth.sign_in_with_password(credentials))
        session = response.session
        if session is None:
            state[NOTICE_KEY] = (
                "warning", "No signed-in session was returned. Please check your account settings and log in."
            )
            return
        user = session.user
        if not user.id:
            raise ValueError("Missing identity")
        account = Account(client, session, user.id, user.email or "")
        state[ACCOUNT_KEY] = account
    except Exception as error:
        messages = {
            "invalid_credentials": "Email or password is incorrect.",
            "weak_password": "Please choose a stronger password.",
            "email_address_invalid": "Please enter a valid email address.",
            "email_not_confirmed": "This account cannot log in until its email is confirmed.",
            "user_already_exists": "Unable to create this account. Try logging in.",
            "email_exists": "Unable to create this account. Try logging in.",
            "over_request_rate_limit": "Too many attempts. Please try again later.",
        }
        message = messages.get(getattr(error, "code", None),
                               "Authentication is unavailable. Please try again later.")
        state[NOTICE_KEY] = ("error", message)
        return
    # A profile outage must not misrepresent a successful signup as a failed one.
    sync_profile(state)


def logout(state):
    account = state.get(ACCOUNT_KEY)
    failed = False
    try:
        if account is not None:
            account.client.auth.sign_out({"scope": "local"})
    except Exception:
        failed = True
    finally:
        clear_private_state(state)
    state[NOTICE_KEY] = (
        ("warning", "Signed out of this app. Server sign-out could not be confirmed.")
        if failed else ("success", "You are signed out.")
    )
