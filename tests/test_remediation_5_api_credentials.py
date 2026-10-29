"""Issue 5: a scoped API key can touch only its own account."""
import json

import config
import database.db as db_mod
from app import create_app
from conftest import sign_in
from database.repository import issue_api_credential, revoke_api_credential, save_chat_turn
from services.rate_limit import gateway as gw_mod


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _profile(goals):
    return {
        "age": 30,
        "income": 100000,
        "expenses": 40000,
        "savings": 20000,
        "risk_appetite": "medium",
        "financial_goals": goals,
    }


def _create(client, goals):
    created = client.post(
        "/api/profile",
        data=json.dumps(_profile(goals)),
        headers={"Content-Type": "application/json"},
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    return created.get_json()["user_id"]


def _drop_cookie(client):
    client.post("/api/auth/logout")
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")


def test_scoped_key_cannot_read_another_account(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cred-cross.db")
    sign_in(client, "a@example.com")
    me = client.get("/api/auth/me")
    account_a = me.get_json()["account_id"]
    user_a = _create(client, "house-a")
    raw_key, _credential_id = issue_api_credential(account_a, "a-key", ["data", "llm"])
    _drop_cookie(client)

    sign_in(client, "b@example.com")
    user_b = _create(client, "house-b")
    save_chat_turn(user_b, "hello", "hi")
    _drop_cookie(client)

    key = {"X-API-Key": raw_key}
    listed = client.get("/api/users", headers=key)
    assert listed.status_code == 200
    goals = [row["financial_goals"] for row in listed.get_json()["users"]]
    assert goals == ["house-a"]
    assert user_a != user_b

    report = client.get(f"/api/report/{user_b}", headers=key)
    chat = client.get(f"/api/chat/history/{user_b}", headers=key)
    assert report.status_code == 404
    assert chat.status_code == 404
    assert "house-b" not in report.get_data(as_text=True)
    assert "hello" not in chat.get_data(as_text=True)


def test_data_scope_cannot_generate(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cred-data.db")
    sign_in(client, "data@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    user_id = _create(client, "house")
    raw_key, _credential_id = issue_api_credential(account_id, "data-only", ["data"])
    _drop_cookie(client)

    key = {"X-API-Key": raw_key, "Content-Type": "application/json"}
    listed = client.get("/api/users", headers=key)
    generated = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=key,
    )
    assert listed.status_code == 200
    assert generated.status_code == 403
    assert generated.get_json()["code"] == "forbidden"


def test_llm_scope_enqueues_its_own_report(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cred-llm.db")
    sign_in(client, "llm@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    user_id = _create(client, "house")
    raw_key, _credential_id = issue_api_credential(account_id, "llm-only", ["llm"])
    _drop_cookie(client)

    generated = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers={"X-API-Key": raw_key, "Content-Type": "application/json"},
    )
    assert generated.status_code == 202
    assert generated.get_json()["status"] in ("queued", "running")


def test_revoked_key_is_unauthorized(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cred-revoke.db")
    sign_in(client, "revoke@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    _create(client, "house")
    raw_key, credential_id = issue_api_credential(account_id, "soon-revoked", ["data"])
    revoke_api_credential(credential_id)
    _drop_cookie(client)

    listed = client.get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "unauthorized"


def test_docs_password_still_cannot_list_profiles(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cred-docs.db")
    sign_in(client, "docs@example.com")
    _create(client, "house")
    _drop_cookie(client)
    listed = client.get("/api/users", headers={"X-API-Key": config.Config.API_SECRET_KEY})
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "unauthorized"
