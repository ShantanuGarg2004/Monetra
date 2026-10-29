"""Finish a password check with the test sign-in code."""
import json

LOGIN_CODE = "482913"
_JSON = {"Content-Type": "application/json"}


def complete_login(client, email, password="correct-horse"):
    """Post the password, then the fixed test code when a code is required."""
    res = client.post(
        "/api/auth/login",
        data=json.dumps({"email": email, "password": password}),
        headers=_JSON,
    )
    body = res.get_json(silent=True) or {}
    if res.status_code == 200 and body.get("otp_required"):
        res = client.post(
            "/api/auth/login-code",
            data=json.dumps({"email": email, "code": LOGIN_CODE}),
            headers=_JSON,
        )
    return res
