"""One HTTP call to Resend. Tests replace send_email. No provider SDK."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from config import Config

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Return True when Resend accepts the message. A missing key skips the network.

    `to` is the address that should receive the message. It is not replaced.
    """
    key = (Config.EMAIL_API_KEY or "").strip()
    sender = (Config.EMAIL_FROM or "").strip()
    recipient = (to or "").strip()
    if not key or not sender:
        logger.info("Skipping email send because EMAIL_API_KEY or EMAIL_FROM is unset")
        return False
    if "@" not in recipient:
        logger.warning("Skipping email send because the recipient is not an email address")
        return False
    body = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "text": text,
    }
    if html:
        body["html"] = html
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Monetra",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        logger.warning("Resend rejected mail to %s (%s): %s", recipient, exc.code, detail)
        return False
    except Exception:
        logger.exception("Email send failed")
        return False
