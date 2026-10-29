-- FinPilot rate-limit schema (Wave 1)
-- Applied automatically on first Postgres container init via docker-compose,
-- or manually: psql "$RATELIMIT_DATABASE_URL" -f database/sql/rate_limit_schema.sql

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    bucket_key     TEXT        NOT NULL,
    window_start   TIMESTAMPTZ NOT NULL,
    window_seconds INTEGER     NOT NULL,
    hit_count      INTEGER     NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (bucket_key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rl_buckets_updated
    ON rate_limit_buckets (updated_at);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    id             BIGSERIAL PRIMARY KEY,
    bucket_key     TEXT        NOT NULL,
    route_class    TEXT        NOT NULL,
    allowed        BOOLEAN     NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rl_events_created
    ON rate_limit_events (created_at);

-- Auth token buckets. Fixed-window rows above stay as they are.
-- A missing key starts full (capacity). The store writes tokens - 1 on a spend.
CREATE TABLE IF NOT EXISTS rate_limit_token_buckets (
    bucket_key TEXT PRIMARY KEY,
    tokens     DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
