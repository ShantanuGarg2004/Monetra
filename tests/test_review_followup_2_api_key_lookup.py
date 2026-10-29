"""Follow-up 2: API keys are found by digest, and rejected keys are counted."""
import json

import config
import database.db as db_mod
import database.repository as repository
from app import create_app
from conftest import sign_in
from database.repository import issue_api_credential, revoke_api_credential
from services.rate_limit import gateway as gw_mod
from werkzeug.security import generate_password_hash


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _profile(goals="house"):
    return {
        "age": 30,
        "income": 100000,
        "expenses": 40000,
        "savings": 20000,
        "risk_appetite": "medium",
        "financial_goals": goals,
    }


def test_new_key_lookup_does_not_check_password_hashes(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "digest.db")
    sign_in(client, "owner@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    created = client.post(
        "/api/profile",
        data=json.dumps(_profile()),
        headers={"Content-Type": "application/json"},
    )
    assert created.status_code == 201
    raw_key, _credential_id = issue_api_credential(account_id, "live", ["data"])

    conn = db_mod.get_connection()
    for label in ("old-a", "old-b"):
        conn.execute(
            """
            INSERT INTO api_credentials (account_id, label, key_hash, scopes)
            VALUES (:account_id, :label, :key_hash, 'data')
            """,
            {
                "account_id": account_id,
                "label": label,
                "key_hash": generate_password_hash("legacy-secret"),
            },
        )
    conn.commit()
    conn.close()
    client.post("/api/auth/logout")
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")

    calls = {"n": 0}
    real = repository.check_password_hash

    def _counted(hashed, password):
        calls["n"] += 1
        return real(hashed, password)

    monkeypatch.setattr(repository, "check_password_hash", _counted)
    listed = client.get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 200
    assert calls["n"] == 0
    assert len(listed.get_json()["users"]) == 1


def test_wrong_key_then_rate_limit_and_missing_cookie_stays_separate(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "reject.db")
    limit = gw_mod.get_gateway().policies.credential_failure.limit
    for _ in range(limit):
        missing = client.get("/api/users")
        assert missing.status_code == 401
        assert missing.get_json()["code"] == "session_expired"

    statuses = []
    for _ in range(limit + 1):
        res = client.get("/api/users", headers={"X-API-Key": "not-a-real-key"})
        statuses.append(res.status_code)
    assert statuses[:limit] == [401] * limit
    assert statuses[limit] == 429
    assert client.get("/api/users", headers={"X-API-Key": "not-a-real-key"}).get_json()["code"] == "rate_limit_exceeded"

    still_session = client.get("/api/users")
    assert still_session.status_code == 401
    assert still_session.get_json()["code"] == "session_expired"


def test_revoked_key_is_unauthorized(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "revoke.db")
    sign_in(client, "owner@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    raw_key, credential_id = issue_api_credential(account_id, "soon", ["data"])
    revoke_api_credential(credential_id)
    client.post("/api/auth/logout")
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")
    listed = client.get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "unauthorized"


def test_llm_scope_cannot_list_profiles(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "scope.db")
    sign_in(client, "owner@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    raw_key, _credential_id = issue_api_credential(account_id, "llm-only", ["llm"])
    client.post("/api/auth/logout")
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")
    listed = client.get("/api/users", headers={"X-API-Key": raw_key})
    assert listed.status_code == 403
    assert listed.get_json()["code"] == "forbidden"


def test_legacy_password_hash_still_matches(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "legacy.db")
    sign_in(client, "owner@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    client.post(
        "/api/profile",
        data=json.dumps(_profile("legacy-house")),
        headers={"Content-Type": "application/json"},
    )
    raw = "legacy-raw-key"
    conn = db_mod.get_connection()
    conn.execute(
        """
        INSERT INTO api_credentials (account_id, label, key_hash, scopes)
        VALUES (:account_id, 'legacy', :key_hash, 'data')
        """,
        {"account_id": account_id, "key_hash": generate_password_hash(raw)},
    )
    conn.commit()
    conn.close()
    client.post("/api/auth/logout")
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")
    listed = client.get("/api/users", headers={"X-API-Key": raw})
    assert listed.status_code == 200
    assert listed.get_json()["users"][0]["financial_goals"] == "legacy-house"
