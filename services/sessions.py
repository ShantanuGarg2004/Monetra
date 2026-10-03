"""Signed session cookie. itsdangerous already ships with Flask."""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import Config

COOKIE_NAME = "finpilot_session"
MAX_AGE_SECONDS = 12 * 60 * 60


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.SESSION_SECRET, salt="finpilot-session")


def issue_token(account_id: int, session_version: int) -> str:
    return _serializer().dumps(
        {"account_id": int(account_id), "session_version": int(session_version)}
    )


def read_token(token: str) -> dict | None:
    try:
        data = _serializer().loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "account_id" not in data:
        return None
    return data


def _cookie_flags():
    """Local Vite proxy stays SameSite=Lax. Vercel→Railway needs None + Secure."""
    local = Config.FLASK_ENV in ("development", "dev", "local")
    if local:
        return {"secure": False, "samesite": "Lax"}
    return {"secure": True, "samesite": "None"}


def attach_cookie(response, account_id: int, session_version: int):
    flags = _cookie_flags()
    response.set_cookie(
        COOKIE_NAME,
        issue_token(account_id, session_version),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=flags["secure"],
        samesite=flags["samesite"],
        path="/",
    )
    return response


def clear_cookie(response):
    flags = _cookie_flags()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=flags["secure"],
        samesite=flags["samesite"],
    )
    return response
