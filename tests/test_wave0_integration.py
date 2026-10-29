"""Integration tests for Wave 0 rate-limit policy and API contracts.

Uses Flask test client + temporary SQLite. No real Groq calls.
Wave 1 gateway owns limits when backend is memory|sql; tests tighten PolicyRegistry.
"""
import json

import pytest

import config
import database.db as db_mod
from app import create_app
from conftest import sign_in
from services.rate_limit import gateway as gw_mod


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """App client with isolated DB and memory rate-limit store."""
    test_db = tmp_path / "wave0_test.db"
    monkeypatch.setattr(db_mod, "DB_NAME", str(test_db))
    monkeypatch.setattr(config.Config, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_URI", "memory://")
    gw_mod._gateway = None

    app = create_app()
    app.config["TESTING"] = True
    # Tighten llm_report for fast 429 assertions (Wave 1 PolicyRegistry).
    gw = gw_mod.get_gateway()
    assert gw is not None
    gw.policies.llm_report = type(gw.policies.llm_report)("llm_report", 2, 60, False)
    gw.policies.llm_report_user = type(gw.policies.llm_report_user)("llm_report", 100, 3600, True)

    client = app.test_client()
    return client, sign_in(client)


def test_health_is_public_and_ok(api_client):
    client, _ = api_client
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["ratelimit_store_ok"] is True
    assert "ratelimit_enabled" not in body


def test_options_preflight_never_429(api_client):
    client, headers = api_client
    # Hammer OPTIONS — must stay non-429 (CORS preflight).
    for _ in range(40):
        res = client.options("/api/report/1", headers=headers)
        assert res.status_code != 429, res.data


def test_get_report_missing_returns_404_not_throttle(api_client):
    client, headers = api_client
    res = client.get("/api/report/99999", headers=headers)
    assert res.status_code == 404
    body = res.get_json()
    assert "error" in body


def test_unauthorized_returns_structured_401(api_client):
    client, _ = api_client
    client.delete_cookie("finpilot_access")
    client.delete_cookie("finpilot_refresh", path="/api/auth/refresh")
    res = client.get("/api/users", headers={"X-API-Key": "wrong"})
    assert res.status_code == 401
    body = res.get_json()
    assert body.get("code") == "unauthorized"


def test_create_profile_and_list_users(api_client):
    client, headers = api_client
    payload = {
        "age": 28,
        "income": 80000,
        "expenses": 40000,
        "savings": 20000,
        "risk_appetite": "medium",
        "financial_goals": "Buy a car in 3 years",
    }
    res = client.post("/api/profile", data=json.dumps(payload), headers=headers)
    assert res.status_code == 201
    user_id = res.get_json()["user_id"]

    res = client.get("/api/users", headers=headers)
    assert res.status_code == 200
    ids = [u["id"] for u in res.get_json()["users"]]
    assert user_id in ids


def test_generate_report_returns_structured_429_when_exceeded(api_client, monkeypatch):
    client, headers = api_client

    # Bypass AI/PDF — fail fast after limiter so we only exercise quota.
    import routes.report_routes as rr

    def _fake_user(uid):
        return {
            "id": uid,
            "age": 30,
            "income": 90000,
            "expenses": 50000,
            "savings": 20000,
            "risk_appetite": "medium",
            "financial_goals": "House",
        }

    monkeypatch.setattr(rr, "get_user_by_id", _fake_user)
    monkeypatch.setattr(rr, "calculate_health_score", lambda p: {"score": 70, "insights": [], "warnings": [], "pillar_scores": {}})
    monkeypatch.setattr(rr, "generate_financial_report", lambda p, h: (True, "## Financial Summary\nok"))

    def _fake_pdf(profile, health, ai_report, filename=None):
        with open(filename, "wb") as fh:
            fh.write(b"%PDF-1.4 fake")
        return True, filename

    monkeypatch.setattr(rr, "generate_pdf_report", _fake_pdf)
    monkeypatch.setattr(rr, "_save_report_to_db", lambda *a, **k: None)

    created = client.post(
        "/api/profile",
        data=json.dumps({
            "age": 30,
            "income": 90000,
            "expenses": 50000,
            "savings": 20000,
            "risk_appetite": "medium",
            "financial_goals": "House",
        }),
        headers=headers,
    )
    user_id = created.get_json()["user_id"]

    # Insert a real user id path uses get_user_by_id mock; body still needs user_id.
    statuses = []
    for _ in range(5):
        res = client.post(
            "/api/generate-report",
            data=json.dumps({"user_id": user_id}),
            headers=headers,
        )
        statuses.append(res.status_code)
        if res.status_code == 429:
            body = res.get_json()
            assert body["code"] == "rate_limit_exceeded"
            assert body["error"]
            break
    assert 429 in statuses, f"expected a 429 within burst, got {statuses}"
