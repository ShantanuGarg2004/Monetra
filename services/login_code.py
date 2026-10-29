"""One-time sign-in codes. The code is emailed to the account address and stored only as a hash."""
from __future__ import annotations

import hashlib
import logging
import secrets

from database.repository import consume_login_code, get_open_challenge, replace_challenge
from services.emailer import send_email
from services.mail_content import compose
from services.verification import VerificationStoreError, inspect_challenge

logger = logging.getLogger(__name__)

PURPOSE = "login_code"
INVALID_CODE = "That code is incorrect or expired."
CODE_MINUTES = 10


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def code_message(email: str) -> str:
    return f"We sent a sign-in code to {email}."


def unconfirmed_message(email: str) -> str:
    return (
        f"Confirm the signup link we sent to {email}. "
        "That link is only for creating the account. Signing in after that uses a code."
    )


def send_login_code(account: dict):
    """Mint a 10-minute code and email it to account['email'].

    Returns ('sent', None), ('limited', decision), or ('failed', None).
    A limited send leaves any older code in place.
    """
    from services.rate_limit.gateway import get_gateway

    recipient = (account.get("email") or "").strip().lower()
    gateway = get_gateway()
    if gateway is not None:
        decision = gateway.note_login_code(recipient)
        if decision is not None and not decision.allowed:
            logger.warning("Sign-in code was not sent for account %s", account["id"])
            return "limited", decision
    raw = generate_login_code()
    replace_challenge(
        int(account["id"]),
        PURPOSE,
        _hash(raw),
        target_email=recipient,
        minutes=CODE_MINUTES,
    )
    text, html = compose(
        title="Your Monetra sign-in code",
        to_address=recipient,
        paragraphs=[
            "Enter this code to finish signing in. It works once.",
            "After the account is confirmed, Monetra sends a code like this at sign-in. The signup link is not used again.",
        ],
        code=raw,
        expiry="This code expires in 10 minutes.",
    )
    ok = send_email(recipient, "Your Monetra sign-in code", text, html)
    if not ok:
        logger.warning("Sign-in code was not accepted for account %s", account["id"])
        return "failed", None
    return "sent", None


def confirm_login_code(email: str, raw: str):
    """Return the account when the code matches a live sign-in challenge. Otherwise None."""
    from database.repository import get_account_by_email

    account = get_account_by_email(email)
    if not account or account.get("email_verified_at") is None:
        return None
    row = get_open_challenge(int(account["id"]), PURPOSE)
    if row is None:
        return None
    if inspect_challenge(int(row["id"]), raw, PURPOSE) != "ok":
        return None
    if not consume_login_code(int(row["id"]), _hash(raw)):
        return None
    return get_account_by_email(email)


__all__ = [
    "INVALID_CODE",
    "VerificationStoreError",
    "code_message",
    "confirm_login_code",
    "send_login_code",
    "unconfirmed_message",
]
