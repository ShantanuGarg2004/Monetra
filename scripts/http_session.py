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


def login_cookie(base_url: str, email: str, password: str) -> str:
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        headers = resp.headers.get_all("Set-Cookie") or []
        resp.read()
    for header in headers:
        if "finpilot_access=" in header:
            return cookie_pair(header)
    raise ValueError("login did not set finpilot_access")
