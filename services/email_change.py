"""Email change. The new address is stored on the challenge until it is confirmed."""
from __future__ import annotations

import hashlib
import logging
import secrets

from config import Config
from database.repository import complete_email_change, replace_challenge
from services.emailer import send_email
from services.mail_content import compose
from services.verification import INVALID_LINK, VerificationStoreError, inspect_challenge

logger = logging.getLogger(__name__)

PURPOSE = "change_email"
CHANGE_ACCEPTED = "Confirm the new address from the link we sent. This address stays until then."
CHANGE_DONE = "Email updated. Sign in again with the new address."
NOTICE_SUBJECT = "Monetra email change requested"
LINK_SUBJECT = "Confirm your new Monetra email"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _link(challenge_id: int, raw: str) -> str:
    origin = (Config.APP_PUBLIC_URL or "http://localhost:5173").rstrip("/")
    return f"{origin}/confirm-email?id={int(challenge_id)}&token={raw}"


def request_email_change(account: dict, new_email: str) -> str:
    """Mint a change_email challenge. Returns 'sent' or 'link_failed'.

    The account email is not updated. A failed notice to the current address
    leaves the challenge unconfirmed.
    """
    raw = secrets.token_urlsafe(32)
    target = new_email.strip().lower()
    row = replace_challenge(int(account["id"]), PURPOSE, _hash(raw), target_email=target)
    link = _link(row["id"], raw)
    link_text, link_html = compose(
        title="Confirm your new email",
        to_address=target,
        paragraphs=[
            "Confirm this address for your Monetra account.",
            "Opening the link does not use it up. Press the confirm button on the page.",
            "You will need to sign in again with this address.",
        ],
        action_label="Confirm new email",
        action_url=link,
        expiry="This link expires in 30 minutes.",
    )
    current = (account.get("email") or "").strip().lower()
    notice_text, notice_html = compose(
        title="Email change requested",
        to_address=current,
        paragraphs=[
            "Someone asked to change the email on this Monetra account.",
            "If this was you, confirm it from the new address. If this was not you, sign in and keep this address.",
        ],
        expiry="No action is required on this address.",
    )
    link_ok = send_email(target, LINK_SUBJECT, link_text, link_html)
    notice_ok = send_email(current, NOTICE_SUBJECT, notice_text, notice_html)
    if not notice_ok:
        logger.warning("Email-change notice was not sent for account %s", account["id"])
    if not link_ok:
        logger.warning("Email-change link was not sent for account %s", account["id"])
        return "link_failed"
    return "sent"


def confirm_email_change(challenge_id: int, raw: str) -> str:
    """Return 'ok' or 'invalid'. A taken address consumes the challenge and does not change the email."""
    if inspect_challenge(challenge_id, raw, PURPOSE) != "ok":
        return "invalid"
    outcome = complete_email_change(int(challenge_id), _hash(raw))
    if outcome == "ok":
        return "ok"
    return "invalid"


__all__ = [
    "CHANGE_ACCEPTED",
    "CHANGE_DONE",
    "INVALID_LINK",
    "VerificationStoreError",
    "confirm_email_change",
    "request_email_change",
]
