"""
Pydantic models — the frontend contract.

These generate the OpenAPI schema that the Next.js client's TypeScript types
are derived from, so a field renamed here surfaces as a compile error there
rather than as `undefined` at runtime.

Rich analysis payloads (analysis, backtest, forecast) are typed loosely on
purpose: their shape is defined by the analysis engine, and contract tests
assert byte-equality with direct function calls. Pinning every nested field
here would mean two sources of truth, and the one that silently drifts is
this one.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, examples=["sayon"])
    password: str = Field(min_length=8)
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    username: str


class UserResponse(BaseModel):
    user_id: int
    username: str


# ── Market data ───────────────────────────────────────────────────────────────

class Quote(BaseModel):
    symbol: str
    price: float
    change: float
    pct_change: float
    high: float | None = None
    low: float | None = None
    open: float | None = None
    prev_close: float | None = None
    source: str | None = None


class SearchResult(BaseModel):
    symbol: str
    name: str
    label: str = Field(description="Display form, e.g. 'AAPL · Apple Inc.'")


class Bar(BaseModel):
    time: str = Field(description="ISO date, as Lightweight Charts expects")
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class HistoryResponse(BaseModel):
    symbol: str
    period: str
    bars: list[Bar]


class Profile(BaseModel):
    name: str
    industry: str | None = None
    market_cap: float | None = None
    logo: str | None = None
    web: str | None = None


class Rating(BaseModel):
    symbol: str
    exchange: str
    recommendation: str
    buy: int
    sell: int
    neutral: int


# ── Portfolio / watchlist / journal ───────────────────────────────────────────

class Position(BaseModel):
    symbol: str
    shares: float
    avg_cost: float


class PositionWrite(BaseModel):
    symbol: str
    shares: float = Field(gt=0)
    avg_cost: float = Field(gt=0)


class PositionValued(Position):
    """A holding priced at the latest quote."""
    price: float
    value: float
    cost: float
    pnl: float
    pnl_pct: float


class PortfolioResponse(BaseModel):
    positions: list[PositionValued]
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float


class WatchlistItem(BaseModel):
    symbol: str
    name: str | None = None
    price: float | None = None
    pct_change: float | None = None


class SymbolRequest(BaseModel):
    symbol: str


class JournalEntry(BaseModel):
    date: str
    symbol: str
    strategy: str | None = None
    entry: float
    exit: float
    shares: float
    pnl: float
    pnl_pct: float
    note: str | None = None
    win: bool


class JournalWrite(BaseModel):
    date: str
    symbol: str
    strategy: str | None = None
    entry: float = Field(gt=0)
    exit: float = Field(gt=0)
    shares: float = Field(gt=0)
    note: str | None = ""


class JournalStats(BaseModel):
    trades: int
    wins: int
    losses: int
    win_rate: float | None = Field(
        description="None when no trades are logged. Never a placeholder value."
    )
    total_pnl: float


class Settings(BaseModel):
    theme: Literal["light", "dark"]


# ── Analysis ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str
    capital: float = Field(default=1000.0, gt=0)
    stop_loss_pct: float = Field(default=0.17, gt=0, lt=1)
    take_profit_pct: float = Field(default=0.25, gt=0)
    rsi_entry: float = Field(default=65, ge=0, le=100)
    rsi_exit: float = Field(default=70, ge=0, le=100)
    vol_ratio_min: float = Field(default=1.2, ge=0)
    vol_lookback: int = Field(default=3, ge=1, le=60)


class ScanRequest(BaseModel):
    scope: Literal["universe", "broad"] = "universe"
    min_score: int = Field(default=55, ge=0, le=100)


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
