"""Issue 3: the session cookie is signed with SESSION_SECRET."""
import json

import pytest

import config
import database.db as db_mod
from app import create_app
from database.repository import get_account_by_email, get_session_by_id, issue_api_credential, mark_email_verified
from tests.auth_client import complete_login
from services.rate_limit import gateway as gw_mod
import services.sessions as sessions
from services.sessions import issue_token, read_token


def test_token_fails_when_the_session_secret_changes(monkeypatch):
    monkeypatch.setattr(sessions.Config, "SESSION_SECRET", "a" * 32)
    token = issue_token(1, 4, 1)
    assert read_token(token)["account_id"] == 1
    assert read_token(token)["session_id"] == 4
    monkeypatch.setattr(sessions.Config, "SESSION_SECRET", "b" * 32)
    assert read_token(token) is None


def test_cookie_flags_are_lax_locally_and_none_in_production(monkeypatch):
    monkeypatch.setattr(sessions.Config, "FLASK_ENV", "development")
    assert sessions._cookie_flags() == {"secure": False, "samesite": "Lax"}
    monkeypatch.setattr(sessions.Config, "FLASK_ENV", "production")
    assert sessions._cookie_flags() == {"secure": True, "samesite": "None"}


def test_production_login_sets_samesite_none(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / "cookie-flags.db"))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "production")
    monkeypatch.setattr(config.Config, "CORS_ORIGINS", ["https://app.example"])
    monkeypatch.setattr(sessions.Config, "FLASK_ENV", "production")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    body = {
        "email": "prod-cookie@example.com",
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    }
    signed = client.post(
        "/api/auth/signup",
        data=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert signed.status_code == 201
    cookie_header = "\n".join(signed.headers.getlist("Set-Cookie"))
    assert "finpilot_access=" in cookie_header
    assert "finpilot_refresh=" in cookie_header
    assert "Path=/api/auth/refresh" in cookie_header
    assert cookie_header.count("SameSite=None") >= 2
    assert cookie_header.count("Secure") >= 2


def test_validate_rejects_a_session_secret_that_matches_the_api_key(monkeypatch):
    monkeypatch.setattr(config.Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(config.Config, "API_SECRET_KEY", "same-secret-value-that-is-long-enough")
    monkeypatch.setattr(config.Config, "SESSION_SECRET", "same-secret-value-that-is-long-enough")
    with pytest.raises(EnvironmentError) as excinfo:
        config.Config.validate()
    assert "SESSION_SECRET" in str(excinfo.value)


def test_validate_rejects_a_missing_session_secret(monkeypatch):
    monkeypatch.setattr(config.Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(config.Config, "API_SECRET_KEY", "api-secret-value-not-the-session")
    monkeypatch.setattr(config.Config, "SESSION_SECRET", None)
    with pytest.raises(EnvironmentError) as excinfo:
        config.Config.validate()
    assert "SESSION_SECRET" in str(excinfo.value)


def test_validate_rejects_a_short_session_secret(monkeypatch):
    monkeypatch.setattr(config.Config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(config.Config, "API_SECRET_KEY", "api-secret-value-not-the-session")
    monkeypatch.setattr(config.Config, "SESSION_SECRET", "too-short")
    with pytest.raises(EnvironmentError) as excinfo:
        config.Config.validate()
    assert "32" in str(excinfo.value)


def _cookies(response):
    found = {}
    for header in response.headers.getlist("Set-Cookie"):
        pair = header.split(";", 1)[0]
        name, value = pair.split("=", 1)
        found[name] = value
    return found


def _client(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    monkeypatch.setattr(sessions.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app


def _signup(client, email):
    return client.post(
        "/api/auth/signup",
        data=json.dumps({
            "email": email,
            "password": "correct-horse",
            "confirm_password": "correct-horse",
        }),
        headers={"Content-Type": "application/json"},
    )


def _login(client, email):
    mark_email_verified(get_account_by_email(email)["id"])
    return complete_login(client, email, "correct-horse")


def test_logout_revokes_that_session_and_leaves_the_version(tmp_path, monkeypatch):
    app = _client(tmp_path, monkeypatch, "session.db")
    client = app.test_client()
    signed = _signup(client, "session@example.com")
    assert signed.status_code == 201
    cookies = _cookies(signed)
    assert "finpilot_access" in cookies
    assert "finpilot_refresh" in cookies
    session_id = read_token(cookies["finpilot_access"])["session_id"]

    assert client.get("/api/auth/me").status_code == 200
    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    account = get_account_by_email("session@example.com")
    assert account["session_version"] == 1
    assert get_session_by_id(session_id)["revoked_at"] is not None

    client.set_cookie("finpilot_access", cookies["finpilot_access"], domain="localhost")
    again = client.get("/api/auth/me")
    assert again.status_code == 401
    assert again.get_json()["code"] == "session_expired"


def test_logout_on_one_device_leaves_the_other_signed_in(tmp_path, monkeypatch):
    app = _client(tmp_path, monkeypatch, "two-devices.db")
    device_a = app.test_client()
    device_b = app.test_client()
    assert _signup(device_a, "two@example.com").status_code == 201
    assert _login(device_b, "two@example.com").status_code == 200

    assert device_a.post("/api/auth/logout").status_code == 200
    gone = device_a.get("/api/auth/me")
    assert gone.status_code == 401
    assert gone.get_json()["code"] == "session_expired"
    assert device_b.get("/api/auth/me").status_code == 200
    assert get_account_by_email("two@example.com")["session_version"] == 1


def test_refresh_rotates_and_reuse_revokes_only_that_session(tmp_path, monkeypatch):
    app = _client(tmp_path, monkeypatch, "refresh.db")
    device_a = app.test_client()
    device_b = app.test_client()
    signed = _signup(device_a, "refresh@example.com")
    first = _cookies(signed)
    session_id = read_token(first["finpilot_access"])["session_id"]
    before = get_session_by_id(session_id)
    assert _login(device_b, "refresh@example.com").status_code == 200

    refreshed = device_a.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    rotated = _cookies(refreshed)
    assert rotated["finpilot_refresh"] != first["finpilot_refresh"]
    after = get_session_by_id(session_id)
    assert after["expires_at"] == before["expires_at"]
    assert after["secret_hash"] != before["secret_hash"]
    assert after["previous_secret_hash"] == before["secret_hash"]
    assert after["revoked_at"] is None
    assert device_a.get("/api/auth/me").status_code == 200

    thief = app.test_client()
    thief.set_cookie(
        "finpilot_refresh",
        first["finpilot_refresh"],
        domain="localhost",
        path="/api/auth/refresh",
    )
    reused = thief.post("/api/auth/refresh")
    assert reused.status_code == 401
    assert reused.get_json()["code"] == "session_expired"
    assert get_session_by_id(session_id)["revoked_at"] is not None
    assert device_a.get("/api/auth/me").status_code == 401
    still = device_b.get("/api/auth/me")
    assert still.status_code == 200
    assert still.get_json()["email"] == "refresh@example.com"


def test_bad_access_cookie_does_not_fall_through_to_an_api_key(tmp_path, monkeypatch):
    app = _client(tmp_path, monkeypatch, "fallthrough.db")
    client = app.test_client()
    assert _signup(client, "key@example.com").status_code == 201
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    raw_key, _row_id = issue_api_credential(account_id, "data-key", ["data"])
    client.set_cookie("finpilot_access", "not-a-real-token", domain="localhost")
    listed = client.get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "session_expired"
