"""Access cookie plus a per-device refresh secret.

The access cookie is signed and lasts 15 minutes. The refresh cookie is an
opaque secret, stored as SHA-256, and expires 7 days after the session row
was created. Refresh rotates that secret and does not move the expiry.
"""
import hashlib
import secrets
from datetime import datetime, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config

ACCESS_COOKIE = "finpilot_access"
REFRESH_COOKIE = "finpilot_refresh"
# Older browsers still hold this name. Logout and sign-in clear it.
LEGACY_COOKIE = "finpilot_session"
COOKIE_NAME = ACCESS_COOKIE
ACCESS_MAX_AGE_SECONDS = 15 * 60
REFRESH_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
REFRESH_PATH = "/api/auth/refresh"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.SESSION_SECRET, salt="finpilot-access")


def _hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def issue_token(account_id: int, session_id: int, session_version: int) -> str:
    return _serializer().dumps({
        "account_id": int(account_id),
        "session_id": int(session_id),
        "session_version": int(session_version),
    })


def read_token(token: str) -> dict | None:
    try:
        data = _serializer().loads(token, max_age=ACCESS_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    if "account_id" not in data or "session_id" not in data or "session_version" not in data:
        return None
    return data


def _cookie_flags():
    """Local Vite proxy stays SameSite=Lax. Vercel→Railway needs None + Secure."""
    local = Config.FLASK_ENV in ("development", "dev", "local")
    if local:
        return {"secure": False, "samesite": "Lax"}
    return {"secure": True, "samesite": "None"}


def refresh_cookie_max_age(expires_at: datetime) -> int:
    remaining = int((_as_utc(expires_at) - datetime.now(timezone.utc)).total_seconds())
    if remaining < 0:
        return 0
    return remaining


def _session_open(row: dict) -> bool:
    if row.get("revoked_at") is not None:
        return False
    expires_at = row.get("expires_at")
    if expires_at is None:
        return False
    return _as_utc(expires_at) > datetime.now(timezone.utc)


def refresh_session_subject(raw: str) -> str:
    """Bucket subject for one refresh cookie. Unknown secrets share one subject."""
    from database.repository import find_session_by_secret

    if not raw:
        return "session:unknown"
    row = find_session_by_secret(_hash_secret(raw))
    if row is None:
        return "session:unknown"
    return f"session:{int(row['id'])}"


def revoke_presented_refresh(raw: str) -> None:
    """Revoke the one session that matches this refresh secret, current or previous."""
    from database.repository import find_session_by_secret, revoke_session

    if not raw:
        return
    row = find_session_by_secret(_hash_secret(raw))
    if row is not None:
        revoke_session(int(row["id"]))


def open_session(account_id: int, user_agent: str) -> dict:
    """Insert one device session and return the raw refresh secret once."""
    from database.repository import insert_session

    raw = secrets.token_urlsafe(32)
    row = insert_session(int(account_id), _hash_secret(raw), user_agent)
    return {
        "session_id": int(row["id"]),
        "refresh_secret": raw,
        "expires_at": row["expires_at"],
    }


def consume_refresh_secret(raw: str):
    """Rotate a live refresh secret, or revoke the session when an old one is replayed.

    Returns a dict with the new secret, the string ``reused``, or None.
    """
    from database.repository import (
        find_session_by_secret,
        revoke_session,
        rotate_session_secret,
    )

    if not raw:
        return None
    digest = _hash_secret(raw)
    row = find_session_by_secret(digest)
    if row is None or not _session_open(row):
        return None
    if row["previous_secret_hash"] == digest and row["secret_hash"] != digest:
        revoke_session(int(row["id"]))
        return "reused"
    if row["secret_hash"] != digest:
        return None
    new_raw = secrets.token_urlsafe(32)
    updated = rotate_session_secret(int(row["id"]), digest, _hash_secret(new_raw))
    if updated is None:
        again = find_session_by_secret(digest)
        if (
            again
            and again["previous_secret_hash"] == digest
            and again["secret_hash"] != digest
            and _session_open(again)
        ):
            revoke_session(int(again["id"]))
            return "reused"
        return None
    return {
        "account_id": int(updated["account_id"]),
        "session_id": int(updated["id"]),
        "refresh_secret": new_raw,
        "expires_at": updated["expires_at"],
    }


def attach_cookies(response, account_id: int, session_id: int, session_version: int, refresh_secret: str, refresh_max_age: int):
    flags = _cookie_flags()
    response.set_cookie(
        ACCESS_COOKIE,
        issue_token(account_id, session_id, session_version),
        max_age=ACCESS_MAX_AGE_SECONDS,
        httponly=True,
        secure=flags["secure"],
        samesite=flags["samesite"],
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_secret,
        max_age=refresh_max_age,
        httponly=True,
        secure=flags["secure"],
        samesite=flags["samesite"],
        path=REFRESH_PATH,
    )
    return response


def clear_cookies(response):
    flags = _cookie_flags()
    for name, path in (
        (ACCESS_COOKIE, "/"),
        (REFRESH_COOKIE, REFRESH_PATH),
        (LEGACY_COOKIE, "/"),
    ):
        response.delete_cookie(
            name,
            path=path,
            secure=flags["secure"],
            samesite=flags["samesite"],
        )
    return response
