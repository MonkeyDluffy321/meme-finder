"""User-scoped library operations through the existing authenticated client."""

from datetime import datetime, timezone

from utils.auth import current_account


class LibraryError(Exception):
    """Safe, user-facing failure without backend details."""


def _account(state):
    account = current_account(state)
    if account is None:
        raise LibraryError("Please sign in using Account in the sidebar to use your library.")
    return account


def save_meme(state, meme_id):
    account = _account(state)
    try:
        account.client.table("saved_memes").upsert(
            {"user_id": account.user_id, "meme_id": meme_id,
             "created_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="user_id,meme_id", ignore_duplicates=True,
        ).execute()
    except Exception:
        raise LibraryError("Could not save this meme. Please try again.") from None


def unsave_meme(state, meme_id):
    account = _account(state)
    try:
        account.client.table("saved_memes").delete().eq(
            "user_id", account.user_id).eq("meme_id", meme_id).execute()
    except Exception:
        raise LibraryError("Could not unsave this meme. Please try again.") from None


def record_view(state, meme_id):
    account = current_account(state)
    if account is None:
        return
    try:
        account.client.table("recently_viewed").upsert(
            {"user_id": account.user_id, "meme_id": meme_id,
             "last_viewed_at": datetime.now(timezone.utc).isoformat()},
            on_conflict="user_id,meme_id",
        ).execute()
    except Exception:
        raise LibraryError("Could not update recently viewed. Please try again.") from None


def fetch_library(state, *, recent=False):
    """Return ordered IDs; page saved rows to avoid the server's row cap."""
    account = _account(state)
    table, timestamp = (("recently_viewed", "last_viewed_at") if recent
                        else ("saved_memes", "created_at"))
    try:
        ids = []
        offset = 0
        while True:
            query = account.client.table(table).select("user_id,meme_id").eq(
                "user_id", account.user_id).order(timestamp, desc=True).order("meme_id")
            response = (query.limit(50) if recent else query.range(offset, offset + 499)).execute()
            rows = response.data
            ids.extend(row["meme_id"] for row in rows if row["user_id"] == account.user_id)
            if recent or len(rows) < 500:
                return list(dict.fromkeys(ids))[:50] if recent else list(dict.fromkeys(ids))
            offset += 500
    except Exception:
        raise LibraryError("Your library is temporarily unavailable. Please try again.") from None


def resolve_memes(memes, ids):
    """Preserve library order and skip templates no longer in the collection."""
    by_id = {meme["id"]: meme for meme in memes}
    return [by_id[meme_id] for meme_id in ids if meme_id in by_id]
