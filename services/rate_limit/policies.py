"""Route-class policies for the Wave 1 gateway."""
from __future__ import annotations

from dataclasses import dataclass
import re

from limits import parse

from config import Config


@dataclass(frozen=True)
class LimitRule:
    route_class: str
    limit: int
    window_seconds: int
    per_user: bool = False
    token_bucket: bool = False
    refill_per_second: float = 0.0
    key_scope: str = ""


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    route_class: str | None
    limit: int | None = None
    remaining: int | None = None
    retry_after: int | None = None
    window_seconds: int | None = None
    fail_open: bool = False
    exempt: bool = False
    store_error: bool = False
    code: str = "rate_limit_exceeded"


def _rule(route_class: str, expr: str, per_user: bool = False) -> LimitRule:
    """Parse a limits expression such as '5 per minute' or '10 per hour'."""
    item = parse(expr)
    return LimitRule(route_class, int(item.amount), int(item.get_expiry()), per_user)


def _token_rule(route_class: str, capacity: int, refill_seconds: int, key_scope: str) -> LimitRule:
    """A full bucket holds `capacity` tokens and gains one token each `refill_seconds`."""
    return LimitRule(
        route_class,
        capacity,
        refill_seconds,
        token_bucket=True,
        refill_per_second=1 / refill_seconds,
        key_scope=key_scope,
    )


class PolicyRegistry:
    """Map method + path → one or more LimitRules."""

    def __init__(self) -> None:
        self.read_light = _rule("read_light", Config.RATELIMIT_READ_LIGHT)
        self.read_report = _rule("read_report", Config.RATELIMIT_READ)
        self.read_chat = _rule("read_chat", Config.RATELIMIT_READ_CHAT)
        self.read_download = _rule("read_download", Config.RATELIMIT_DOWNLOAD)
        self.pdf_rebuild = _rule("pdf_rebuild", Config.RATELIMIT_PDF_REBUILD)
        self.write_profile = _rule("write_profile", Config.RATELIMIT_WRITE_PROFILE)
        self.write_goal = _rule("write_goal", Config.RATELIMIT_GOAL)
        self.write_goal_user = _rule("write_goal", Config.RATELIMIT_GOAL_USER, per_user=True)
        self.delete_profile_user = _rule("write_profile", Config.RATELIMIT_DELETE_USER, per_user=True)
        self.llm_chat = _rule("llm_chat", Config.RATELIMIT_LLM_CHAT)
        self.llm_chat_user = _rule("llm_chat", Config.RATELIMIT_LLM_CHAT_USER, per_user=True)
        self.llm_report = _rule("llm_report", Config.RATELIMIT_LLM_REPORT)
        self.llm_report_user = _rule("llm_report", Config.RATELIMIT_LLM_REPORT_USER, per_user=True)
        self.auth_ip = _token_rule("auth_ip", 8, 15, "ip")
        self.auth_account = _token_rule("auth_account", 5, 600, "email")
        self.auth_refresh = _token_rule("auth_refresh", 4, 60, "session")
        self.auth_resend = _token_rule("auth_resend", 3, 600, "email")
        self.auth_login_code = _token_rule("auth_login_code", 5, 60, "email")
        self.auth_account_action = _token_rule("auth_account_action", 5, 60, "account")
        self.auth_challenge = LimitRule(
            "auth_challenge",
            5,
            0,
            token_bucket=True,
            refill_per_second=0.0,
            key_scope="challenge",
        )
        self.credential_failure = _rule("credential_failure", Config.RATELIMIT_AUTH)

    def rules_for(self, method: str, path: str) -> list[LimitRule] | None:
        """Return rules to apply, [] for exempt, None if no policy (allow)."""
        method = (method or "GET").upper()
        path = path or "/"

        if method == "OPTIONS":
            return []
        if path.rstrip("/") in ("/api/health", "/health"):
            return []

        if path.rstrip("/") in (
            "/api/auth/login",
            "/api/auth/signup",
            "/api/auth/forgot-password",
            "/api/auth/reset-password",
        ) and method == "POST":
            return [self.auth_ip]
        if path.rstrip("/") == "/api/auth/logout" and method == "POST":
            return []
        if path.rstrip("/") == "/api/auth/refresh" and method == "POST":
            return [self.auth_refresh]
        if path.rstrip("/") == "/api/auth/verify-email" and method == "POST":
            return [self.auth_ip]
        if path.rstrip("/") == "/api/auth/resend-verification" and method == "POST":
            return [self.auth_resend]
        if path.rstrip("/") in (
            "/api/auth/change-email",
            "/api/auth/change-password",
            "/api/auth/delete-account",
        ) and method == "POST":
            return [self.auth_account_action]
        if path.rstrip("/") == "/api/auth/login-code" and method == "POST":
            return []
        if path.rstrip("/") == "/api/auth/confirm-email" and method == "POST":
            return []
        if path.rstrip("/") == "/api/auth/me" and method == "GET":
            return [self.read_light]

        if method == "GET" and path.rstrip("/") == "/api/users":
            return [self.read_light]
        if method == "GET" and re.match(r"^/api/report/\d+$", path):
            return [self.read_report]
        if method == "GET" and re.match(r"^/api/download-report/\d+$", path):
            return [self.read_download]
        if method == "GET" and re.match(r"^/api/chat/history/\d+$", path):
            return [self.read_chat]

        if method == "GET" and re.match(r"^/api/profile/\d+$", path):
            return [self.read_light]
        if method == "POST" and path.rstrip("/") == "/api/profile":
            return [self.write_profile]
        if method == "DELETE" and re.match(r"^/api/profile/\d+$", path):
            return [self.write_profile, self.delete_profile_user]
        if method == "DELETE" and re.match(r"^/api/chat/history/\d+$", path):
            return [self.write_profile]

        if method == "POST" and path.rstrip("/") == "/api/goal-plan":
            return [self.write_goal, self.write_goal_user]
        if method == "POST" and path.rstrip("/") == "/api/chat":
            return [self.llm_chat, self.llm_chat_user]
        if method == "POST" and path.rstrip("/") == "/api/generate-report":
            return [self.llm_report, self.llm_report_user]

        return None

    @staticmethod
    def is_llm(route_class: str | None) -> bool:
        return route_class in ("llm_chat", "llm_report")

    @staticmethod
    def is_expensive(route_class: str | None) -> bool:
        return PolicyRegistry.is_llm(route_class) or route_class == "pdf_rebuild"

    @staticmethod
    def fails_closed(route_class: str | None) -> bool:
        return PolicyRegistry.is_expensive(route_class) or route_class in (
            "auth_ip",
            "auth_account",
            "auth_refresh",
            "auth_resend",
            "auth_login_code",
            "auth_challenge",
            "auth_account_action",
        )
