"""Sprint 3: verification links, the unverified gate, and auth mail buckets."""
import json

import config
import database.db as db_mod
from app import create_app
from database.models import create_tables
from database.repository import get_account_by_email, get_verify_challenge
from services.rate_limit import gateway as gw_mod
import services.verification as verification


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


def _capture(monkeypatch):
    sent = {}

    def fake_send(to, subject, text):
        sent["to"] = to
        sent["subject"] = subject
        sent["text"] = text
        return True

    monkeypatch.setattr(verification, "send_email", fake_send)
    return sent


def _link_parts(text):
    line = next(part for part in text.splitlines() if "verify-email?" in part)
    query = line.split("?", 1)[1]
    parts = dict(item.split("=", 1) for item in query.split("&"))
    return int(parts["id"]), parts["token"]


def _signup(client, email="new@example.com"):
    return _post(client, "/api/auth/signup", {
        "email": email,
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    })


def test_signup_sends_a_link_and_blocks_the_profile_until_confirm(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "verify-ok.db")
    created = _signup(client)
    assert created.status_code == 201
    body = created.get_json()
    assert body["email_verified"] is False
    assert "message" not in body
    assert sent["to"] == "new@example.com"
    challenge_id, token = _link_parts(sent["text"])
    assert get_verify_challenge(challenge_id)["consumed_at"] is None

    blocked = _post(client, "/api/profile", {
        "age": 30, "income": 1, "expenses": 1, "savings": 1,
        "risk_appetite": "low", "financial_goals": "house",
    })
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "email_unverified"
    assert client.get("/api/auth/me").status_code == 200

    confirmed = _post(client, "/api/auth/verify-email", {"id": challenge_id, "token": token})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["message"] == "Email confirmed."
    assert get_verify_challenge(challenge_id)["consumed_at"] is not None
    again = _post(client, "/api/auth/verify-email", {"id": challenge_id, "token": token})
    assert again.status_code == 400
    assert again.get_json()["error"] == "That link is invalid or expired."
    assert client.get("/api/auth/me").get_json()["email_verified"] is True
    opened = _post(client, "/api/profile", {
        "age": 30, "income": 1, "expenses": 1, "savings": 1,
        "risk_appetite": "low", "financial_goals": "house",
    })
    assert opened.status_code == 201


def test_failed_send_keeps_the_account_and_names_resend(tmp_path, monkeypatch):
    monkeypatch.setattr(verification, "send_email", lambda *args, **kwargs: False)
    client = _app(tmp_path, monkeypatch, "verify-fail.db")
    created = _signup(client, "missed@example.com")
    assert created.status_code == 201
    assert "Use resend." in created.get_json()["message"]
    assert get_account_by_email("missed@example.com")["email_verified_at"] is None


def test_wrong_secret_burns_the_row_on_the_fifth_miss(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "verify-burn.db")
    assert _signup(client, "burn@example.com").status_code == 201
    challenge_id, token = _link_parts(sent["text"])
    for _ in range(5):
        wrong = _post(client, "/api/auth/verify-email", {"id": challenge_id, "token": "not-the-secret"})
        assert wrong.status_code == 400
        assert wrong.get_json()["error"] == "That link is invalid or expired."
    assert get_verify_challenge(challenge_id)["consumed_at"] is not None
    real = _post(client, "/api/auth/verify-email", {"id": challenge_id, "token": token})
    assert real.status_code == 400
    assert real.get_json()["error"] == "That link is invalid or expired."
    assert get_account_by_email("burn@example.com")["email_verified_at"] is None


def test_resend_replaces_the_open_challenge_and_then_limits(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "verify-resend.db")
    assert _signup(client, "resend@example.com").status_code == 201
    first_id, first_token = _link_parts(sent["text"])
    for _ in range(3):
        resent = client.post("/api/auth/resend-verification")
        assert resent.status_code == 200
    latest_id, latest_token = _link_parts(sent["text"])
    assert latest_id != first_id
    stale = _post(client, "/api/auth/verify-email", {"id": first_id, "token": first_token})
    assert stale.status_code == 400
    blocked = client.post("/api/auth/resend-verification")
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_resend"
    assert blocked.get_json()["retry_after"] == 600
    confirmed = _post(client, "/api/auth/verify-email", {"id": latest_id, "token": latest_token})
    assert confirmed.status_code == 200


def test_verify_posts_share_the_address_bucket(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "verify-ip.db")
    for _ in range(8):
        res = _post(client, "/api/auth/verify-email", {})
        assert res.status_code == 400
        assert res.get_json()["error"] == "That link is invalid or expired."
    blocked = _post(client, "/api/auth/verify-email", {})
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_ip"
    assert blocked.get_json()["retry_after"] == 15


def test_an_expired_link_uses_the_same_sentence(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    client = _app(tmp_path, monkeypatch, "verify-expired.db")
    assert _signup(client, "old-link@example.com").status_code == 201
    challenge_id, token = _link_parts(sent["text"])
    conn = db_mod.get_connection()
    conn.execute(
        "UPDATE auth_challenges SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE id = :id",
        {"id": challenge_id},
    )
    conn.commit()
    conn.close()
    expired = _post(client, "/api/auth/verify-email", {"id": challenge_id, "token": token})
    assert expired.status_code == 400
    assert expired.get_json()["error"] == "That link is invalid or expired."
    assert get_account_by_email("old-link@example.com")["email_verified_at"] is None


def test_existing_rows_are_grandfathered_only_when_the_column_is_added(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / "grandfather.db"))
    create_tables()
    conn = db_mod.get_connection()
    conn.execute("ALTER TABLE accounts DROP COLUMN email_verified_at")
    conn.execute(
        """
        INSERT INTO accounts (email, password_hash, auth_provider)
        VALUES ('old@example.com', 'hash', 'local')
        """
    )
    conn.commit()
    conn.close()
    create_tables()
    account = get_account_by_email("old@example.com")
    assert account["email_verified_at"] is not None
    conn = db_mod.get_connection()
    conn.execute(
        """
        INSERT INTO accounts (email, password_hash, auth_provider)
        VALUES ('later@example.com', 'hash', 'local')
        """
    )
    conn.commit()
    conn.close()
    create_tables()
    assert get_account_by_email("later@example.com")["email_verified_at"] is None
