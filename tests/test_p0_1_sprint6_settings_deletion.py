"""Sprint 6: settings actions, account deletion, and cross-account reads."""
import json
from pathlib import Path

import app as app_mod
import config
import database.db as db_mod
import database.pdf_files as pdf_files
from app import create_app
from database.db import connection
from database.repository import (
    enqueue_report_job,
    get_account_by_email,
    issue_api_credential,
    mark_email_verified,
    save_chat_turn,
    save_report,
    store_pdf,
)
from services.rate_limit import gateway as gw_mod

PASSWORD = "correct-horse"
NEW_PASSWORD = "brand-new-pass"
PRIVATE_REPORT = "private advisory"
PRIVATE_CHAT = "private chat line"


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    pdf_dir = str(tmp_path / "pdfs")
    for holder in {config.Config, app_mod.Config, pdf_files.Config}:
        monkeypatch.setattr(holder, "RATELIMIT_STORAGE_BACKEND", "memory")
        monkeypatch.setattr(holder, "RATELIMIT_ENABLED", True)
        monkeypatch.setattr(holder, "FLASK_ENV", "development")
        monkeypatch.setattr(holder, "APP_PUBLIC_URL", "http://localhost:5173")
        monkeypatch.setattr(holder, "PDF_STORAGE_DIR", pdf_dir)
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), headers={"Content-Type": "application/json"})


def _signup(client, email, password=PASSWORD):
    res = _post(client, "/api/auth/signup", {
        "email": email,
        "password": password,
        "confirm_password": password,
    })
    assert res.status_code == 201, res.get_data(as_text=True)
    mark_email_verified(res.get_json()["account_id"])
    return res


def _login(client, email, password=PASSWORD):
    from tests.auth_client import complete_login
    res = complete_login(client, email, password)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res


def _profile(goals="house"):
    return {
        "age": 30,
        "income": 100000,
        "expenses": 40000,
        "savings": 20000,
        "risk_appetite": "medium",
        "financial_goals": goals,
    }


def _create(client, goals="house"):
    created = _post(client, "/api/profile", _profile(goals))
    assert created.status_code == 201, created.get_data(as_text=True)
    return created.get_json()["user_id"]


def _seed(user_id, account_id):
    save_report(user_id, {"score": 70}, PRIVATE_REPORT)
    store_pdf(user_id, b"%PDF-sprint6")
    save_chat_turn(user_id, PRIVATE_CHAT, "private reply")
    enqueue_report_job(user_id, account_id)


def _count(sql, params):
    with connection() as conn:
        return conn.execute(sql, params).fetchone()["n"]


def _assert_hidden(client, user_id):
    profile = client.get(f"/api/profile/{user_id}")
    report = client.get(f"/api/report/{user_id}")
    chat = client.get(f"/api/chat/history/{user_id}")
    pdf = client.get(f"/api/download-report/{user_id}")
    assert profile.status_code == 404
    assert profile.get_json()["code"] == "not_found"
    assert report.status_code == 404
    assert report.get_json()["code"] == "not_found"
    assert chat.status_code == 404
    assert pdf.status_code == 404
    assert pdf.get_json()["code"] == "not_found"
    body = " ".join(
        item.get_data(as_text=True) for item in (profile, report, chat, pdf)
    )
    assert "100000" not in body
    assert PRIVATE_REPORT not in body
    assert PRIVATE_CHAT not in body
    assert "job" not in report.get_json()


def test_deletion_removes_sessions_key_and_owned_reads(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    app = _app(tmp_path, monkeypatch, "delete.db")
    owner = app.test_client()
    other_device = app.test_client()
    created = _signup(owner, "owner@example.com")
    account_id = created.get_json()["account_id"]
    _login(other_device, "owner@example.com")
    user_id = _create(owner)
    _seed(user_id, account_id)
    raw_key, _credential_id = issue_api_credential(account_id, "data-key", ["data"])
    key_client = app.test_client()
    assert key_client.get("/api/users", headers={"X-API-Key": raw_key}).status_code == 200
    pdf_path = Path(pdf_files.Config.PDF_STORAGE_DIR) / f"profile_{user_id}.pdf"
    assert pdf_path.is_file()

    reader = app.test_client()
    _signup(reader, "reader@example.com")

    deleted = _post(owner, "/api/auth/delete-account", {
        "password": PASSWORD,
        "email": "owner@example.com",
    })
    assert deleted.status_code == 200
    assert deleted.get_json() == {"message": "Account deleted."}
    assert PASSWORD not in caplog.text
    assert "100000" not in caplog.text

    assert owner.get("/api/auth/me").status_code == 401
    assert other_device.get("/api/auth/me").status_code == 401
    assert owner.post("/api/auth/refresh").status_code == 401
    assert other_device.post("/api/auth/refresh").status_code == 401
    assert key_client.get("/api/users", headers={"X-API-Key": raw_key}).status_code == 401
    _assert_hidden(reader, user_id)
    assert not pdf_path.is_file()
    assert get_account_by_email("owner@example.com") is None
    assert _count("SELECT COUNT(*) AS n FROM users WHERE id = :id", {"id": user_id}) == 0
    assert _count("SELECT COUNT(*) AS n FROM jobs WHERE user_id = :id", {"id": user_id}) == 0
    assert _count("SELECT COUNT(*) AS n FROM reports WHERE user_id = :id", {"id": user_id}) == 0
    assert _count("SELECT COUNT(*) AS n FROM chat_history WHERE user_id = :id", {"id": user_id}) == 0


def test_account_a_cannot_read_account_b(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, "isolate.db")
    account_a = app.test_client()
    account_b = app.test_client()
    _signup(account_a, "a@example.com")
    created_b = _signup(account_b, "b@example.com")
    own_id = _create(account_a, "a-goal")
    other_id = _create(account_b, "b-goal")
    _seed(other_id, created_b.get_json()["account_id"])

    assert account_b.get(f"/api/profile/{other_id}").status_code == 200
    assert account_b.get(f"/api/report/{other_id}").status_code == 200
    assert account_b.get(f"/api/chat/history/{other_id}").status_code == 200
    assert account_b.get(f"/api/download-report/{other_id}").status_code == 200
    listed = {row["id"] for row in account_a.get("/api/users").get_json()["users"]}
    assert own_id in listed
    assert other_id not in listed
    _assert_hidden(account_a, other_id)


def test_logout_is_one_session_and_password_or_delete_revokes_all(tmp_path, monkeypatch, caplog):
    caplog.set_level("INFO")
    app = _app(tmp_path, monkeypatch, "sessions.db")
    first = app.test_client()
    second = app.test_client()
    created = _signup(first, "owner@example.com")
    account_id = created.get_json()["account_id"]
    _login(second, "owner@example.com")

    assert first.post("/api/auth/logout").status_code == 200
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 200

    _login(first, "owner@example.com")
    raw_key, _credential_id = issue_api_credential(account_id, "still-live", ["data"])
    key_client = app.test_client()
    assert key_client.get("/api/users", headers={"X-API-Key": raw_key}).status_code == 200

    short = _post(first, "/api/auth/change-password", {
        "current_password": PASSWORD,
        "password": "short-pass",
        "confirm_password": "short-pass",
    })
    assert short.status_code == 400
    assert "12" in json.dumps(short.get_json())
    assert second.get("/api/auth/me").status_code == 200

    wrong = _post(first, "/api/auth/change-password", {
        "current_password": "not-the-password",
        "password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert wrong.status_code == 401
    assert wrong.get_json()["code"] == "invalid_credentials"
    assert wrong.get_json()["error"] == "Email or password is incorrect."

    changed = _post(first, "/api/auth/change-password", {
        "current_password": PASSWORD,
        "password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert changed.status_code == 200
    assert changed.get_json()["message"] == "Password updated. You will need to sign in again on each device."
    assert PASSWORD not in caplog.text
    assert NEW_PASSWORD not in caplog.text
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    assert first.post("/api/auth/refresh").status_code == 401
    assert second.post("/api/auth/refresh").status_code == 401
    assert key_client.get("/api/users", headers={"X-API-Key": raw_key}).status_code == 200

    _login(first, "owner@example.com", NEW_PASSWORD)
    _login(second, "owner@example.com", NEW_PASSWORD)
    old = _post(app.test_client(), "/api/auth/login", {
        "email": "owner@example.com",
        "password": PASSWORD,
    })
    assert old.status_code == 401
    assert old.get_json()["code"] == "invalid_credentials"

    mismatch = _post(first, "/api/auth/delete-account", {
        "password": NEW_PASSWORD,
        "email": "someone-else@example.com",
    })
    assert mismatch.status_code == 400
    assert mismatch.get_json()["code"] == "email_mismatch"
    assert first.get("/api/auth/me").status_code == 200
    assert second.get("/api/auth/me").status_code == 200

    deleted = _post(first, "/api/auth/delete-account", {
        "password": NEW_PASSWORD,
        "email": "Owner@Example.com",
    })
    assert deleted.status_code == 200
    assert deleted.get_json() == {"message": "Account deleted."}
    assert first.get("/api/auth/me").status_code == 401
    assert second.get("/api/auth/me").status_code == 401
    assert first.post("/api/auth/refresh").status_code == 401
    assert second.post("/api/auth/refresh").status_code == 401
    assert key_client.get("/api/users", headers={"X-API-Key": raw_key}).status_code == 401
    assert get_account_by_email("owner@example.com") is None
