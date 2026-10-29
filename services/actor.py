"""Who is calling: a session cookie, or a scoped API credential.

The docs password (API_SECRET_KEY) opens local Swagger only. It is not a data actor.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import Request

from config import Config
from database.repository import find_active_api_credential, get_account_by_id, get_live_session
from services.rate_limit.keys import hash_api_key
from services.sessions import ACCESS_COOKIE, read_token


@dataclass(frozen=True)
class Actor:
    """anonymous, user, api_key, or docs. Request code should not grow a second identity."""

    kind: str
    credential: str = ""
    scopes: tuple[str, ...] = ()

    def rate_limit_subject(self) -> str:
        """One bucket per account, whether the caller sent a cookie or a scoped key."""
        if self.kind in ("user", "api_key") and str(self.credential).isdigit():
            return f"acct:{self.credential}"
        return hash_api_key(self.credential)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def presented_credential(req: Request) -> str:
    header = req.headers.get("X-API-Key", "") or ""
    if header:
        return header
    auth = req.authorization
    if auth and auth.password:
        return auth.password
    return ""


def resolve_actor(req: Request) -> Actor | None:
    """Return the caller, or None when the request must be rejected.

    A presented session cookie is resolved first. A bad cookie does not fall
    through to the API key. ``g.auth_error`` is set to ``session_expired`` or
    ``unauthorized`` when the caller cannot continue.
    """
    from flask import g

    token = req.cookies.get(ACCESS_COOKIE, "")
    if token:
        payload = read_token(token)
        session = None
        account = None
        if payload is not None:
            session = get_live_session(int(payload["session_id"]))
            account = get_account_by_id(int(payload["account_id"]))
        version_ok = (
            account is not None
            and session is not None
            and int(session["account_id"]) == int(account["id"])
            and int(account["session_version"]) == int(payload.get("session_version"))
        )
        if version_ok:
            g.auth_error = None
            return Actor(kind="user", credential=str(account["id"]))
        g.auth_error = "session_expired"
        return None

    key = presented_credential(req)
    if key:
        credential = find_active_api_credential(key)
        if credential is not None:
            g.auth_error = None
            return Actor(
                kind="api_key",
                credential=str(credential["account_id"]),
                scopes=credential["scopes"],
            )
        from services.rate_limit.gateway import is_public_docs
        if is_public_docs(req.path) and key == Config.API_SECRET_KEY:
            g.auth_error = None
            return Actor(kind="docs")
        g.auth_error = "unauthorized"
        return None

    g.auth_error = "session_expired"
    return None
