# ─────────────────────────────────────────────
#  db.py — Per-user persistence
#
#  SQLAlchemy over SQLite or Postgres. Which one is chosen by DATABASE_URL
#  alone, so moving to Postgres is a config change, not a code change:
#
#      DATABASE_URL=postgresql+psycopg://user:pass@host/apex
#
#  This matters because SQLite on a platform with an ephemeral filesystem
#  (Vercel, Railway's default, Heroku) loses every account on restart.
#
#  The public function API is unchanged from the raw-sqlite3 version, so
#  app.py and api/ did not need touching. The isolation tests prove it.
# ─────────────────────────────────────────────

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, func, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _database_url() -> str:
    """
    DATABASE_URL wins. APEX_DB_PATH is still honoured so existing local
    setups and the test suite keep working unchanged.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Accept the `postgres://` form some platforms inject.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        return url
    path = os.environ.get(
        "APEX_DB_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "apex.db"),
    )
    return f"sqlite:///{path}"


DATABASE_URL = _database_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

# check_same_thread is a SQLite-only concern (Streamlit and FastAPI both
# touch the database from worker threads). pool_pre_ping keeps Postgres
# connections alive across a managed provider's idle timeouts.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

DEFAULT_WATCHLIST = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL"]


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    shares: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    sort: Mapped[int] = mapped_column(Integer, default=0)


class JournalRow(Base):
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trade_date: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(16))
    strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry: Mapped[float] = mapped_column(Float)
    exit: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    pnl_pct: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserSettings(Base):
    __tablename__ = "settings"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(16), default="light")


class RefreshToken(Base):
    """
    One row per issued refresh token.

    Only a hash is stored: a database leak must not hand out live sessions.
    `family_id` ties a rotation chain together so that replaying an already
    used token can revoke every descendant at once — the standard way to
    detect a stolen token.
    """
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Job(Base):
    """
    A long-running task and its progress.

    Job state lives in the database rather than in the worker's memory so
    that progress is readable from any process, survives a restart, and
    leaves a history. That holds whether the work runs in a background
    thread or, later, in a separate RQ worker.
    """
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    params: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Refreshed on every progress tick. Staleness — not merely being in the
    # 'running' state — is what identifies an abandoned job, so a second
    # worker starting up cannot kill another worker's live job.
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    Base.metadata.create_all(engine)


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str | None, password_hash: str, salt: str) -> int:
    with session() as s:
        user = User(username=username, email=email or None,
                    password_hash=password_hash, salt=salt)
        s.add(user)
        s.flush()
        s.add(UserSettings(user_id=user.id, theme="light"))
        s.add_all([WatchlistItem(user_id=user.id, symbol=sym, sort=i)
                   for i, sym in enumerate(DEFAULT_WATCHLIST)])
        return int(user.id)


def get_user(username: str) -> dict | None:
    """Case-insensitive lookup, matching the original COLLATE NOCASE column."""
    with session() as s:
        user = s.scalar(
            select(User).where(func.lower(User.username) == (username or "").lower())
        )
        if not user:
            return None
        return {"id": user.id, "username": user.username, "email": user.email,
                "password_hash": user.password_hash, "salt": user.salt,
                "created_at": user.created_at}


def get_user_by_id(user_id: int) -> dict | None:
    with session() as s:
        user = s.get(User, user_id)
        if not user:
            return None
        return {"id": user.id, "username": user.username, "email": user.email}


def user_count() -> int:
    with session() as s:
        return int(s.scalar(select(func.count()).select_from(User)) or 0)


# ── Positions ─────────────────────────────────────────────────────────────────

def get_positions(user_id: int) -> dict[str, dict]:
    with session() as s:
        rows = s.scalars(
            select(Position).where(Position.user_id == user_id).order_by(Position.symbol)
        ).all()
    return {r.symbol: {"shares": r.shares, "avg_cost": r.avg_cost} for r in rows}


def upsert_position(user_id: int, symbol: str, shares: float, avg_cost: float) -> None:
    symbol = symbol.upper()
    with session() as s:
        row = s.scalar(select(Position).where(
            Position.user_id == user_id, Position.symbol == symbol))
        if row:
            row.shares, row.avg_cost = shares, avg_cost
        else:
            s.add(Position(user_id=user_id, symbol=symbol,
                           shares=shares, avg_cost=avg_cost))


def delete_position(user_id: int, symbol: str) -> None:
    with session() as s:
        row = s.scalar(select(Position).where(
            Position.user_id == user_id, Position.symbol == symbol.upper()))
        if row:
            s.delete(row)


# ── Watchlist ─────────────────────────────────────────────────────────────────

def get_watchlist(user_id: int) -> list[str]:
    with session() as s:
        rows = s.scalars(
            select(WatchlistItem).where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.sort, WatchlistItem.symbol)
        ).all()
    return [r.symbol for r in rows]


def add_to_watchlist(user_id: int, symbol: str) -> None:
    symbol = symbol.upper()
    with session() as s:
        exists = s.scalar(select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol))
        if exists:
            return
        nxt = s.scalar(select(func.coalesce(func.max(WatchlistItem.sort), -1) + 1)
                       .where(WatchlistItem.user_id == user_id)) or 0
        s.add(WatchlistItem(user_id=user_id, symbol=symbol, sort=int(nxt)))


def remove_from_watchlist(user_id: int, symbol: str) -> None:
    with session() as s:
        row = s.scalar(select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol.upper()))
        if row:
            s.delete(row)


# ── Journal ───────────────────────────────────────────────────────────────────

def add_journal_entry(user_id: int, entry: dict) -> None:
    with session() as s:
        s.add(JournalRow(
            user_id=user_id, trade_date=entry["date"], symbol=entry["symbol"].upper(),
            strategy=entry.get("strategy"), entry=entry["entry"], exit=entry["exit"],
            shares=entry["shares"], pnl=entry["pnl"], pnl_pct=entry["pnl_pct"],
            note=entry.get("note", ""),
        ))


def get_journal(user_id: int) -> list[dict]:
    with session() as s:
        rows = s.scalars(
            select(JournalRow).where(JournalRow.user_id == user_id)
            .order_by(JournalRow.trade_date.desc(), JournalRow.id.desc())
        ).all()
    return [{"date": r.trade_date, "symbol": r.symbol, "strategy": r.strategy,
             "entry": r.entry, "exit": r.exit, "shares": r.shares, "pnl": r.pnl,
             "pnl_pct": r.pnl_pct, "note": r.note, "win": r.pnl > 0} for r in rows]


def journal_stats(user_id: int) -> dict:
    """
    Win rate from the user's own logged trades. Returns None for win_rate
    when nothing is logged — never a placeholder. A hardcoded "68%" shown
    identically to every user is the bug this replaced.
    """
    with session() as s:
        rows = s.scalars(select(JournalRow).where(JournalRow.user_id == user_id)).all()
    n = len(rows)
    wins = sum(1 for r in rows if r.pnl > 0)
    return {
        "trades": n, "wins": wins, "losses": n - wins,
        "win_rate": round(wins / n * 100, 1) if n else None,
        "total_pnl": float(sum(r.pnl for r in rows)),
    }


# ── Settings ──────────────────────────────────────────────────────────────────

def get_theme(user_id: int) -> str:
    with session() as s:
        row = s.get(UserSettings, user_id)
        return (row.theme if row else "light") or "light"


def set_theme(user_id: int, theme: str) -> None:
    with session() as s:
        row = s.get(UserSettings, user_id)
        if row:
            row.theme = theme
        else:
            s.add(UserSettings(user_id=user_id, theme=theme))


# ── Refresh tokens ────────────────────────────────────────────────────────────

def store_refresh_token(user_id: int, token_hash: str, family_id: str,
                        ttl_seconds: int) -> None:
    with session() as s:
        s.add(RefreshToken(
            user_id=user_id, token_hash=token_hash, family_id=family_id,
            expires_at=_utcnow() + timedelta(seconds=ttl_seconds),
        ))


def get_refresh_token(token_hash: str) -> dict | None:
    with session() as s:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if not row:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:          # SQLite round-trips naive datetimes
            expires = expires.replace(tzinfo=timezone.utc)
        return {"id": row.id, "user_id": row.user_id, "family_id": row.family_id,
                "expires_at": expires, "used": row.used, "revoked": row.revoked}


def mark_refresh_token_used(token_hash: str) -> None:
    with session() as s:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if row:
            row.used = True


def revoke_token_family(family_id: str) -> int:
    """Revoke a whole rotation chain — used when a token is replayed."""
    with session() as s:
        rows = s.scalars(select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False))).all()
        for r in rows:
            r.revoked = True
        return len(rows)


def revoke_all_user_tokens(user_id: int) -> int:
    with session() as s:
        rows = s.scalars(select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))).all()
        for r in rows:
            r.revoked = True
        return len(rows)


def purge_expired_refresh_tokens() -> int:
    with session() as s:
        rows = s.scalars(select(RefreshToken).where(
            RefreshToken.expires_at < _utcnow())).all()
        for r in rows:
            s.delete(r)
        return len(rows)


# ── Jobs ──────────────────────────────────────────────────────────────────────

import json as _json


def _job_to_dict(row: "Job") -> dict:
    def _iso(dt):
        if dt is None:
            return None
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()

    return {
        "id": row.id,
        "kind": row.kind,
        "status": row.status,
        "params": _json.loads(row.params) if row.params else {},
        "progress": {
            "done": row.progress_done,
            "total": row.progress_total,
            "label": row.progress_label,
            "pct": round(row.progress_done / row.progress_total * 100, 1)
                   if row.progress_total else None,
        },
        "result": _json.loads(row.result) if row.result else None,
        "error": row.error,
        "created_at": _iso(row.created_at),
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
    }


def create_job(job_id: str, user_id: int, kind: str, params: dict) -> dict:
    with session() as s:
        row = Job(id=job_id, user_id=user_id, kind=kind,
                  params=_json.dumps(params), status="queued")
        s.add(row)
        s.flush()
        return _job_to_dict(row)


def get_job(job_id: str, user_id: int | None = None) -> dict | None:
    """user_id scopes the lookup, so one account cannot read another's job."""
    with session() as s:
        row = s.get(Job, job_id)
        if row is None or (user_id is not None and row.user_id != user_id):
            return None
        return _job_to_dict(row)


def list_jobs(user_id: int, limit: int = 20) -> list[dict]:
    with session() as s:
        rows = s.scalars(
            select(Job).where(Job.user_id == user_id)
            .order_by(Job.created_at.desc()).limit(limit)
        ).all()
        return [_job_to_dict(r) for r in rows]


def start_job(job_id: str) -> None:
    with session() as s:
        row = s.get(Job, job_id)
        if row:
            row.status = "running"
            row.started_at = row.heartbeat_at = _utcnow()


def update_job_progress(job_id: str, done: int, total: int, label: str | None = None) -> None:
    with session() as s:
        row = s.get(Job, job_id)
        if row:
            row.progress_done, row.progress_total = done, total
            row.heartbeat_at = _utcnow()
            if label:
                row.progress_label = label[:128]


def finish_job(job_id: str, result) -> None:
    with session() as s:
        row = s.get(Job, job_id)
        if row:
            row.status, row.result = "finished", _json.dumps(result)
            row.finished_at = _utcnow()


def fail_job(job_id: str, error: str) -> None:
    with session() as s:
        row = s.get(Job, job_id)
        if row:
            row.status, row.error = "failed", str(error)[:2000]
            row.finished_at = _utcnow()


def request_cancel(job_id: str, user_id: int) -> bool:
    with session() as s:
        row = s.get(Job, job_id)
        if row is None or row.user_id != user_id:
            return False
        if row.status in ("finished", "failed", "cancelled"):
            return False
        row.cancel_requested = True
        if row.status == "queued":
            row.status, row.finished_at = "cancelled", _utcnow()
        return True


def is_cancel_requested(job_id: str) -> bool:
    with session() as s:
        row = s.get(Job, job_id)
        return bool(row and row.cancel_requested)


def mark_job_cancelled(job_id: str) -> None:
    with session() as s:
        row = s.get(Job, job_id)
        if row:
            row.status, row.finished_at = "cancelled", _utcnow()


JOB_STALE_SECONDS = int(os.environ.get("APEX_JOB_STALE_SECONDS", "900"))


def reap_orphaned_jobs(stale_seconds: int | None = None) -> int:
    """
    Fail jobs abandoned by a process that died.

    Only *stale* jobs are reaped — those with no heartbeat for
    JOB_STALE_SECONDS. Reaping every running job instead would mean a
    second worker booting could kill jobs still running healthily in the
    first, which is exactly wrong in a multi-process deployment.
    """
    cutoff_seconds = JOB_STALE_SECONDS if stale_seconds is None else stale_seconds
    cutoff = _utcnow() - timedelta(seconds=cutoff_seconds)

    def _aware(dt):
        return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)

    with session() as s:
        rows = s.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
        reaped = 0
        for r in rows:
            last_seen = _aware(r.heartbeat_at) or _aware(r.started_at) or _aware(r.created_at)
            if last_seen is not None and last_seen > cutoff:
                continue        # still alive
            r.status = "failed"
            r.error = "Worker stopped before the job finished (server restart?)"
            r.finished_at = _utcnow()
            reaped += 1
        return reaped
