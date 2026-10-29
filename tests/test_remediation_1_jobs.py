"""Issue 1: report generation is a job. The request does not call Groq."""
import json

import config
import database.db as db_mod
from app import create_app
from database.repository import enqueue_report_job, get_report_job, mark_email_verified
from conftest import sign_in
from services.jobs.worker import process_once
from services.rate_limit import gateway as gw_mod


def _client(tmp_path, monkeypatch, name="jobs.db"):
    monkeypatch.setattr(db_mod, "DB_NAME", str(tmp_path / name))
    monkeypatch.setattr(config.Config, "RATELIMIT_STORAGE_BACKEND", "memory")
    monkeypatch.setattr(config.Config, "FLASK_ENV", "development")
    gw_mod._gateway = None
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _profile():
    return {
        "age": 30,
        "income": 100000,
        "expenses": 40000,
        "savings": 20000,
        "risk_appetite": "medium",
        "financial_goals": "house",
    }


def _headers():
    return {"Content-Type": "application/json"}


def _create_profile(client):
    sign_in(client, "jobs@example.com")
    res = client.post("/api/profile", data=json.dumps(_profile()), headers=_headers())
    assert res.status_code == 201
    return res.get_json()["user_id"]


def test_enqueue_does_not_call_groq_and_second_post_reuses_the_job(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    user_id = _create_profile(client)
    import routes.report_routes as rr

    def _boom(*_a, **_k):
        raise AssertionError("Groq must not run inside the request")

    monkeypatch.setattr(rr, "generate_financial_report", _boom)
    first = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=_headers(),
    )
    second = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=_headers(),
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.get_json()["job_id"] == second.get_json()["job_id"]
    assert first.get_json()["status"] == "queued"

    monkeypatch.setattr(rr, "generate_financial_report", lambda p, h: (True, "Queued advisory"))
    monkeypatch.setattr(rr, "generate_pdf_report", lambda *a, **k: (False, "no pdf"))
    finished = process_once()
    assert finished["status"] == "succeeded"
    stored = client.get(f"/api/report/{user_id}", headers=_headers())
    assert stored.status_code == 200
    assert stored.get_json()["ai_report"] == "Queued advisory"
    assert "job" not in stored.get_json()


def test_other_account_cannot_enqueue(tmp_path, monkeypatch):
    owner = _client(tmp_path, monkeypatch, "own.db")
    signup = owner.post(
        "/api/auth/signup",
        data=json.dumps({
            "email": "owner@example.com",
            "password": "correct-horse",
            "confirm_password": "correct-horse",
        }),
        headers={"Content-Type": "application/json"},
    )
    assert signup.status_code == 201
    mark_email_verified(signup.get_json()["account_id"])
    created = owner.post(
        "/api/profile",
        data=json.dumps(_profile()),
        headers={"Content-Type": "application/json"},
    )
    user_id = created.get_json()["user_id"]

    stranger = _client(tmp_path, monkeypatch, "own.db")
    stranger_signup = stranger.post(
        "/api/auth/signup",
        data=json.dumps({
            "email": "stranger@example.com",
            "password": "correct-horse",
            "confirm_password": "correct-horse",
        }),
        headers={"Content-Type": "application/json"},
    )
    assert stranger_signup.status_code == 201
    mark_email_verified(stranger_signup.get_json()["account_id"])
    denied = stranger.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers={"Content-Type": "application/json"},
    )
    assert denied.status_code == 400


def test_groq_failure_keeps_the_previous_report(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "fail.db")
    user_id = _create_profile(client)
    import routes.report_routes as rr

    monkeypatch.setattr(rr, "generate_financial_report", lambda p, h: (True, "Original advisory"))
    monkeypatch.setattr(rr, "generate_pdf_report", lambda *a, **k: (False, "no pdf"))
    assert client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=_headers(),
    ).status_code == 202
    assert process_once()["status"] == "succeeded"

    monkeypatch.setattr(
        rr,
        "generate_financial_report",
        lambda p, h: (False, {"error": "provider down", "code": "upstream_error"}),
    )
    again = client.post(
        "/api/generate-report",
        data=json.dumps({"user_id": user_id}),
        headers=_headers(),
    )
    assert again.status_code == 202
    failed = process_once()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "upstream_error"
    stored = client.get(f"/api/report/{user_id}", headers=_headers()).get_json()
    assert stored["ai_report"] == "Original advisory"
    assert stored["job"]["status"] == "failed"
    assert stored["job"]["error_code"] == "upstream_error"


def test_stale_running_job_is_failed_without_another_groq_call(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "stale.db")
    user_id = _create_profile(client)
    import routes.report_routes as rr

    def _boom(*_a, **_k):
        raise AssertionError("a lost worker must not call Groq again")

    monkeypatch.setattr(rr, "generate_financial_report", _boom)
    job = enqueue_report_job(user_id, None)
    conn = db_mod.get_connection()
    conn.execute(
        """
        UPDATE jobs
        SET status = 'running', started_at = CURRENT_TIMESTAMP - interval '1 day'
        WHERE id = :id
        """,
        {"id": job["job_id"]},
    )
    conn.commit()
    conn.close()

    assert process_once() is None
    row = get_report_job(job["job_id"])
    assert row["status"] == "failed"
    assert row["error_code"] == "worker_lost"


def test_worker_rejects_a_job_whose_owner_does_not_match(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "owner.db")
    user_id = _create_profile(client)
    import routes.report_routes as rr
    from database.repository import insert_account

    def _boom(*_a, **_k):
        raise AssertionError("owner mismatch must not call Groq")

    monkeypatch.setattr(rr, "generate_financial_report", _boom)
    other = insert_account("other-owner@example.com", "correct-horse")
    job = enqueue_report_job(user_id, other["id"])
    finished = process_once()
    assert finished["status"] == "failed"
    assert finished["error_code"] == "not_found"
    assert finished["error_detail"] == "owner_mismatch"
