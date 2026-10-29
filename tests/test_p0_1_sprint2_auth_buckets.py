"""Sprint 2: auth routes use a token bucket. Other quotas stay fixed-window."""
import json

from flask import Flask, request

import config
import database.db as db_mod
from app import create_app
from services.rate_limit.gateway import RateLimitGateway
from services.rate_limit.memory_store import MemoryRateLimitStore
from services.rate_limit.policies import PolicyRegistry
from services.rate_limit import gateway as gw_mod
from database.repository import mark_email_verified
from services.rate_limit.store import token_retry_after


def _clock(box):
    return lambda: box["t"]


def test_bucket_starts_full_refills_one_token_and_caps_at_capacity():
    box = {"t": 1_000.0}
    store = MemoryRateLimitStore(clock=_clock(box))
    capacity = 8
    refill = 1 / 15
    allowed = [store.take_token("ip:203.0.113.8:auth_ip", capacity, refill) for _ in range(capacity)]
    assert all(item.allowed for item in allowed)
    assert allowed[0].remaining == capacity - 1
    blocked = store.take_token("ip:203.0.113.8:auth_ip", capacity, refill)
    assert blocked.allowed is False
    assert blocked.retry_after == token_retry_after(0, refill)
    assert blocked.retry_after == 15

    box["t"] += 15
    refilled = store.take_token("ip:203.0.113.8:auth_ip", capacity, refill)
    assert refilled.allowed is True
    assert refilled.remaining == 0

    box["t"] += 10_000
    capped = store.take_token("ip:203.0.113.8:auth_ip", capacity, refill)
    assert capped.allowed is True
    assert capped.remaining == capacity - 1


def test_auth_policies_keep_other_quotas_on_a_fixed_window():
    pol = PolicyRegistry()
    assert pol.auth_ip.token_bucket is True
    assert pol.auth_ip.limit == 8
    assert pol.auth_ip.window_seconds == 15
    assert pol.auth_account.limit == 5
    assert pol.auth_account.window_seconds == 600
    assert pol.auth_refresh.limit == 4
    assert pol.auth_refresh.window_seconds == 60
    assert pol.rules_for("POST", "/api/auth/logout") == []
    assert pol.rules_for("POST", "/api/auth/login")[0].route_class == "auth_ip"
    assert pol.rules_for("POST", "/api/auth/refresh")[0].route_class == "auth_refresh"
    report = pol.rules_for("POST", "/api/generate-report")
    assert all(rule.token_bucket is False for rule in report)
    assert pol.credential_failure.token_bucket is False
    assert pol.credential_failure.limit == 20


class _DownStore(MemoryRateLimitStore):
    def take_token(self, key, capacity, refill_per_second):
        raise RuntimeError("store down")


def test_auth_bucket_store_error_fails_closed():
    gateway = RateLimitGateway(_DownStore())
    app = Flask(__name__)
    with app.test_request_context("/api/auth/login", method="POST"):
        decision = gateway.check(request)
    assert decision is not None
    assert decision.allowed is False
    assert decision.fail_open is False
    assert decision.route_class == "auth_ip"
    assert decision.retry_after == 30


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "RATELIMIT_ENABLED", True)
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), headers={"Content-Type": "application/json"})


def test_ninth_login_from_one_address_returns_retry_after(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "auth-ip.db")
    for _ in range(8):
        res = _post(client, "/api/auth/login", {})
        assert res.status_code == 400
    blocked = _post(client, "/api/auth/login", {"email": "person@example.com", "password": "correct-horse"})
    assert blocked.status_code == 429
    body = blocked.get_json()
    assert body["code"] == "rate_limit_exceeded"
    assert body["route_class"] == "auth_ip"
    assert body["retry_after"] == 15
    assert blocked.headers["Retry-After"] == "15"


def test_failed_password_bucket_allows_a_later_correct_password(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "auth-account.db")
    created = _post(client, "/api/auth/signup", {
        "email": "locked@example.com",
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    })
    assert created.status_code == 201
    for _ in range(5):
        bad = _post(client, "/api/auth/login", {"email": "locked@example.com", "password": "not-the-password"})
        assert bad.status_code == 401
        assert bad.get_json()["code"] == "invalid_credentials"
    blocked = _post(client, "/api/auth/login", {"email": "locked@example.com", "password": "not-the-password"})
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_account"
    assert blocked.get_json()["retry_after"] == 600
    mark_email_verified(created.get_json()["account_id"])
    signed = _post(client, "/api/auth/login", {"email": "locked@example.com", "password": "correct-horse"})
    assert signed.status_code == 200
    assert signed.get_json()["otp_required"] is True


def test_fifth_refresh_is_limited_and_logout_is_not(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "auth-refresh.db")
    assert _post(client, "/api/auth/signup", {
        "email": "refresh-limit@example.com",
        "password": "correct-horse",
        "confirm_password": "correct-horse",
    }).status_code == 201
    for _ in range(4):
        assert client.post("/api/auth/refresh").status_code == 200
    blocked = client.post("/api/auth/refresh")
    assert blocked.status_code == 429
    assert blocked.get_json()["route_class"] == "auth_refresh"
    assert blocked.get_json()["retry_after"] == 60
    assert client.get("/api/auth/me").status_code == 200
    for _ in range(12):
        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 200
