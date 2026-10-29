"""Flask before-request rate-limit gateway."""
from __future__ import annotations

import hashlib
import logging
import math
import random
import threading
from typing import Any

from flask import Request, g, jsonify

from config import Config
from services.actor import Actor
from .keys import build_bucket_key
from .memory_store import MemoryRateLimitStore
from .policies import LimitDecision, LimitRule, PolicyRegistry
from .sql_store import SqlRateLimitStore
from .store import RateLimitStore

logger = logging.getLogger(__name__)


def is_application_api(path: str) -> bool:
    """True for /api and /api/..., not for /apidocs (which only shares the /api prefix)."""
    path = path or ""
    return path == "/api" or path.startswith("/api/")


def is_public_docs(path: str) -> bool:
    path = path or ""
    return (
        path == "/apidocs"
        or path.startswith("/apidocs/")
        or path == "/apispec.json"
        or path.startswith("/flasgger_static")
    )


def _extract_user_id(req: Request) -> int | None:
    # Path params like /report/12
    for part in (req.view_args or {}).values():
        if isinstance(part, int):
            return part
    # JSON body (cached by Flask)
    data = req.get_json(silent=True)
    if isinstance(data, dict) and "user_id" in data:
        try:
            return int(data["user_id"])
        except (TypeError, ValueError):
            return None
    return None


class RateLimitGateway:
    def __init__(self, store: RateLimitStore, policies: PolicyRegistry | None = None) -> None:
        self.store = store
        self.policies = policies or PolicyRegistry()
        self._checks = 0
        self._lock = threading.Lock()

    def check(self, req: Request) -> LimitDecision | None:
        """
        Return a deny decision, or None when the request may proceed.
        Exempt / unmapped routes return None.
        """
        if not Config.RATELIMIT_ENABLED:
            return None

        rules = self.policies.rules_for(req.method, req.path)
        if rules is None:
            if is_application_api(req.path):
                return LimitDecision(
                    allowed=False,
                    route_class=None,
                    code="rate_policy_missing",
                )
            return None
        if rules == []:
            return LimitDecision(allowed=True, route_class=None, exempt=True)

        actor = _actor_for(req)
        user_id = _extract_user_id(req)

        maybe_cleanup()

        last_ok: LimitDecision | None = None
        for rule in rules:
            decision = self._apply_rule(actor, user_id, rule, req)
            if decision is None:
                # store failure handled per fail-open/closed
                continue
            if not decision.allowed:
                return decision
            last_ok = decision
        return last_ok

    def note_rejected_credential(self, remote_addr: str) -> LimitDecision | None:
        """Count a presented key that matched nothing. The bucket is the client address."""
        if not Config.RATELIMIT_ENABLED:
            return None
        address = (remote_addr or "").strip() or "unknown"
        rule = self.policies.credential_failure
        key = build_bucket_key(f"ip:{address}", rule.route_class)
        try:
            result = self.store.incr_and_check(key, rule.window_seconds, rule.limit)
        except Exception:
            logger.exception("rate limit store error for %s", rule.route_class)
            return LimitDecision(
                allowed=False,
                route_class=rule.route_class,
                limit=rule.limit,
                remaining=0,
                retry_after=30,
                window_seconds=rule.window_seconds,
                fail_open=False,
            )
        return LimitDecision(
            allowed=result.allowed,
            route_class=rule.route_class,
            limit=result.limit,
            remaining=result.remaining,
            retry_after=result.retry_after,
            window_seconds=result.window_seconds,
        )

    def consume(self, req: Request, rule: LimitRule) -> LimitDecision | None:
        """Count one extra bucket. Used for PDF rebuild, which is not a cheap read."""
        if not Config.RATELIMIT_ENABLED:
            return None
        return self._apply_rule(_actor_for(req), _extract_user_id(req), rule, req)

    def note_failed_password(self, email: str) -> LimitDecision | None:
        """Spend auth_account after a wrong password. A correct password does not call this."""
        if not Config.RATELIMIT_ENABLED:
            return None
        rule = self.policies.auth_account
        normalized = (email or "").strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        key = f"email:{digest}:{rule.route_class}"
        return self._take_token(rule, key)

    def note_resend(self, email: str) -> LimitDecision | None:
        """Spend auth_resend for a verification resend or a password-reset send."""
        return self._note_email_bucket(self.policies.auth_resend, email)

    def note_login_code(self, email: str) -> LimitDecision | None:
        """Spend auth_login_code before emailing a sign-in code. Capacity 5, one token per 60 seconds."""
        return self._note_email_bucket(self.policies.auth_login_code, email)

    def _note_email_bucket(self, rule: LimitRule, email: str) -> LimitDecision | None:
        if not Config.RATELIMIT_ENABLED:
            return None
        normalized = (email or "").strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        key = f"email:{digest}:{rule.route_class}"
        return self._take_token(rule, key)

    def note_wrong_challenge(self, challenge_id: int) -> LimitDecision | None:
        """Spend one no-refill token for a wrong challenge secret."""
        if not Config.RATELIMIT_ENABLED:
            return None
        rule = self.policies.auth_challenge
        key = f"challenge:{int(challenge_id)}:{rule.route_class}"
        return self._take_token(rule, key)

    def _apply_rule(self, actor: Actor, user_id: int | None, rule: LimitRule, req: Request | None = None) -> LimitDecision | None:
        if rule.per_user and user_id is None:
            # Cannot enforce per-user without id — skip this rule rather than block reads.
            return LimitDecision(
                allowed=True,
                route_class=rule.route_class,
                limit=rule.limit,
                remaining=rule.limit,
                window_seconds=rule.window_seconds,
            )

        key = build_bucket_key(
            actor.rate_limit_subject(),
            rule.route_class,
            user_id if rule.per_user else None,
        )
        if rule.token_bucket:
            return self._take_token(rule, self._token_key(rule, req))

        try:
            result = self.store.incr_and_check(key, rule.window_seconds, rule.limit)
        except Exception:
            logger.exception("rate limit store error for %s", rule.route_class)
            return self._store_failure(rule)

        return LimitDecision(
            allowed=result.allowed,
            route_class=rule.route_class,
            limit=result.limit,
            remaining=result.remaining,
            retry_after=result.retry_after,
            window_seconds=result.window_seconds,
        )

    def _token_key(self, rule: LimitRule, req: Request | None) -> str:
        if rule.key_scope == "ip":
            address = ((req.remote_addr if req is not None else "") or "").strip() or "unknown"
            return f"ip:{address}:{rule.route_class}"
        if rule.key_scope == "session":
            from services.sessions import REFRESH_COOKIE, refresh_session_subject

            raw = req.cookies.get(REFRESH_COOKIE, "") if req is not None else ""
            try:
                subject = refresh_session_subject(raw)
            except Exception:
                logger.exception("refresh session lookup failed")
                subject = "session:unknown"
            return f"{subject}:{rule.route_class}"
        if rule.key_scope == "email":
            from database.repository import get_account_by_id

            actor = getattr(g, "actor", None)
            email = ""
            if actor is not None and getattr(actor, "kind", "") in ("user", "api_key"):
                if str(getattr(actor, "credential", "")).isdigit():
                    account = get_account_by_id(int(actor.credential))
                    email = (account or {}).get("email") or ""
            digest = hashlib.sha256((email or "unknown").strip().lower().encode("utf-8")).hexdigest()
            return f"email:{digest}:{rule.route_class}"
        if rule.key_scope == "account":
            actor = getattr(g, "actor", None)
            account_id = "unknown"
            if actor is not None and getattr(actor, "kind", "") in ("user", "api_key"):
                if str(getattr(actor, "credential", "")).isdigit():
                    account_id = str(int(actor.credential))
            return f"acct:{account_id}:{rule.route_class}"
        raise ValueError(f"unsupported token bucket scope: {rule.key_scope}")

    def _take_token(self, rule: LimitRule, key: str) -> LimitDecision:
        try:
            result = self.store.take_token(key, rule.limit, rule.refill_per_second)
        except Exception:
            logger.exception("rate limit store error for %s", rule.route_class)
            return self._store_failure(rule)
        return LimitDecision(
            allowed=result.allowed,
            route_class=rule.route_class,
            limit=result.capacity,
            remaining=max(0, math.floor(result.remaining)),
            retry_after=result.retry_after,
            window_seconds=rule.window_seconds,
        )

    def _store_failure(self, rule: LimitRule) -> LimitDecision:
        if PolicyRegistry.fails_closed(rule.route_class):
            return LimitDecision(
                allowed=False,
                route_class=rule.route_class,
                limit=rule.limit,
                remaining=0,
                retry_after=30,
                window_seconds=rule.window_seconds,
                fail_open=False,
                store_error=True,
            )
        return LimitDecision(
            allowed=True,
            route_class=rule.route_class,
            limit=rule.limit,
            remaining=rule.limit,
            window_seconds=rule.window_seconds,
            fail_open=True,
        )

    def denial_response(self, decision: LimitDecision):
        body = {
            "error": (
                "No rate policy for this route"
                if decision.code == "rate_policy_missing"
                else "Rate limit exceeded"
            ),
            "code": decision.code,
            "route_class": decision.route_class,
            "retry_after": decision.retry_after,
            "limit": decision.limit,
            "window_seconds": decision.window_seconds,
        }
        resp = jsonify(body)
        resp.status_code = 429
        if decision.retry_after is not None:
            resp.headers["Retry-After"] = str(decision.retry_after)
        if decision.limit is not None:
            resp.headers["X-RateLimit-Limit"] = str(decision.limit)
        if decision.remaining is not None:
            resp.headers["X-RateLimit-Remaining"] = str(max(0, decision.remaining))
        return resp

    def ping(self) -> bool:
        return self.store.ping()


_gateway: RateLimitGateway | None = None
_cleanup_counter = 0
_cleanup_lock = threading.Lock()


def build_store() -> RateLimitStore:
    backend = (Config.RATELIMIT_STORAGE_BACKEND or "memory").lower()
    if backend == "sql":
        return SqlRateLimitStore(Config.RATELIMIT_DATABASE_URL or "")
    # memory (and unknown) → in-process store
    return MemoryRateLimitStore()


def build_gateway() -> RateLimitGateway:
    global _gateway
    store = build_store()
    _gateway = RateLimitGateway(store)
    return _gateway


def get_gateway() -> RateLimitGateway | None:
    return _gateway


def maybe_cleanup() -> None:
    """Occasionally purge stale buckets (no external cron required for Wave 1)."""
    global _cleanup_counter
    with _cleanup_lock:
        _cleanup_counter += 1
        if _cleanup_counter % 200 != 0 and random.random() > 0.02:
            return
        gw = _gateway
    if not gw:
        return
    try:
        removed = gw.store.cleanup()
        if removed:
            logger.info("rate_limit cleanup removed %d stale buckets", removed)
    except Exception:
        logger.exception("rate_limit cleanup failed")


def _actor_for(req: Request) -> Actor:
    """Prefer the actor resolved by auth. Fall back so direct checks still have a subject."""
    actor = getattr(g, "actor", None)
    if isinstance(actor, Actor) and actor.kind != "anonymous":
        return actor
    return Actor(kind="api_key", credential=req.headers.get("X-API-Key", "") or "")


def uses_custom_gateway() -> bool:
    """True when Wave 1 gateway owns limiting (sql or memory backend)."""
    backend = (Config.RATELIMIT_STORAGE_BACKEND or "memory").lower()
    return backend in ("sql", "memory")
