"""Q5: password login, session cookie, and profile ownership."""
import base64
import json

import app as app_mod
import config
import database.db as db_mod
from app import create_app
from database.models import create_tables
from database.repository import mark_email_verified
from services.rate_limit import gateway as gw_mod


def _app(tmp_path, monkeypatch, name="q5.db"):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _signup(client, email, password="correct-horse"):
    res = client.post(
        "/api/auth/signup",
        data=json.dumps({
            "email": email,
            "password": password,
            "confirm_password": password,
        }),
        headers={"Content-Type": "application/json"},
    )
    if res.status_code == 201:
        mark_email_verified(res.get_json()["account_id"])
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


def test_signup_sets_session_and_hides_other_accounts(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    first = _signup(client, "a@example.com")
    assert first.status_code == 201
    assert "finpilot_access" in first.headers.get("Set-Cookie", "")
    created = client.post(
        "/api/profile",
        data=json.dumps(_profile()),
        headers={"Content-Type": "application/json"},
    )
    own_id = created.get_json()["user_id"]

    other = _app(tmp_path, monkeypatch, "q5.db")
    assert _signup(other, "b@example.com").status_code == 201
    hidden = other.get(f"/api/report/{own_id}")
    assert hidden.status_code == 404
    assert hidden.get_json()["code"] == "not_found"
    assert other.get("/api/users").get_json()["users"] == []


def test_wrong_password_does_not_look_like_a_missing_report(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "login.db")
    _signup(client, "a@example.com")
    client.post("/api/auth/logout")
    bad = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "a@example.com", "password": "not-the-password"}),
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 401
    assert bad.get_json()["code"] == "invalid_credentials"
    assert "report" not in bad.get_json()["error"].lower()


def test_expired_cookie_is_session_expired(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "cookie.db")
    client.set_cookie("finpilot_access", "not-a-real-token", domain="localhost")
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert res.get_json()["code"] == "session_expired"


def test_api_key_cannot_list_profiles(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "key.db")
    _signup(client, "a@example.com")
    client.post(
        "/api/profile",
        data=json.dumps(_profile()),
        headers={"Content-Type": "application/json"},
    )
    client.post("/api/auth/logout")
    listed = client.get("/api/users", headers={"X-API-Key": config.Config.API_SECRET_KEY})
    assert listed.status_code == 401
    assert listed.get_json()["code"] == "unauthorized"


def test_swagger_lists_every_api(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod.Config, "FLASK_ENV", "development")
    client = _app(tmp_path, monkeypatch, "spec.db")
    key = config.Config.API_SECRET_KEY
    basic = base64.b64encode(f"finpilot:{key}".encode()).decode()
    spec = client.get("/apispec.json", headers={"Authorization": f"Basic {basic}"})
    assert spec.status_code == 200, spec.status_code
    paths = spec.get_json()["paths"]
    expected = {
        "/api/health",
        "/api/auth/signup",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/users",
        "/api/profile",
        "/api/profile/{user_id}",
        "/api/report/{user_id}",
        "/api/generate-report",
        "/api/download-report/{user_id}",
        "/api/chat",
        "/api/chat/history/{user_id}",
        "/api/goal-plan",
    }
    assert expected <= set(paths)


def test_bootstrap_attaches_existing_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / "boot.db"))
    monkeypatch.setattr(config.Config, "BOOTSTRAP_ACCOUNT_EMAIL", "owner@example.com")
    monkeypatch.setattr(config.Config, "BOOTSTRAP_ACCOUNT_PASSWORD", "bootstrap-password")
    create_tables()
    conn = db_mod.get_connection()
    conn.execute(
        "INSERT INTO users (age, income, expenses, savings, risk_appetite, financial_goals) "
        "VALUES (30, 1, 1, 1, 'low', 'house')"
    )
    conn.commit()
    conn.close()
    create_tables()
    conn = db_mod.get_connection()
    row = conn.execute(
        "SELECT users.account_id, accounts.email FROM users JOIN accounts ON accounts.id = users.account_id"
    ).fetchone()
    conn.close()
    assert row["email"] == "owner@example.com"
    assert row["account_id"]
