# ─────────────────────────────────────────────
#  db.py — Per-user persistence (SQLite)
#
#  Replaces the hardcoded PORTFOLIO/WATCHLIST in config.py so every
#  user owns their own holdings, watchlist and trade journal.
#
#  A new connection per call keeps this safe across Streamlit's
#  worker threads; SQLite handles this fine at the concurrency a
#  single-instance app sees.
# ─────────────────────────────────────────────

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "APEX_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "apex.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT    UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    salt          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol   TEXT    NOT NULL,
    shares   REAL    NOT NULL,
    avg_cost REAL    NOT NULL,
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol  TEXT    NOT NULL,
    sort    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS journal (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trade_date TEXT   NOT NULL,
    symbol    TEXT    NOT NULL,
    strategy  TEXT,
    entry     REAL    NOT NULL,
    exit      REAL    NOT NULL,
    shares    REAL    NOT NULL,
    pnl       REAL    NOT NULL,
    pnl_pct   REAL    NOT NULL,
    note      TEXT,
    created_at TEXT   NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme   TEXT NOT NULL DEFAULT 'light'
);
"""

DEFAULT_WATCHLIST = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL"]


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str | None, password_hash: str, salt: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, salt, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, email or None, password_hash, salt, _now()),
        )
        user_id = int(cur.lastrowid)
        conn.execute("INSERT INTO settings (user_id, theme) VALUES (?, 'light')", (user_id,))
        conn.executemany(
            "INSERT INTO watchlist (user_id, symbol, sort) VALUES (?, ?, ?)",
            [(user_id, s, i) for i, s in enumerate(DEFAULT_WATCHLIST)],
        )
        return user_id


def get_user(username: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def user_count() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


# ── Positions ─────────────────────────────────────────────────────────────────

def get_positions(user_id: int) -> dict[str, dict]:
    """{symbol: {shares, avg_cost}} — same shape the app already expects."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT symbol, shares, avg_cost FROM positions WHERE user_id = ? ORDER BY symbol",
            (user_id,),
        ).fetchall()
    return {r["symbol"]: {"shares": r["shares"], "avg_cost": r["avg_cost"]} for r in rows}


def upsert_position(user_id: int, symbol: str, shares: float, avg_cost: float) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO positions (user_id, symbol, shares, avg_cost) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(user_id, symbol) DO UPDATE SET shares = ?, avg_cost = ?",
            (user_id, symbol.upper(), shares, avg_cost, shares, avg_cost),
        )


def delete_position(user_id: int, symbol: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND symbol = ?", (user_id, symbol.upper())
        )


# ── Watchlist ─────────────────────────────────────────────────────────────────

def get_watchlist(user_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT symbol FROM watchlist WHERE user_id = ? ORDER BY sort, symbol", (user_id,)
        ).fetchall()
    return [r["symbol"] for r in rows]


def add_to_watchlist(user_id: int, symbol: str) -> None:
    with connect() as conn:
        n = conn.execute(
            "SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM watchlist WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, symbol, sort) VALUES (?, ?, ?)",
            (user_id, symbol.upper(), n),
        )


def remove_from_watchlist(user_id: int, symbol: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?", (user_id, symbol.upper())
        )


# ── Journal ───────────────────────────────────────────────────────────────────

def add_journal_entry(user_id: int, entry: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO journal (user_id, trade_date, symbol, strategy, entry, exit,"
            " shares, pnl, pnl_pct, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, entry["date"], entry["symbol"].upper(), entry.get("strategy"),
                entry["entry"], entry["exit"], entry["shares"],
                entry["pnl"], entry["pnl_pct"], entry.get("note", ""), _now(),
            ),
        )


def get_journal(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT trade_date AS date, symbol, strategy, entry, exit, shares,"
            " pnl, pnl_pct, note FROM journal WHERE user_id = ? ORDER BY trade_date DESC, id DESC",
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["win"] = d["pnl"] > 0
        out.append(d)
    return out


def journal_stats(user_id: int) -> dict:
    """
    Real win rate from the user's own logged trades. This replaces the
    hardcoded "68% · 17 of 25 trades" tile, which was not derived from
    anything and was shown identically to every user.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n,"
            " SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,"
            " COALESCE(SUM(pnl), 0) AS total_pnl"
            " FROM journal WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    n = int(row["n"] or 0)
    wins = int(row["wins"] or 0)
    return {
        "trades":    n,
        "wins":      wins,
        "losses":    n - wins,
        "win_rate":  round(wins / n * 100, 1) if n else None,
        "total_pnl": float(row["total_pnl"] or 0.0),
    }


# ── Settings ──────────────────────────────────────────────────────────────────

def get_theme(user_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT theme FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    return (row["theme"] if row else "light") or "light"


def set_theme(user_id: int, theme: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (user_id, theme) VALUES (?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET theme = ?",
            (user_id, theme, theme),
        )
