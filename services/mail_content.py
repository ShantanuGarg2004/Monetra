"""Plain-text and HTML bodies for account mail. The recipient is named in both."""
from __future__ import annotations

from html import escape

PRODUCT = "Monetra"
SITE = "https://monetra.site"


def compose(
    *,
    title: str,
    to_address: str,
    paragraphs: list[str],
    expiry: str,
    action_label: str | None = None,
    action_url: str | None = None,
    code: str | None = None,
) -> tuple[str, str]:
    """Return (text, html). The action URL, when present, is on its own text line."""
    recipient = (to_address or "").strip()
    text_lines = [
        title,
        "",
        f"This message was sent to {recipient}.",
        "",
        *paragraphs,
        "",
    ]
    if code:
        text_lines.extend([code, ""])
    if action_url:
        if action_label:
            text_lines.append(action_label)
        text_lines.extend([action_url, ""])
    text_lines.extend([
        expiry,
        "If you did not ask for this, you can ignore this email.",
        "",
        PRODUCT,
        SITE,
    ])
    return "\n".join(text_lines), _html(
        title=title,
        recipient=recipient,
        paragraphs=paragraphs,
        expiry=expiry,
        action_label=action_label,
        action_url=action_url,
        code=code,
    )


def _html(
    *,
    title: str,
    recipient: str,
    paragraphs: list[str],
    expiry: str,
    action_label: str | None,
    action_url: str | None,
    code: str | None,
) -> str:
    safe_title = escape(title)
    safe_recipient = escape(recipient)
    body = "".join(f"<p style=\"margin:0 0 16px;font-size:16px;line-height:1.6;color:#3f3a33;\">{escape(part)}</p>" for part in paragraphs)
    code_block = ""
    if code:
        code_block = (
            "<p style=\"margin:8px 0 24px;font-family:ui-monospace,Menlo,Consolas,monospace;"
            "font-size:32px;letter-spacing:0.28em;font-weight:700;color:#1c1915;\">"
            f"{escape(code)}</p>"
        )
    action_block = ""
    if action_url:
        href = escape(action_url, quote=True)
        label = escape(action_label or "Continue")
        action_block = (
            "<p style=\"margin:8px 0 20px;\">"
            f"<a href=\"{href}\" style=\"display:inline-block;background:#1c1915;color:#f7f4ee;"
            "text-decoration:none;font-size:15px;font-weight:600;padding:14px 22px;border-radius:999px;\">"
            f"{label}</a></p>"
            "<p style=\"margin:0 0 8px;font-size:13px;line-height:1.5;color:#6f675d;\">"
            "If the button does not open, paste this address into your browser:</p>"
            f"<p style=\"margin:0 0 20px;font-size:13px;line-height:1.5;word-break:break-all;\">"
            f"<a href=\"{href}\" style=\"color:#8a7340;\">{href}</a></p>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:32px 16px;background:#f3f1ea;font-family:Georgia,'Iowan Old Style',serif;">
    <div style="display:none;max-height:0;overflow:hidden;">{safe_title} This message was sent to {safe_recipient}.</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:18px;">
      <tr>
        <td style="padding:36px 36px 12px;">
          <p style="margin:0 0 20px;font-family:Inter,Arial,sans-serif;font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#8a7340;">{PRODUCT}</p>
          <h1 style="margin:0 0 16px;font-size:28px;line-height:1.25;font-weight:700;color:#1c1915;">{safe_title}</h1>
          <p style="margin:0 0 16px;font-size:14px;line-height:1.5;color:#6f675d;">This message was sent to {safe_recipient}.</p>
          {body}
          {code_block}
          {action_block}
          <p style="margin:0 0 8px;font-size:14px;line-height:1.5;color:#6f675d;">{escape(expiry)}</p>
          <p style="margin:0;font-size:14px;line-height:1.5;color:#6f675d;">If you did not ask for this, you can ignore this email.</p>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 36px 32px;font-family:Inter,Arial,sans-serif;font-size:12px;line-height:1.5;color:#8a8175;">
          {PRODUCT}<br />
          <a href="{SITE}" style="color:#8a8175;text-decoration:none;">{SITE}</a>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
