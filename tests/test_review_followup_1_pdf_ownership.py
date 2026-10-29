"""Follow-up 1: PDF download checks ownership before reading the file."""
import json

import config
import database.db as db_mod
from app import create_app
from conftest import sign_in
from database.repository import issue_api_credential, save_report, store_pdf
from services.rate_limit import gateway as gw_mod

_MISSING = {
    "error": "No report found. Generate one first.",
    "code": "not_found",
}


def _app(tmp_path, monkeypatch, name):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    monkeypatch.setattr(config.Config, "PDF_STORAGE_DIR", str(tmp_path / "pdfs"))
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


def test_owner_downloads_pdf_and_stranger_gets_the_missing_report_body(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "pdf-own.db")
    sign_in(client, "owner@example.com")
    owner_id = _create(client, "house-owner")
    save_report(owner_id, {"score": 70}, "private advisory")
    store_pdf(owner_id, b"%PDF-owner")

    own = client.get(f"/api/download-report/{owner_id}")
    assert own.status_code == 200
    assert own.data == b"%PDF-owner"

    _drop_cookie(client)
    sign_in(client, "stranger@example.com")
    _create(client, "house-stranger")
    hidden = client.get(f"/api/download-report/{owner_id}")
    assert hidden.status_code == 404
    assert hidden.get_json() == _MISSING
    assert b"%PDF-owner" not in hidden.data
    assert b"private advisory" not in hidden.data

    absent = client.get("/api/download-report/999999")
    assert absent.status_code == 404
    assert absent.get_json() == _MISSING


def test_stranger_does_not_receive_advisory_text_when_the_file_is_missing(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "pdf-text.db")
    sign_in(client, "owner@example.com")
    owner_id = _create(client, "house-owner")
    save_report(owner_id, {"score": 70}, "private advisory")
    _drop_cookie(client)

    sign_in(client, "stranger@example.com")
    hidden = client.get(f"/api/download-report/{owner_id}")
    assert hidden.status_code == 404
    assert hidden.get_json() == _MISSING
    assert "private advisory" not in hidden.get_data(as_text=True)


def test_data_scope_downloads_and_llm_scope_is_forbidden(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, "pdf-scope.db")
    sign_in(client, "owner@example.com")
    account_id = client.get("/api/auth/me").get_json()["account_id"]
    owner_id = _create(client, "house-owner")
    save_report(owner_id, {"score": 70}, "private advisory")
    store_pdf(owner_id, b"%PDF-scoped")
    data_key, _data_id = issue_api_credential(account_id, "data-only", ["data"])
    llm_key, _llm_id = issue_api_credential(account_id, "llm-only", ["llm"])
    _drop_cookie(client)

    downloaded = client.get(
        f"/api/download-report/{owner_id}",
        headers={"X-API-Key": data_key},
    )
    assert downloaded.status_code == 200
    assert downloaded.data == b"%PDF-scoped"

    forbidden = client.get(
        f"/api/download-report/{owner_id}",
        headers={"X-API-Key": llm_key},
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["code"] == "forbidden"
