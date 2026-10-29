"""Email verification links. The raw secret is only placed in the message."""
from __future__ import annotations

import hashlib
import logging
import secrets

from config import Config
from database.repository import (
    confirm_verify_challenge,
    get_challenge,
    register_wrong_attempt,
    replace_verify_challenge,
)
from services.emailer import send_email

logger = logging.getLogger(__name__)

INVALID_LINK = "That link is invalid or expired."
SEND_FAILED = "Account created, but the verification email could not be sent. Use resend."


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _link(challenge_id: int, raw: str) -> str:
    origin = (Config.APP_PUBLIC_URL or "http://localhost:5173").rstrip("/")
    return f"{origin}/verify-email?id={int(challenge_id)}&token={raw}"


def send_verification(account: dict) -> bool:
    """Mint a verify_email challenge and send the link. False means the mail was not accepted."""
    raw = secrets.token_urlsafe(32)
    row = replace_verify_challenge(int(account["id"]), _hash(raw))
    text = (
        "Confirm your FinPilot email.\n\n"
        "Open this link and press the confirm button. Opening the link does not use it up.\n"
        f"{_link(row['id'], raw)}\n\n"
        "The link expires in 30 minutes."
    )
    ok = send_email(account["email"], "Confirm your FinPilot email", text)
    if not ok:
        logger.warning("Verification email was not sent for account %s", account["id"])
    return ok


def inspect_challenge(challenge_id: int, raw: str, purpose: str) -> str:
    """Return 'ok' when the secret matches a live row. Does not consume it.

    A wrong secret for a live row counts as one miss. The fifth miss consumes the row.
    """
    if not raw or challenge_id is None:
        return "invalid"
    row = get_challenge(int(challenge_id), purpose)
    if row is None or row["consumed_at"] is not None:
        return "invalid"
    expires_at = row["expires_at"]
    from datetime import datetime, timezone

    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return "invalid"
    if row["secret_hash"] != _hash(raw):
        _count_wrong(int(challenge_id), purpose)
        return "invalid"
    return "ok"


def describe_challenge(challenge_id: int, raw: str) -> str:
    """Return 'ok' or 'invalid'. A matching secret is consumed."""
    if inspect_challenge(challenge_id, raw, "verify_email") != "ok":
        return "invalid"
    if not confirm_verify_challenge(int(challenge_id), _hash(raw)):
        return "invalid"
    return "ok"


def _count_wrong(challenge_id: int, purpose: str) -> None:
    from services.rate_limit.gateway import get_gateway

    gateway = get_gateway()
    if gateway is not None:
        decision = gateway.note_wrong_challenge(challenge_id)
        if decision is not None and not decision.allowed and decision.store_error:
            raise VerificationStoreError(decision)
    register_wrong_attempt(challenge_id, purpose)


class VerificationStoreError(Exception):
    def __init__(self, decision):
        self.decision = decision
