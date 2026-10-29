"""One HTTP call to Resend. Tests replace send_email. No provider SDK."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from config import Config

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, text: str) -> bool:
    """Return True when Resend accepts the message. A missing key skips the network."""
    key = (Config.EMAIL_API_KEY or "").strip()
    sender = (Config.EMAIL_FROM or "").strip()
    if not key or not sender:
        logger.info("Skipping email send because EMAIL_API_KEY or EMAIL_FROM is unset")
        return False
    payload = json.dumps({
        "from": sender,
        "to": [to],
        "subject": subject,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "FinPilot",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.warning("Resend rejected the message (%s)", exc.code)
        return False
    except Exception:
        logger.exception("Email send failed")
        return False
