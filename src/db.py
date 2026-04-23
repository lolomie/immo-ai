"""
Database abstraction layer.

- SQLite (default): zero setup, file-based, persistent. Used locally.
- PostgreSQL: set DATABASE_URL env var for production (Neon, Supabase, Railway).

All SQL goes through this module. Never import sqlite3 or psycopg2 elsewhere.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

# ── Driver selection ──────────────────────────────────────────────────────────

_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
_on_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

_SQLITE_PATH = (
    "/tmp/immo.db"
    if _on_vercel
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "immo.db")
)


def _use_postgres() -> bool:
    return bool(_DATABASE_URL)


# ── Connection context manager ────────────────────────────────────────────────
# Each call opens a fresh connection, commits on success, rolls back on error,
# and always closes — guaranteeing writes reach disk immediately.

@contextmanager
def get_conn():
    if _use_postgres():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        data_dir = os.path.dirname(_SQLITE_PATH)
        os.makedirs(data_dir, exist_ok=True)
        conn = sqlite3.connect(_SQLITE_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
            # Force WAL checkpoint so data is in the main DB file
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adapt(sql: str) -> str:
    if _use_postgres():
        return sql.replace("?", "%s")
    return sql


def execute(sql: str, params: Sequence = ()) -> None:
    sql = _adapt(sql)
    with get_conn() as conn:
        conn.execute(sql, params)


def fetchone(sql: str, params: Sequence = ()) -> Optional[dict]:
    sql = _adapt(sql)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetchall(sql: str, params: Sequence = ()) -> List[dict]:
    sql = _adapt(sql)
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ── Schema ────────────────────────────────────────────────────────────────────

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS users (
    username         TEXT PRIMARY KEY,
    password_hash    TEXT NOT NULL DEFAULT '',
    full_name        TEXT DEFAULT '',
    email            TEXT DEFAULT '',
    phone            TEXT DEFAULT '',
    company          TEXT DEFAULT '',
    plan             TEXT DEFAULT 'starter',
    gcal_calendar_id TEXT DEFAULT '',
    google_id        TEXT DEFAULT '',
    gdpr_consent     INTEGER DEFAULT 0,
    gdpr_consent_at  TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signup_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL,
    company      TEXT DEFAULT '',
    phone        TEXT DEFAULT '',
    plan_key     TEXT DEFAULT 'pro',
    message      TEXT DEFAULT '',
    status       TEXT DEFAULT 'pending',
    gdpr_consent INTEGER DEFAULT 0,
    ip_address   TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usage (
    username   TEXT NOT NULL,
    year_month TEXT NOT NULL,
    count      INTEGER DEFAULT 0,
    PRIMARY KEY (username, year_month)
);

CREATE TABLE IF NOT EXISTS calendar_events (
    appointment_id TEXT PRIMARY KEY,
    property_id    TEXT DEFAULT '',
    client_name    TEXT NOT NULL,
    client_contact TEXT DEFAULT '',
    date           TEXT NOT NULL,
    time           TEXT NOT NULL,
    type           TEXT NOT NULL,
    notes          TEXT DEFAULT '',
    username       TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    username                TEXT NOT NULL UNIQUE,
    stripe_customer_id      TEXT DEFAULT '',
    stripe_subscription_id  TEXT DEFAULT '',
    stripe_price_id         TEXT DEFAULT '',
    plan_key                TEXT DEFAULT 'starter',
    billing                 TEXT DEFAULT 'monthly',
    status                  TEXT DEFAULT 'pending',
    current_period_end      INTEGER,
    cancel_at_period_end    INTEGER DEFAULT 0,
    created_at              TEXT DEFAULT (datetime('now')),
    updated_at              TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_by TEXT DEFAULT '',
    data       TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_calendar_date  ON calendar_events(date);
CREATE INDEX IF NOT EXISTS idx_signup_email   ON signup_requests(email);
CREATE INDEX IF NOT EXISTS idx_usage_user     ON usage(username);
CREATE INDEX IF NOT EXISTS idx_sub_customer   ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_sub_stripe_sub ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs(status);
"""

_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS users (
    username         TEXT PRIMARY KEY,
    password_hash    TEXT NOT NULL DEFAULT '',
    full_name        TEXT DEFAULT '',
    email            TEXT DEFAULT '',
    phone            TEXT DEFAULT '',
    company          TEXT DEFAULT '',
    plan             TEXT DEFAULT 'starter',
    gcal_calendar_id TEXT DEFAULT '',
    google_id        TEXT DEFAULT '',
    gdpr_consent     SMALLINT DEFAULT 0,
    gdpr_consent_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signup_requests (
    id           SERIAL PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL,
    company      TEXT DEFAULT '',
    phone        TEXT DEFAULT '',
    plan_key     TEXT DEFAULT 'pro',
    message      TEXT DEFAULT '',
    status       TEXT DEFAULT 'pending',
    gdpr_consent SMALLINT DEFAULT 0,
    ip_address   TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage (
    username   TEXT NOT NULL,
    year_month TEXT NOT NULL,
    count      INTEGER DEFAULT 0,
    PRIMARY KEY (username, year_month)
);

CREATE TABLE IF NOT EXISTS calendar_events (
    appointment_id TEXT PRIMARY KEY,
    property_id    TEXT DEFAULT '',
    client_name    TEXT NOT NULL,
    client_contact TEXT DEFAULT '',
    date           TEXT NOT NULL,
    time           TEXT NOT NULL,
    type           TEXT NOT NULL,
    notes          TEXT DEFAULT '',
    username       TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      SERIAL PRIMARY KEY,
    username                TEXT NOT NULL UNIQUE,
    stripe_customer_id      TEXT DEFAULT '',
    stripe_subscription_id  TEXT DEFAULT '',
    stripe_price_id         TEXT DEFAULT '',
    plan_key                TEXT DEFAULT 'starter',
    billing                 TEXT DEFAULT 'monthly',
    status                  TEXT DEFAULT 'pending',
    current_period_end      BIGINT,
    cancel_at_period_end    SMALLINT DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    created_by TEXT DEFAULT '',
    data       TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_date  ON calendar_events(date);
CREATE INDEX IF NOT EXISTS idx_signup_email   ON signup_requests(email);
CREATE INDEX IF NOT EXISTS idx_usage_user     ON usage(username);
CREATE INDEX IF NOT EXISTS idx_sub_customer   ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_sub_stripe_sub ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs(status);
"""


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    if _use_postgres():
        import psycopg2
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            cur = conn.cursor()
            for stmt in _POSTGRES_DDL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
            conn.commit()
        finally:
            conn.close()
    else:
        data_dir = os.path.dirname(_SQLITE_PATH)
        os.makedirs(data_dir, exist_ok=True)
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.executescript(_SQLITE_DDL)
        conn.commit()
        conn.close()
    _run_migrations()
    logger.info("DB ready (%s @ %s)",
                "PostgreSQL" if _use_postgres() else "SQLite",
                "DATABASE_URL" if _use_postgres() else _SQLITE_PATH)


def _run_migrations() -> None:
    """Add columns/tables that were missing in older schema versions."""
    _safe = [
        "ALTER TABLE users ADD COLUMN google_id TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN gcal_calendar_id TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN company TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN gdpr_consent INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN gdpr_consent_at TEXT",
        "ALTER TABLE users ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
        # jobs table for DBs that pre-date this column
        """CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_by TEXT DEFAULT '',
            data TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')))""",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    ]
    for sql in _safe:
        try:
            execute(sql)
        except Exception:
            pass  # column/table already exists — intentionally ignored
