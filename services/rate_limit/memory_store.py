"""In-memory fixed-window store (tests / single-process fallback)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .store import IncrResult, RateLimitStore, TokenResult, token_retry_after


class MemoryRateLimitStore(RateLimitStore):
    def __init__(self, clock=None) -> None:
        self._lock = threading.Lock()
        self._clock = clock or time.time
        # (key, window_start_epoch) -> hit_count
        self._buckets: dict[tuple[str, int], int] = {}
        # key -> (tokens, updated_at epoch)
        self._tokens: dict[str, tuple[float, float]] = {}

    def incr_and_check(self, key: str, window_seconds: int, limit: int) -> IncrResult:
        now = self._clock()
        window_start = int(now // window_seconds) * window_seconds
        bucket = (key, window_start)
        with self._lock:
            hits = self._buckets.get(bucket, 0) + 1
            self._buckets[bucket] = hits
        reset_at = datetime.fromtimestamp(window_start + window_seconds, tz=timezone.utc)
        allowed = hits <= limit
        remaining = max(0, limit - hits)
        return IncrResult(
            allowed=allowed,
            hit_count=hits,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            window_seconds=window_seconds,
        )

    def take_token(self, key: str, capacity: int, refill_per_second: float) -> TokenResult:
        now = self._clock()
        with self._lock:
            stored = self._tokens.get(key)
            if stored is None:
                tokens_now = float(capacity)
            else:
                tokens, updated_at = stored
                elapsed = max(0.0, now - updated_at)
                tokens_now = min(float(capacity), tokens + refill_per_second * elapsed)
            if tokens_now < 1:
                return TokenResult(
                    allowed=False,
                    remaining=tokens_now,
                    retry_after=token_retry_after(tokens_now, refill_per_second),
                    capacity=capacity,
                )
            self._tokens[key] = (tokens_now - 1, now)
            return TokenResult(
                allowed=True,
                remaining=tokens_now - 1,
                retry_after=None,
                capacity=capacity,
            )

    def ping(self) -> bool:
        return True

    def cleanup(self, older_than_seconds: int = 172800) -> int:
        cutoff = self._clock() - older_than_seconds
        with self._lock:
            stale = [k for k in self._buckets if k[1] < cutoff]
            for k in stale:
                del self._buckets[k]
            old_tokens = [k for k, (_, updated) in self._tokens.items() if updated < cutoff]
            for k in old_tokens:
                del self._tokens[k]
            return len(stale) + len(old_tokens)
