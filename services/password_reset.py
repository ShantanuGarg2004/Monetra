"""Password reset links. The raw secret is only placed in the message."""
from __future__ import annotations

import hashlib
import logging
import secrets

from config import Config
from database.repository import complete_password_reset, replace_challenge
from services.emailer import send_email
from services.mail_content import compose
from services.verification import INVALID_LINK, VerificationStoreError, inspect_challenge

logger = logging.getLogger(__name__)

FORGOT_MESSAGE = "If an account exists for that email, a reset link is on its way."
RESET_DONE = "Password updated. You will need to sign in again on each device."
PURPOSE = "reset_password"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _link(challenge_id: int, raw: str) -> str:
    origin = (Config.APP_PUBLIC_URL or "http://localhost:5173").rstrip("/")
    return f"{origin}/reset-password?id={int(challenge_id)}&token={raw}"


def send_password_reset(account: dict) -> bool:
    """Mint a reset challenge and send the link. A denied resend bucket sends nothing."""
    from services.rate_limit.gateway import get_gateway

    gateway = get_gateway()
    if gateway is not None:
        decision = gateway.note_resend(account["email"])
        if decision is not None and not decision.allowed:
            logger.warning("Password reset email was not sent for account %s", account["id"])
            return False
    raw = secrets.token_urlsafe(32)
    row = replace_challenge(int(account["id"]), PURPOSE, _hash(raw))
    recipient = (account.get("email") or "").strip().lower()
    link = _link(row["id"], raw)
    text, html = compose(
        title="Reset your password",
        to_address=recipient,
        paragraphs=[
            "A password reset was requested for this Monetra account.",
            "Open the link and choose a new password. Opening the link does not use it up.",
            "You will need to sign in again on each device.",
        ],
        action_label="Choose a new password",
        action_url=link,
        expiry="This link expires in 30 minutes.",
    )
    ok = send_email(recipient, "Reset your Monetra password", text, html)
    if not ok:
        logger.warning("Password reset email was not sent for account %s", account["id"])
    return ok


def reset_password(challenge_id: int, raw: str, password: str) -> str:
    """Return 'ok' or 'invalid'. Success replaces the password and signs every device out."""
    if inspect_challenge(challenge_id, raw, PURPOSE) != "ok":
        return "invalid"
    if not complete_password_reset(int(challenge_id), _hash(raw), password):
        return "invalid"
    return "ok"


__all__ = [
    "FORGOT_MESSAGE",
    "INVALID_LINK",
    "RESET_DONE",
    "VerificationStoreError",
    "reset_password",
    "send_password_reset",
]
