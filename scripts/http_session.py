"""Session cookie for scripts. The deployment API key is not a data credential."""
from __future__ import annotations

import json
import urllib.request


def cookie_pair(set_cookie_header: str) -> str:
    if not set_cookie_header:
        raise ValueError("login did not set finpilot_access")
    pair = set_cookie_header.split(";", 1)[0].strip()
    if not pair.startswith("finpilot_access="):
        raise ValueError("login did not set finpilot_access")
    return pair


def data_headers(session_cookie: str) -> dict:
    """Headers for a data call. No X-API-Key."""
    return {
        "Cookie": session_cookie,
        "Content-Type": "application/json",
    }


def _post(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        headers = resp.headers.get_all("Set-Cookie") or []
        body = json.loads(resp.read().decode("utf-8") or "{}")
    return body, headers


def login_cookie(base_url: str, email: str, password: str, code: str | None = None) -> str:
    root = base_url.rstrip("/")
    body, headers = _post(root + "/api/auth/login", {"email": email, "password": password})
    if body.get("otp_required"):
        if not code:
            raise ValueError("login requires the code sent to " + str(body.get("email") or email))
        _body, headers = _post(root + "/api/auth/login-code", {"email": email, "code": code})
    for header in headers:
        if "finpilot_access=" in header and "finpilot_access=;" not in header:
            return cookie_pair(header)
    raise ValueError("login did not set finpilot_access")
