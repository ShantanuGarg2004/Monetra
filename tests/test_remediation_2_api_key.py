"""Issue 2: the deployment key is not a data credential."""
import json

import config
import database.db as db_mod
import app as app_mod
from app import create_app
from conftest import sign_in
from scripts.http_session import cookie_pair, data_headers
from services.rate_limit import gateway as gw_mod


def _client(tmp_path, monkeypatch, name="issue2.db", env="development"):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(app_mod.Config, "FLASK_ENV", env)
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_data_headers_send_the_cookie_and_not_the_api_key():
    headers = data_headers(cookie_pair("finpilot_access=abc; HttpOnly; Path=/"))
    assert headers["Cookie"] == "finpilot_access=abc"
    assert "X-API-Key" not in headers


def test_api_key_is_forbidden_on_users_and_generate(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    sign_in(client, "owner@example.com")
    created = client.post(
        "/api/profile",
        data=json.dumps({
            "age": 30,
            "income": 1,
            "expenses": 1,
            "savings": 1,
            "risk_appetite": "low",
            "financial_goals": "house",
        }),
        headers={"Content-Type": "application/json"},
    )
    user_id = created.get_json()["user_id"]
    client.post("/api/auth/logout")

    key = {"X-API-Key": config.Config.API_SECRET_KEY, "Content-Type": "application/json"}
    listed = client.get("/api/users", headers=key)
    generated = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=key,
    )
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "unauthorized"
    assert generated.status_code == 401
    assert generated.get_json()["code"] == "unauthorized"


def test_login_health_and_docs_still_accept_their_existing_rules(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "open.db")
    health = client.get("/api/health")
    assert health.status_code == 200

    signed = sign_in(client, "still@example.com")
    me = client.get("/api/auth/me", headers=signed)
    assert me.status_code == 200
    assert me.get_json()["email"] == "still@example.com"

    import base64
    key = config.Config.API_SECRET_KEY
    basic = base64.b64encode(f"finpilot:{key}".encode()).decode()
    spec = client.get("/apispec.json", headers={"Authorization": f"Basic {basic}"})
    assert spec.status_code == 200
    description = spec.get_json()["securityDefinitions"]["ApiKeyAuth"]["description"]
    assert "does not open profiles" in description
