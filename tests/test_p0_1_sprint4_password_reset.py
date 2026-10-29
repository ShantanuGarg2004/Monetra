"""Sprint 4: forgot-password stays uniform, and reset signs every device out."""
import json

import config
import database.db as db_mod
from app import create_app
from database.repository import get_account_by_email, issue_api_credential, mark_email_verified
from tests.auth_client import complete_login
from services.rate_limit import gateway as gw_mod
import services.password_reset as password_reset
import services.verification as verification

FORGOT = "If an account exists for that email, a reset link is on its way."
INVALID = "That link is invalid or expired."


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    monkeypatch.setattr(config.Config, "APP_PUBLIC_URL", "http://localhost:5173")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), headers={"Content-Type": "application/json"})


def _capture(monkeypatch):
    sent = []

    def fake_send(to, subject, text, html=None):
        sent.append({"to": to, "subject": subject, "text": text})
        return True

    monkeypatch.setattr(verification, "send_email", fake_send)
    monkeypatch.setattr(password_reset, "send_email", fake_send)
    return sent


def _signup(client, email, password="correct-horse"):
    return _post(client, "/api/auth/signup", {
        "email": email,
        "password": password,
        "confirm_password": password,
    })


def _forgot(client, email):
    return _post(client, "/api/auth/forgot-password", {"email": email})


def _link_parts(text):
    line = next(part for part in text.splitlines() if "reset-password?" in part)
    query = line.split("?", 1)[1]
    parts = dict(item.split("=", 1) for item in query.split("&"))
    return int(parts["id"]), parts["token"]


def _reset_mails(sent):
    return [item for item in sent if "reset-password?" in item["text"]]


def test_unknown_and_known_emails_share_the_forgot_response(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "forgot.db").test_client()
    unknown = _forgot(client, "missing@example.com")
    created = _signup(client, "known@example.com")
    assert created.status_code == 201
    mark_email_verified(created.get_json()["account_id"])
    known = _forgot(client, "known@example.com")
    unverified = _signup(client, "new@example.com")
    assert unverified.status_code == 201
    quiet = _forgot(client, "new@example.com")

    assert unknown.status_code == known.status_code == quiet.status_code == 200
    assert unknown.get_json() == known.get_json() == quiet.get_json() == {"message": FORGOT}
    reset_mails = _reset_mails(sent)
    assert [item["to"] for item in reset_mails] == ["known@example.com"]
    assert get_account_by_email("new@example.com")["email"] == "new@example.com"


def test_the_fourth_reset_send_keeps_the_same_body(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "resend-reset.db").test_client()
    created = _signup(client, "often@example.com")
    mark_email_verified(created.get_json()["account_id"])
    for _ in range(3):
        sent_ok = _forgot(client, "often@example.com")
        assert sent_ok.status_code == 200
        assert sent_ok.get_json() == {"message": FORGOT}
    assert len(_reset_mails(sent)) == 3
    held = _forgot(client, "often@example.com")
    assert held.status_code == 200
    assert held.get_json() == {"message": FORGOT}
    assert len(_reset_mails(sent)) == 3


def test_reset_revokes_both_sessions_and_the_secret_once(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    app = _app(tmp_path, monkeypatch, "reset.db")
    first = app.test_client()
    second = app.test_client()
    created = _signup(first, "owner@example.com")
    assert created.status_code == 201
    account_id = created.get_json()["account_id"]
    mark_email_verified(account_id)
    signed = complete_login(second, "owner@example.com", "correct-horse")
    assert signed.status_code == 200
    assert first.get("/api/auth/me").status_code == 200
    assert second.get("/api/auth/me").status_code == 200
    raw_key, _credential_id = issue_api_credential(account_id, "keep-me", ["data"])

    assert _forgot(first, "owner@example.com").status_code == 200
    challenge_id, token = _link_parts(_reset_mails(sent)[-1]["text"])
    asker = app.test_client()
    reset = _post(asker, "/api/auth/reset-password", {
        "id": challenge_id,
        "token": token,
        "password": "brand-new-pass",
        "confirm_password": "brand-new-pass",
    })
    assert reset.status_code == 200
    assert reset.get_json()["message"] == "Password updated. You will need to sign in again on each device."
    assert asker.get("/api/auth/me").status_code == 401

    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    assert first.post("/api/auth/refresh").status_code == 401
    assert second.post("/api/auth/refresh").status_code == 401

    again = _post(app.test_client(), "/api/auth/reset-password", {
        "id": challenge_id,
        "token": token,
        "password": "another-password",
        "confirm_password": "another-password",
    })
    assert again.status_code == 400
    assert again.get_json()["error"] == INVALID

    fresh = app.test_client()
    old = _post(fresh, "/api/auth/login", {
        "email": "owner@example.com",
        "password": "correct-horse",
    })
    assert old.status_code == 401
    assert old.get_json()["code"] == "invalid_credentials"
    new = _post(fresh, "/api/auth/login", {
        "email": "owner@example.com",
        "password": "brand-new-pass",
    })
    assert new.status_code == 200
    listed = app.test_client().get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 200
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"


def test_five_wrong_reset_secrets_burn_the_row(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "burn-reset.db").test_client()
    created = _signup(client, "burn@example.com")
    mark_email_verified(created.get_json()["account_id"])
    assert _forgot(client, "burn@example.com").status_code == 200
    challenge_id, token = _link_parts(_reset_mails(sent)[-1]["text"])
    for _ in range(5):
        wrong = _post(client, "/api/auth/reset-password", {
            "id": challenge_id,
            "token": "not-the-secret",
            "password": "brand-new-pass",
            "confirm_password": "brand-new-pass",
        })
        assert wrong.status_code == 400
        assert wrong.get_json()["error"] == INVALID
    real = _post(client, "/api/auth/reset-password", {
        "id": challenge_id,
        "token": token,
        "password": "brand-new-pass",
        "confirm_password": "brand-new-pass",
    })
    assert real.status_code == 400
    assert real.get_json()["error"] == INVALID
    from werkzeug.security import check_password_hash
    stored = get_account_by_email("burn@example.com")
    assert check_password_hash(stored["password_hash"], "correct-horse")
