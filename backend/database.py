"""
database.py — SQLite persistence for the ShadowX Factory run index.

We use SQLite (not an ORM) so the dependency footprint stays minimal.
Runs are indexed here; the full run state lives in runs/<id>/state.json
so the two sources never conflict — SQLite is the summary/query layer.
"""

from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from typing import Optional

# Database file lives next to the runs/ directory in backend/.
DB_PATH = Path(__file__).parent / "shadowx_factory.db"


def _connect() -> sqlite3.Connection:
    """Return a connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the runs table if it doesn't exist yet, and ensure schema migrations."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id           TEXT PRIMARY KEY,
                idea             TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending',
                current_stage    TEXT NOT NULL DEFAULT 'IDLE',
                created_at       REAL NOT NULL,
                updated_at       REAL NOT NULL,
                duration_seconds REAL DEFAULT 0.0,
                total_tokens     INTEGER DEFAULT 0,
                cost_usd         REAL DEFAULT 0.0,
                debug_iterations INTEGER DEFAULT 0,
                tests_passed     INTEGER DEFAULT 0,
                total_tests      INTEGER DEFAULT 0,
                error            TEXT
            )
        """)
        # Schema migration: ensure cost_usd column exists if table pre-dates it
        cursor = conn.execute("PRAGMA table_info(runs)")
        cols = {row["name"] for row in cursor.fetchall()}
        if "cost_usd" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN cost_usd REAL DEFAULT 0.0")
        conn.commit()


def upsert_run(
    run_id: str,
    idea: str,
    status: str,
    current_stage: str,
    created_at: float,
    updated_at: float,
    duration_seconds: float = 0.0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    debug_iterations: int = 0,
    tests_passed: int = 0,
    total_tests: int = 0,
    error: Optional[str] = None,
) -> None:
    """Insert a new run or update all mutable fields of an existing one."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO runs (
                run_id, idea, status, current_stage,
                created_at, updated_at, duration_seconds,
                total_tokens, cost_usd, debug_iterations,
                tests_passed, total_tests, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status           = excluded.status,
                current_stage    = excluded.current_stage,
                updated_at       = excluded.updated_at,
                duration_seconds = excluded.duration_seconds,
                total_tokens     = excluded.total_tokens,
                cost_usd         = excluded.cost_usd,
                debug_iterations = excluded.debug_iterations,
                tests_passed     = excluded.tests_passed,
                total_tests      = excluded.total_tests,
                error            = excluded.error
        """, (
            run_id, idea, status, current_stage,
            created_at, updated_at, duration_seconds,
            total_tokens, cost_usd, debug_iterations,
            tests_passed, total_tests, error,
        ))
        conn.commit()


def get_run(run_id: str) -> Optional[dict]:
    """Return the SQLite row for a run as a dict, or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


def list_runs() -> list[dict]:
    """Return all runs ordered by creation time descending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
