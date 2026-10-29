"""Rate-limit storage interface and result types."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IncrResult:
    allowed: bool
    hit_count: int
    limit: int
    remaining: int
    reset_at: datetime
    window_seconds: int

    @property
    def retry_after(self) -> int | None:
        if self.allowed:
            return None
        now = datetime.now(timezone.utc)
        reset = self.reset_at if self.reset_at.tzinfo else self.reset_at.replace(tzinfo=timezone.utc)
        return max(1, int((reset - now).total_seconds()))


@dataclass(frozen=True)
class TokenResult:
    allowed: bool
    remaining: float
    retry_after: int | None
    capacity: int


def token_retry_after(tokens_now: float, refill_per_second: float) -> int:
    """Seconds until one token is available. Matches ceil((1 - tokens_now) / refill)."""
    if refill_per_second <= 0:
        return 60
    needed = (1.0 - tokens_now) / refill_per_second
    return max(1, math.ceil(needed - 1e-9))


class RateLimitStore(ABC):
    @abstractmethod
    def incr_and_check(self, key: str, window_seconds: int, limit: int) -> IncrResult:
        """Atomically increment the fixed window counter and say allow/deny."""

    @abstractmethod
    def take_token(self, key: str, capacity: int, refill_per_second: float) -> TokenResult:
        """Spend one token. A new key starts full. Reject when fewer than one token is available."""

    @abstractmethod
    def ping(self) -> bool:
        """True if the store is reachable."""

    @abstractmethod
    def cleanup(self, older_than_seconds: int = 172800) -> int:
        """Delete stale windows; return rows removed."""
