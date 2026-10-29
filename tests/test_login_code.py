"""Signup mail goes to the form address. Later sign-in uses a code, not the confirm wall."""
import json

import config
import database.db as db_mod
from app import create_app
from database.repository import get_open_challenge, mark_email_verified
from services.rate_limit import gateway as gw_mod
import services.login_code as login_code
import services.verification as verification
from tests.auth_client import LOGIN_CODE


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    monkeypatch.setattr(config.Config, "APP_PUBLIC_URL", "http://localhost:5173")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), headers={"Content-Type": "application/json"})


def _capture(monkeypatch, module):
    sent = []

    def fake_send(to, subject, text, html=None):
        sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return True

    monkeypatch.setattr(module, "send_email", fake_send)
    return sent


def _signup(client, email):
    return _post(client, "/api/auth/signup", {
        "email": email,
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    })


def test_signup_link_is_addressed_to_the_form_email(tmp_path, monkeypatch):
    sent = _capture(monkeypatch, verification)
    client = _app(tmp_path, monkeypatch, "signup-mail.db")
    created = _signup(client, "Owner@Example.com")
    assert created.status_code == 201
    assert sent[0]["to"] == "owner@example.com"
    assert "owner@example.com" in sent[0]["text"]
    assert "owner@example.com" in sent[0]["html"]
    assert "Monetra" in sent[0]["html"]
    assert "verify-email?" in sent[0]["text"]
    assert created.get_json()["email_verified"] is False


def test_verified_login_emails_a_code_and_does_not_open_the_confirm_wall(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    sent = _capture(monkeypatch, login_code)
    client = _app(tmp_path, monkeypatch, "login-code.db")
    created = _signup(client, "owner@example.com")
    mark_email_verified(created.get_json()["account_id"])
    asked = _post(client, "/api/auth/login", {
        "email": "owner@example.com",
        "password": "correct-horse",
    })
    assert asked.status_code == 200
    body = asked.get_json()
    assert body["otp_required"] is True
    assert body["email"] == "owner@example.com"
    assert "owner@example.com" in body["message"]
    assert client.get("/api/auth/me").status_code == 401
    assert sent[-1]["to"] == "owner@example.com"
    assert LOGIN_CODE in sent[-1]["text"]
    assert LOGIN_CODE in sent[-1]["html"]
    assert "Monetra" in sent[-1]["subject"]
    assert LOGIN_CODE not in caplog.text

    wrong = _post(client, "/api/auth/login-code", {
        "email": "owner@example.com",
        "code": "000000",
    })
    assert wrong.status_code == 400
    assert wrong.get_json()["code"] == "invalid_code"
    assert client.get("/api/auth/me").status_code == 401

    signed = _post(client, "/api/auth/login-code", {
        "email": "owner@example.com",
        "code": LOGIN_CODE,
    })
    assert signed.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["email_verified"] is True


def test_unconfirmed_login_sends_the_signup_link_and_does_not_sign_in(tmp_path, monkeypatch):
    sent = _capture(monkeypatch, verification)
    client = _app(tmp_path, monkeypatch, "unconfirmed.db")
    assert _signup(client, "new@example.com").status_code == 201
    client.post("/api/auth/logout")
    asked = _post(client, "/api/auth/login", {
        "email": "new@example.com",
        "password": "correct-horse",
    })
    assert asked.status_code == 403
    assert asked.get_json()["code"] == "email_unverified"
    assert asked.get_json()["email"] == "new@example.com"
    assert client.get("/api/auth/me").status_code == 401
    assert sent[-1]["to"] == "new@example.com"
    assert "verify-email?" in sent[-1]["text"]


def test_fifth_wrong_code_burns_the_row(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "burn-code.db")
    created = _signup(client, "burn@example.com")
    account_id = created.get_json()["account_id"]
    mark_email_verified(account_id)
    assert _post(client, "/api/auth/login", {
        "email": "burn@example.com",
        "password": "correct-horse",
    }).status_code == 200
    for _ in range(5):
        wrong = _post(client, "/api/auth/login-code", {
            "email": "burn@example.com",
            "code": "111111",
        })
        assert wrong.status_code == 400
    assert get_open_challenge(account_id, "login_code") is None
    real = _post(client, "/api/auth/login-code", {
        "email": "burn@example.com",
        "code": LOGIN_CODE,
    })
    assert real.status_code == 400
    assert client.get("/api/auth/me").status_code == 401


def test_sixth_code_send_is_limited(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "code-limit.db")
    created = _signup(client, "often@example.com")
    mark_email_verified(created.get_json()["account_id"])
    for _ in range(5):
        asked = _post(client, "/api/auth/login", {
            "email": "often@example.com",
            "password": "correct-horse",
        })
        assert asked.status_code == 200
        assert asked.get_json()["otp_required"] is True
    blocked = _post(client, "/api/auth/login", {
        "email": "often@example.com",
        "password": "correct-horse",
    })
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_login_code"
    assert blocked.get_json()["retry_after"] == 60
