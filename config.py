import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _split_csv(raw: str | None, default: list[str]) -> list[str]:
    if raw is None:
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    # ── LLM provider: Groq (OpenAI-compatible) ──────────────────────────────
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    # Per-service model selection (overridable via .env).
    GROQ_REPORT_MODEL = os.getenv("GROQ_REPORT_MODEL", "openai/gpt-oss-120b")
    GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
    # Q6 load test. When true, ask_gpt returns fixed text and does not call Groq.
    GROQ_STUB = _env_bool("GROQ_STUB", False)

    # Wave 0: split token budgets (report needs full 6-section output).
    GROQ_REPORT_MAX_TOKENS = _env_int("GROQ_REPORT_MAX_TOKENS", 4096)
    GROQ_CHAT_MAX_TOKENS = _env_int("GROQ_CHAT_MAX_TOKENS", 1500)
    # Wave 3: Groq call budget. Worker/proxy timeout must be larger than this.
    GROQ_TIMEOUT_SECONDS = _env_int("GROQ_TIMEOUT_SECONDS", 90)
    WORKER_TIMEOUT_SECONDS = _env_int("WORKER_TIMEOUT_SECONDS", 120)
    # Claim threads inside this one worker process. Extra processes each open a pool.
    WORKER_CLAIM_THREADS = _env_int("WORKER_CLAIM_THREADS", 1)
    # In-flight LLM calls the process tier should absorb, plus spare workers for reads.
    PEAK_CONCURRENT_LLM = _env_int("PEAK_CONCURRENT_LLM", 4)
    WORKER_HEADROOM = _env_int("WORKER_HEADROOM", 2)
    # Off by default. A normal start does not open a SQLite file.
    SQLITE_IMPORT = _env_bool("SQLITE_IMPORT", False)
    # Q3: PDF bytes live on disk. The row stores the file name, not the blob.
    _ROOT = os.path.dirname(os.path.abspath(__file__))
    PDF_STORAGE_DIR = os.getenv("PDF_STORAGE_DIR", os.path.join(_ROOT, "data", "pdfs"))

    # Secret key scripts and Swagger send as X-API-Key. Not the session signer.
    API_SECRET_KEY = os.getenv("API_SECRET_KEY")
    # Signs finpilot_access. Must differ from API_SECRET_KEY.
    SESSION_SECRET = os.getenv("SESSION_SECRET")
    # Transactional mail. Unset skips the network in every environment.
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    EMAIL_FROM = os.getenv("EMAIL_FROM")
    APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://localhost:5173")

    # Rate limiting (Wave 0 Flask-Limiter + Wave 1 SQL store prep)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = _env_bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_BACKEND = (os.getenv("RATELIMIT_STORAGE_BACKEND") or "memory").lower()
    RATELIMIT_DATABASE_URL = os.getenv("RATELIMIT_DATABASE_URL")
    # Application data. Separate database from the rate-limit store.
    APP_DATABASE_URL = os.getenv(
        "APP_DATABASE_URL",
        "postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot",
    )
    FLASK_ENV = (os.getenv("FLASK_ENV") or os.getenv("FINPILOT_ENV") or "production").lower()

    # Quota strings. PolicyRegistry parses these with the `limits` package.
    _dev = FLASK_ENV in ("development", "dev", "local")
    _read = "600 per minute" if _dev else "120 per minute"
    _light = "600 per minute" if _dev else "300 per minute"
    RATELIMIT_READ = os.getenv("RATELIMIT_READ", _read)
    RATELIMIT_READ_LIGHT = os.getenv("RATELIMIT_READ_LIGHT", _light)
    RATELIMIT_READ_CHAT = os.getenv("RATELIMIT_READ_CHAT", _read)
    RATELIMIT_DOWNLOAD = os.getenv("RATELIMIT_DOWNLOAD", _read)
    RATELIMIT_PDF_REBUILD = os.getenv("RATELIMIT_PDF_REBUILD", "5 per minute")
    RATELIMIT_WRITE_PROFILE = os.getenv("RATELIMIT_WRITE_PROFILE", "30 per minute")
    RATELIMIT_LLM_CHAT = os.getenv("RATELIMIT_LLM_CHAT", "15 per minute")
    RATELIMIT_LLM_CHAT_USER = os.getenv("RATELIMIT_LLM_CHAT_USER", "60 per hour")
    RATELIMIT_LLM_REPORT = os.getenv("RATELIMIT_LLM_REPORT", "5 per minute")
    RATELIMIT_LLM_REPORT_USER = os.getenv("RATELIMIT_LLM_REPORT_USER", "10 per hour")
    RATELIMIT_GOAL = os.getenv("RATELIMIT_GOAL", "20 per minute")
    RATELIMIT_GOAL_USER = os.getenv("RATELIMIT_GOAL_USER", "60 per hour")
    RATELIMIT_DELETE_USER = os.getenv("RATELIMIT_DELETE_USER", "30 per hour")
    RATELIMIT_AUTH = os.getenv("RATELIMIT_AUTH", "20 per minute")
    BOOTSTRAP_ACCOUNT_EMAIL = os.getenv("BOOTSTRAP_ACCOUNT_EMAIL")
    BOOTSTRAP_ACCOUNT_PASSWORD = os.getenv("BOOTSTRAP_ACCOUNT_PASSWORD")

    # Q4: browser origins. Unset means local Vite only. Empty is rejected in production.
    CORS_ORIGINS = _split_csv(
        os.getenv("CORS_ORIGINS"),
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )

    @classmethod
    def validate(cls):
        missing = [k for k in ("GROQ_API_KEY", "API_SECRET_KEY", "SESSION_SECRET") if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Add them to your .env file."
            )
        if len(cls.SESSION_SECRET) < 32:
            raise EnvironmentError(
                "SESSION_SECRET must be at least 32 characters."
            )
        if cls.SESSION_SECRET == cls.API_SECRET_KEY:
            raise EnvironmentError(
                "SESSION_SECRET must be different from API_SECRET_KEY."
            )
        if not cls.APP_DATABASE_URL:
            raise EnvironmentError(
                "APP_DATABASE_URL is required (PostgreSQL database for profiles, reports, and chat)."
            )
        if cls.RATELIMIT_ENABLED and cls.RATELIMIT_STORAGE_BACKEND == "sql":
            if not cls.RATELIMIT_DATABASE_URL:
                raise EnvironmentError(
                    "RATELIMIT_STORAGE_BACKEND=sql requires RATELIMIT_DATABASE_URL "
                    "(PostgreSQL SQLAlchemy URL)."
                )
        if cls.FLASK_ENV not in ("development", "dev", "local") and not cls.CORS_ORIGINS:
            raise EnvironmentError(
                "CORS_ORIGINS must list at least one frontend origin when FLASK_ENV is not local."
            )
        if (
            cls.FLASK_ENV not in ("development", "dev", "local")
            and _is_local_database_default(cls.APP_DATABASE_URL)
        ):
            raise EnvironmentError(
                "APP_DATABASE_URL is still the local default. Set a production database URL."
            )
        if cls.WORKER_TIMEOUT_SECONDS <= cls.GROQ_TIMEOUT_SECONDS:
            raise EnvironmentError(
                "WORKER_TIMEOUT_SECONDS must be greater than GROQ_TIMEOUT_SECONDS "
                "so a slow Groq call returns upstream_timeout instead of a worker kill."
            )


def _is_local_database_default(url: str | None) -> bool:
    """True for the Compose database named finpilot when it still uses the dev password.

    The test database is a different name, so the suite can keep using the local server.
    """
    raw = url or ""
    if "finpilot_dev_password" not in raw:
        return False
    name = raw.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    return name == "finpilot"


def recommended_worker_count(
    peak_concurrent_llm: int | None = None,
    headroom: int | None = None,
) -> int:
    """workers ≈ peak in-flight LLM calls + headroom for cheap reads."""
    peak = Config.PEAK_CONCURRENT_LLM if peak_concurrent_llm is None else peak_concurrent_llm
    extra = Config.WORKER_HEADROOM if headroom is None else headroom
    return max(2, int(peak) + int(extra))
