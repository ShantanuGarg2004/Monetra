"""Issue 3: the session cookie is signed with SESSION_SECRET."""
import json

import pytest

import config
import database.db as db_mod
from app import create_app
from database.repository import get_account_by_email
from services.rate_limit import gateway as gw_mod
import services.sessions as sessions
from services.sessions import issue_token, read_token


def test_token_fails_when_the_session_secret_changes(monkeypatch):
    monkeypatch.setattr(sessions.Config, "SESSION_SECRET", "a" * 32)
    token = issue_token(1, 1)
    assert read_token(token)["account_id"] == 1
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
    cookie_header = signed.headers.get("Set-Cookie", "")
    assert "finpilot_session=" in cookie_header
    assert "SameSite=None" in cookie_header
    assert "Secure" in cookie_header


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


def test_login_sets_cookie_and_logout_bumps_session_version(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / "session.db"))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    body = {
        "email": "session@example.com",
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    }
    signed = client.post(
        "/api/auth/signup",
        data=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert signed.status_code == 201
    assert "finpilot_session=" in signed.headers.get("Set-Cookie", "")
    cookie = signed.headers.get("Set-Cookie", "").split(";", 1)[0].split("=", 1)[1]

    assert client.get("/api/auth/me").status_code == 200
    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    account = get_account_by_email("session@example.com")
    assert account["session_version"] == 2

    client.set_cookie("finpilot_session", cookie, domain="localhost")
    again = client.get("/api/auth/me")
    assert again.status_code == 401
    assert again.get_json()["code"] == "session_expired"
