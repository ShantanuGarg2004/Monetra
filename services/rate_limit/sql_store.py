"""PostgreSQL fixed-window store via SQLAlchemy."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .store import IncrResult, RateLimitStore, TokenResult, token_retry_after

logger = logging.getLogger(__name__)

_UPSERT = text(
    """
    INSERT INTO rate_limit_buckets (bucket_key, window_start, window_seconds, hit_count, updated_at)
    VALUES (:key, to_timestamp(:window_start), :window_seconds, 1, NOW())
    ON CONFLICT (bucket_key, window_start)
    DO UPDATE SET
        hit_count  = rate_limit_buckets.hit_count + 1,
        updated_at = NOW()
    RETURNING hit_count
    """
)

_CLEANUP = text(
    """
    DELETE FROM rate_limit_buckets
    WHERE updated_at < NOW() - make_interval(secs => :older_than)
    """
)

_PING = text("SELECT 1")

_CREATE_TOKEN_BUCKETS = text(
    """
    CREATE TABLE IF NOT EXISTS rate_limit_token_buckets (
        bucket_key TEXT PRIMARY KEY,
        tokens     DOUBLE PRECISION NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
)

_SEED_TOKEN = text(
    """
    INSERT INTO rate_limit_token_buckets (bucket_key, tokens, updated_at)
    VALUES (:key, :capacity, NOW())
    ON CONFLICT (bucket_key) DO NOTHING
    """
)

_LOCK_TOKEN = text(
    """
    SELECT tokens,
           EXTRACT(EPOCH FROM (NOW() - updated_at)) AS elapsed
    FROM rate_limit_token_buckets
    WHERE bucket_key = :key
    FOR UPDATE
    """
)

_SPEND_TOKEN = text(
    """
    UPDATE rate_limit_token_buckets
    SET tokens = :tokens, updated_at = NOW()
    WHERE bucket_key = :key
    """
)

_CLEANUP_TOKENS = text(
    """
    DELETE FROM rate_limit_token_buckets
    WHERE updated_at < NOW() - make_interval(secs => :older_than)
    """
)


class SqlRateLimitStore(RateLimitStore):
    def __init__(self, database_url: str, pool_size: int = 5, max_overflow: int = 10) -> None:
        if not database_url:
            raise ValueError("RATELIMIT_DATABASE_URL is required for sql backend")
        self._engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            future=True,
        )
        self._token_ready = False

    def incr_and_check(self, key: str, window_seconds: int, limit: int) -> IncrResult:
        now = datetime.now(timezone.utc)
        window_start_epoch = int(now.timestamp() // window_seconds) * window_seconds
        with self._engine.begin() as conn:
            hit_count = conn.execute(
                _UPSERT,
                {
                    "key": key,
                    "window_start": window_start_epoch,
                    "window_seconds": window_seconds,
                },
            ).scalar_one()
        reset_at = datetime.fromtimestamp(window_start_epoch + window_seconds, tz=timezone.utc)
        allowed = hit_count <= limit
        remaining = max(0, limit - hit_count)
        return IncrResult(
            allowed=allowed,
            hit_count=hit_count,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            window_seconds=window_seconds,
        )

    def _ensure_token_table(self) -> None:
        if self._token_ready:
            return
        with self._engine.begin() as conn:
            conn.execute(_CREATE_TOKEN_BUCKETS)
        self._token_ready = True

    def take_token(self, key: str, capacity: int, refill_per_second: float) -> TokenResult:
        self._ensure_token_table()
        with self._engine.begin() as conn:
            conn.execute(_SEED_TOKEN, {"key": key, "capacity": float(capacity)})
            row = conn.execute(_LOCK_TOKEN, {"key": key}).one()
            elapsed = max(0.0, float(row.elapsed or 0))
            tokens_now = min(float(capacity), float(row.tokens) + refill_per_second * elapsed)
            if tokens_now < 1:
                return TokenResult(
                    allowed=False,
                    remaining=tokens_now,
                    retry_after=token_retry_after(tokens_now, refill_per_second),
                    capacity=capacity,
                )
            remaining = tokens_now - 1
            conn.execute(_SPEND_TOKEN, {"key": key, "tokens": remaining})
        return TokenResult(
            allowed=True,
            remaining=remaining,
            retry_after=None,
            capacity=capacity,
        )

    def ping(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(_PING)
            return True
        except Exception:
            logger.exception("SqlRateLimitStore.ping failed")
            return False

    def cleanup(self, older_than_seconds: int = 172800) -> int:
        self._ensure_token_table()
        with self._engine.begin() as conn:
            result = conn.execute(_CLEANUP, {"older_than": older_than_seconds})
            tokens = conn.execute(_CLEANUP_TOKENS, {"older_than": older_than_seconds})
            return (result.rowcount or 0) + (tokens.rowcount or 0)
