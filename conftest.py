"""
Pytest bootstrap for the FinPilot backend test suite.

This runs before any test module is imported, so it is the right place to:
  1. Put the project root on sys.path (enables `import config`, `import services.*`).
  2. Establish a deterministic, offline test environment. Values are set with
     ``setdefault`` BEFORE `config` is imported, so `config.load_dotenv(override=False)`
     will not clobber them and the Groq client can be constructed without a real key
     (every network call is mocked in the tests).
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("EMAIL_API_KEY", "")
os.environ.setdefault("EMAIL_FROM", "")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("API_SECRET_KEY", "test-api-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-the-api-key-32")
os.environ.setdefault("GROQ_REPORT_MODEL", "openai/gpt-oss-120b")
os.environ.setdefault("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
os.environ.setdefault("GROQ_REPORT_MAX_TOKENS", "4096")
os.environ.setdefault("GROQ_CHAT_MAX_TOKENS", "1500")
os.environ.setdefault("GROQ_TIMEOUT_SECONDS", "90")
os.environ.setdefault("WORKER_TIMEOUT_SECONDS", "120")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("RATELIMIT_ENABLED", "true")
# Tests use in-memory Wave 1 store by default (no Postgres required).
os.environ.setdefault("RATELIMIT_STORAGE_BACKEND", "memory")
os.environ.setdefault(
    "APP_DATABASE_URL",
    "postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot_test",
)
os.environ.setdefault("FLASK_ENV", "production")
os.environ.setdefault("BOOTSTRAP_ACCOUNT_EMAIL", "bootstrap@finpilot.local")
os.environ.setdefault("BOOTSTRAP_ACCOUNT_PASSWORD", "bootstrap-test-password")
os.environ.setdefault(
    "PDF_STORAGE_DIR",
    os.path.join(tempfile.gettempdir(), "finpilot-pytest-pdfs"),
)


def sign_in(client, email="person@example.com", password="correct-horse"):
    """Create an account on this test client and keep its session cookie."""
    import json

    res = client.post(
        "/api/auth/signup",
        data=json.dumps({
            "email": email,
            "password": password,
            "confirm_password": password,
        }),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 201, res.get_data(as_text=True)
    from database.repository import mark_email_verified
    mark_email_verified(res.get_json()["account_id"])
    return {"Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _predictable_login_code(monkeypatch):
    """Sign-in codes are fixed in tests. The mail call does not touch Resend."""
    from tests.auth_client import LOGIN_CODE
    import services.login_code as login_code

    monkeypatch.setattr(login_code, "generate_login_code", lambda: LOGIN_CODE)
    monkeypatch.setattr(login_code, "send_email", lambda *args, **kwargs: True)
