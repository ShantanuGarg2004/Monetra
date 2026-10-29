import logging
from datetime import date, datetime

from flask import Flask, g, request, jsonify
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_limiter.errors import RateLimitExceeded
from flasgger import Swagger

from extensions import limiter
from routes.user_routes import user_bp
from routes.report_routes import report_bp
from routes.chat_routes import chat_bp
from routes.goal_routes import goal_bp
from routes.auth_routes import auth_bp
from database.models import create_tables
from database.db import close_request_connection, ping_database
from config import Config
from services.actor import Actor, resolve_actor
from services.rate_limit import build_gateway
from services.rate_limit.gateway import get_gateway, is_application_api, is_public_docs, uses_custom_gateway

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_DATA_PREFIXES = (
    "/api/users",
    "/api/profile",
    "/api/report",
    "/api/generate-report",
    "/api/download-report",
    "/api/chat",
    "/api/goal-plan",
)


def _is_data_route(path: str) -> bool:
    path = (path or "").rstrip("/")
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _DATA_PREFIXES)


def _requires_verified_email(method: str, path: str) -> bool:
    """Profile create, report, chat, goal, and PDF download stay closed until the email is verified."""
    path = (path or "").rstrip("/")
    method = (method or "GET").upper()
    if method == "POST" and path == "/api/profile":
        return True
    if method == "GET" and path.startswith("/api/profile/"):
        return True
    if method == "POST" and path == "/api/generate-report":
        return True
    if method == "GET" and path.startswith("/api/report/"):
        return True
    if method == "GET" and path.startswith("/api/download-report/"):
        return True
    if method == "POST" and path == "/api/chat":
        return True
    if path.startswith("/api/chat/"):
        return True
    if method == "POST" and path == "/api/goal-plan":
        return True
    if method == "POST" and path == "/api/auth/change-email":
        return True
    return False


def _actor_email_verified(actor: Actor) -> bool:
    if not str(actor.credential).isdigit():
        return False
    from database.repository import get_account_by_id

    account = get_account_by_id(int(actor.credential))
    return bool(account and account.get("email_verified_at") is not None)


def _required_scope(method: str, path: str) -> str | None:
    """data or llm for a scoped key. A browser session is not checked here."""
    path = (path or "").rstrip("/")
    if method == "POST" and path in ("/api/generate-report", "/api/chat"):
        return "llm"
    if _is_data_route(path):
        return "data"
    return None


class FinPilotJSONProvider(DefaultJSONProvider):
    """Timestamps from PostgreSQL are datetimes. The API still speaks JSON."""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def create_app():
    Config.validate()

    app = Flask(__name__)
    app.json = FinPilotJSONProvider(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": Config.CORS_ORIGINS}},
        supports_credentials=True,
    )

    # The gateway is the limiter when the backend is sql or memory.
    # Flask-Limiter stays imported for the route decorators and is turned off so it does not count twice.
    if uses_custom_gateway():
        limiter.enabled = False
        gateway = build_gateway()
        logger.info(
            "Wave 1 rate-limit gateway active (backend=%s, store_ping=%s)",
            Config.RATELIMIT_STORAGE_BACKEND,
            gateway.ping(),
        )
    else:
        limiter.enabled = Config.RATELIMIT_ENABLED
        logger.info("Flask-Limiter active (legacy backend=%s)", Config.RATELIMIT_STORAGE_BACKEND)

    limiter.init_app(app)

    # Application data lives in PostgreSQL (separate database from the limiter).
    create_tables()
    app.teardown_appcontext(close_request_connection)

    def _local_env() -> bool:
        return Config.FLASK_ENV in ("development", "dev", "local")

    def _unauthorized(challenge_docs: bool = False):
        logger.warning("Rejected request — bad API key from %s", request.remote_addr)
        resp = jsonify({
            "error": "Unauthorised — invalid or missing X-API-Key header",
            "code": "unauthorized",
        })
        resp.status_code = 401
        if challenge_docs:
            resp.headers["WWW-Authenticate"] = 'Basic realm="FinPilot API docs"'
        return resp

    def _bind_actor():
        actor = resolve_actor(request)
        if actor is None:
            return None
        g.actor = actor
        return actor

    def _count_rejected_credential():
        """A presented key that matched nothing counts against this address before the 401."""
        gw = get_gateway()
        if gw is None:
            return None
        decision = gw.note_rejected_credential(request.remote_addr or "")
        if decision is not None and not decision.allowed:
            return gw.denial_response(decision)
        return None

    # ── Auth then rate-limit ───────────────────────────────────────────────
    @app.before_request
    def require_api_key():
        """Cookie first, then a scoped credential. API_SECRET_KEY opens local docs only."""
        if request.method == "OPTIONS":
            g.actor = Actor(kind="anonymous")
            return
        if request.path == "/" or request.path.rstrip("/") == "/api/health":
            g.actor = Actor(kind="anonymous")
            return
        if request.method == "POST" and request.path.rstrip("/") in (
            "/api/auth/login",
            "/api/auth/signup",
            "/api/auth/logout",
            "/api/auth/refresh",
            "/api/auth/verify-email",
            "/api/auth/forgot-password",
            "/api/auth/reset-password",
            "/api/auth/confirm-email",
        ):
            g.actor = Actor(kind="anonymous")
            return
        if is_public_docs(request.path):
            if not _local_env():
                return jsonify({"error": "Not found", "code": "not_found"}), 404
            if _bind_actor() is None:
                if getattr(g, "auth_error", None) == "unauthorized":
                    denied = _count_rejected_credential()
                    if denied is not None:
                        return denied
                return _unauthorized(challenge_docs=True)
            return
        if not is_application_api(request.path):
            return

        if _bind_actor() is None:
            if getattr(g, "auth_error", None) == "unauthorized":
                denied = _count_rejected_credential()
                if denied is not None:
                    return denied
                return _unauthorized()
            return jsonify({
                "error": "Your session ended. Sign in again.",
                "code": "session_expired",
            }), 401

        if g.actor.kind == "api_key":
            needed = _required_scope(request.method, request.path)
            if needed is not None and not g.actor.has_scope(needed):
                return jsonify({
                    "error": "This API key cannot call this route.",
                    "code": "forbidden",
                }), 403

        if g.actor.kind in ("user", "api_key") and _requires_verified_email(request.method, request.path):
            if not _actor_email_verified(g.actor):
                return jsonify({
                    "error": "Verify your email before using this part of FinPilot.",
                    "code": "email_unverified",
                }), 403

    @app.before_request
    def enforce_rate_limit():
        """Apply the gateway. Health is exempt. Flask-Limiter is not the live counter."""
        if request.method == "OPTIONS":
            return
        if is_public_docs(request.path) or not is_application_api(request.path):
            return
        if request.path.rstrip("/") == "/api/health":
            return
        gw = get_gateway()
        if not gw:
            return
        decision = gw.check(request)
        if decision is not None and not decision.allowed and not decision.exempt:
            return gw.denial_response(decision)

    # ── Legacy Flask-Limiter 429 shape (if ever re-enabled) ────────────────
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(exc: RateLimitExceeded):
        retry_after = None
        try:
            for item in exc.get_headers() or []:
                if str(item[0]).lower() == "retry-after":
                    retry_after = int(item[1])
                    break
        except Exception:
            retry_after = None

        body = {
            "error": "Rate limit exceeded",
            "code": "rate_limit_exceeded",
            "retry_after": retry_after,
            "limit": str(exc.description) if exc.description else None,
        }
        resp = jsonify(body)
        resp.status_code = 429
        if retry_after is not None:
            resp.headers["Retry-After"] = str(retry_after)
        return resp

    # ── Swagger ───────────────────────────────────────────────────────────
    swagger_config = {
        "headers": [],
        "specs": [{"endpoint": "apispec", "route": "/apispec.json",
                   "rule_filter": lambda rule: True,
                   "model_filter": lambda tag: True}],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }
    swagger_template = {
        "securityDefinitions": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "name": "X-API-Key",
                "in": "header",
                "description": (
                    "Local docs password (API_SECRET_KEY). "
                    "It only opens this page. "
                    "It does not open profiles, reports, chat, or goals. "
                    "A scoped key is issued with scripts/issue_api_credential.py "
                    "and sent as X-API-Key. "
                    "A browser signs in and sends the finpilot_access cookie."
                ),
            }
        },
        "security": [{"ApiKeyAuth": []}],
    }
    if Config.FLASK_ENV in ("development", "dev", "local"):
        Swagger(app, config=swagger_config, template=swagger_template)
    else:
        logger.info("Swagger disabled because FLASK_ENV=%s", Config.FLASK_ENV)

    @app.route("/")
    def home():
        return "AI Financial Advisor Backend Running 🚀"

    @app.route("/api/health")
    def health():
        """
        Liveness probe. No API key and no session.
        ---
        tags:
          - Health
        security: []
        responses:
          200:
            description: Process is up and the application database answered
          503:
            description: Rate-limit store or application database is down
        """
        gw = get_gateway()
        store_ok = gw.ping() if gw else None
        database_ok = ping_database()
        status = "ok" if store_ok is not False and database_ok else "degraded"
        return jsonify({
            "status": status,
            "database_ok": database_ok,
            "ratelimit_store_ok": store_ok,
        }), (200 if status == "ok" else 503)

    @app.after_request
    def private_api_responses(response):
        """Authenticated JSON must not be reused for the next account."""
        if request.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(user_bp, url_prefix="/api")
    app.register_blueprint(report_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(goal_bp, url_prefix="/api")

    logger.info(
        "App ready — ratelimit enabled=%s backend=%s flask_limiter=%s",
        Config.RATELIMIT_ENABLED,
        Config.RATELIMIT_STORAGE_BACKEND,
        limiter.enabled,
    )
    return app


def serve():
    """Local debugger only. A production-shaped environment exits before listen."""
    if Config.FLASK_ENV not in ("development", "dev", "local"):
        logger.error(
            "This entrypoint is the local debugger. It does not listen outside a local environment."
        )
        raise SystemExit(1)
    application = create_app()
    application.run(debug=True)


if __name__ == "__main__":
    serve()
