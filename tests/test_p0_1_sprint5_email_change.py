"""Sprint 5: the new address is applied only after its confirm link is posted."""
import json

import config
import database.db as db_mod
from app import create_app
from database.repository import get_account_by_email, get_challenge, mark_email_verified
from tests.auth_client import complete_login
from services.rate_limit import gateway as gw_mod
import services.email_change as email_change
import services.verification as verification

INVALID = "That link is invalid or expired."
WRONG = "Email or password is incorrect."


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
        if subject == email_change.NOTICE_SUBJECT:
            return False if fake_send.fail_notice else True
        return True

    fake_send.fail_notice = False
    monkeypatch.setattr(verification, "send_email", fake_send)
    monkeypatch.setattr(email_change, "send_email", fake_send)
    return sent, fake_send


def _signup(client, email, password="correct-horse"):
    res = _post(client, "/api/auth/signup", {
        "email": email,
        "password": password,
        "confirm_password": password,
    })
    assert res.status_code == 201, res.get_data(as_text=True)
    mark_email_verified(res.get_json()["account_id"])
    return res


def _link_parts(text):
    line = next(part for part in text.splitlines() if "confirm-email?" in part)
    query = line.split("?", 1)[1]
    parts = dict(item.split("=", 1) for item in query.split("&"))
    return int(parts["id"]), parts["token"]


def _link_mails(sent):
    return [item for item in sent if "confirm-email?" in item["text"]]


def test_password_is_required(tmp_path, monkeypatch):
    sent, _fake = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "password.db").test_client()
    _signup(client, "owner@example.com")
    missing = _post(client, "/api/auth/change-email", {"email": "next@example.com"})
    assert missing.status_code == 400
    assert "password" in json.dumps(missing.get_json()).lower()
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"
    assert _link_mails(sent) == []


def test_a_wrong_password_matches_login_and_spends_both_buckets(tmp_path, monkeypatch):
    _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "wrong-password.db").test_client()
    _signup(client, "owner@example.com")
    for _ in range(5):
        wrong = _post(client, "/api/auth/change-email", {
            "email": "next@example.com",
            "password": "not-the-password",
        })
        assert wrong.status_code == 401
        assert wrong.get_json()["error"] == WRONG
        assert wrong.get_json()["code"] == "invalid_credentials"
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"

    blocked = _post(client, "/api/auth/change-email", {
        "email": "next@example.com",
        "password": "correct-horse",
    })
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_account_action"
    assert blocked.get_json()["retry_after"] == 60

    login = _post(client, "/api/auth/login", {
        "email": "owner@example.com",
        "password": "not-the-password",
    })
    assert login.status_code == 429
    assert login.get_json()["route_class"] == "auth_account"
    assert login.get_json()["retry_after"] == 600


def test_old_address_stays_until_confirm_and_both_sessions_end(tmp_path, monkeypatch):
    sent, _fake = _capture(monkeypatch)
    app = _app(tmp_path, monkeypatch, "confirm.db")
    first = app.test_client()
    second = app.test_client()
    _signup(first, "owner@example.com")
    assert complete_login(second, "owner@example.com", "correct-horse").status_code == 200
    assert first.get("/api/auth/me").status_code == 200
    assert second.get("/api/auth/me").status_code == 200

    requested = _post(first, "/api/auth/change-email", {
        "email": "next@example.com",
        "password": "correct-horse",
    })
    assert requested.status_code == 200
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"
    assert get_account_by_email("next@example.com") is None
    wrong_login = _post(app.test_client(), "/api/auth/login", {
        "email": "owner@example.com",
        "password": "not-the-password",
    })
    assert wrong_login.status_code == 401
    assert wrong_login.get_json()["code"] == "invalid_credentials"
    notice = next(item for item in sent if item["subject"] == email_change.NOTICE_SUBJECT)
    assert "confirm-email?" not in notice["text"]
    assert notice["to"] == "owner@example.com"
    challenge_id, token = _link_parts(_link_mails(sent)[-1]["text"])
    assert _link_mails(sent)[-1]["to"] == "next@example.com"
    assert get_challenge(challenge_id, "change_email")["consumed_at"] is None

    asker = app.test_client()
    confirmed = _post(asker, "/api/auth/confirm-email", {"id": challenge_id, "token": token})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["message"] == "Email updated. Sign in again with the new address."
    assert asker.get("/api/auth/me").status_code == 401
    moved = get_account_by_email("next@example.com")
    assert moved is not None
    assert moved["email_verified_at"] is not None
    assert get_account_by_email("owner@example.com") is None
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    assert first.post("/api/auth/refresh").status_code == 401
    assert second.post("/api/auth/refresh").status_code == 401

    again = _post(asker, "/api/auth/confirm-email", {"id": challenge_id, "token": token})
    assert again.status_code == 400
    assert again.get_json()["error"] == INVALID


def test_a_taken_address_is_consumed_and_rejected(tmp_path, monkeypatch):
    sent, _fake = _capture(monkeypatch)
    app = _app(tmp_path, monkeypatch, "taken.db")
    owner = app.test_client()
    other = app.test_client()
    _signup(other, "taken@example.com")
    _signup(owner, "owner@example.com")
    requested = _post(owner, "/api/auth/change-email", {
        "email": "taken@example.com",
        "password": "correct-horse",
    })
    assert requested.status_code == 200
    challenge_id, token = _link_parts(_link_mails(sent)[-1]["text"])
    rejected = _post(app.test_client(), "/api/auth/confirm-email", {"id": challenge_id, "token": token})
    assert rejected.status_code == 400
    assert rejected.get_json()["error"] == INVALID
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"
    assert get_account_by_email("taken@example.com")["email"] == "taken@example.com"
    assert get_challenge(challenge_id, "change_email")["consumed_at"] is not None
    second = _post(app.test_client(), "/api/auth/confirm-email", {"id": challenge_id, "token": token})
    assert second.status_code == 400
    assert second.get_json()["error"] == INVALID


def test_a_failed_notice_leaves_the_challenge_unconfirmed(tmp_path, monkeypatch):
    sent, fake = _capture(monkeypatch)
    fake.fail_notice = True
    client = _app(tmp_path, monkeypatch, "notice.db").test_client()
    _signup(client, "owner@example.com")
    requested = _post(client, "/api/auth/change-email", {
        "email": "next@example.com",
        "password": "correct-horse",
    })
    assert requested.status_code == 200
    assert get_account_by_email("owner@example.com")["email"] == "owner@example.com"
    challenge_id, token = _link_parts(_link_mails(sent)[-1]["text"])
    assert get_challenge(challenge_id, "change_email")["consumed_at"] is None
    notice = next(item for item in sent if item["subject"] == email_change.NOTICE_SUBJECT)
    assert "token=" not in notice["text"]
    confirmed = _post(app_client(client), "/api/auth/confirm-email", {"id": challenge_id, "token": token})
    assert confirmed.status_code == 200
    assert get_account_by_email("next@example.com")["email"] == "next@example.com"


def app_client(client):
    return client.application.test_client()
