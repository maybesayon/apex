"""
Per-user resources: portfolio, watchlist, journal, settings.

Every route here derives its user_id from the auth dependency. There is no
route that accepts a user_id as a parameter, which is what makes
cross-account access structurally impossible rather than merely unlikely.
"""

from fastapi import APIRouter, HTTPException, status

import db
from api.deps import CurrentUser
from api.schemas import (
    JournalEntry,
    JournalStats,
    JournalWrite,
    PortfolioResponse,
    PositionValued,
    PositionWrite,
    Settings,
    SymbolRequest,
    WatchlistItem,
)
from api.serialization import to_jsonable

router = APIRouter(tags=["user"])


# ── Portfolio ─────────────────────────────────────────────────────────────────

@router.get("/portfolio", response_model=PortfolioResponse)
def get_portfolio(user: CurrentUser):
    """Holdings priced at the latest quote, with totals."""
    from prices import get_multiple_quotes

    positions = db.get_positions(user["user_id"])
    if not positions:
        return PortfolioResponse(positions=[], total_value=0.0, total_cost=0.0,
                                 total_pnl=0.0, total_pnl_pct=0.0)

    quotes = get_multiple_quotes(sorted(positions))
    rows, total_value, total_cost = [], 0.0, 0.0
    for sym, pos in positions.items():
        q = quotes.get(sym)
        price = float(q["price"]) if q else float(pos["avg_cost"])
        value = price * pos["shares"]
        cost = pos["avg_cost"] * pos["shares"]
        total_value += value
        total_cost += cost
        rows.append(PositionValued(
            symbol=sym, shares=pos["shares"], avg_cost=pos["avg_cost"],
            price=round(price, 2), value=round(value, 2), cost=round(cost, 2),
            pnl=round(value - cost, 2),
            pnl_pct=round((value - cost) / cost * 100, 2) if cost else 0.0,
        ))

    pnl = total_value - total_cost
    return PortfolioResponse(
        positions=rows,
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_pnl=round(pnl, 2),
        total_pnl_pct=round(pnl / total_cost * 100, 2) if total_cost else 0.0,
    )


@router.put("/portfolio/positions", status_code=status.HTTP_204_NO_CONTENT)
def upsert_position(body: PositionWrite, user: CurrentUser):
    db.upsert_position(user["user_id"], body.symbol, body.shares, body.avg_cost)


@router.delete("/portfolio/positions/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(symbol: str, user: CurrentUser):
    db.delete_position(user["user_id"], symbol)


# ── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist", response_model=list[WatchlistItem])
def get_watchlist(user: CurrentUser):
    from prices import get_multiple_quotes
    from symbols import get_symbol_index

    symbols = db.get_watchlist(user["user_id"])
    if not symbols:
        return []
    quotes = get_multiple_quotes(symbols)
    names = get_symbol_index()
    out = []
    for s in symbols:
        q = quotes.get(s)
        out.append(WatchlistItem(
            symbol=s,
            name=names.get(s),
            price=to_jsonable(q["price"]) if q else None,
            pct_change=to_jsonable(q["pct_change"]) if q else None,
        ))
    return out


@router.post("/watchlist", status_code=status.HTTP_204_NO_CONTENT)
def add_to_watchlist(body: SymbolRequest, user: CurrentUser):
    from symbols import resolve_symbol

    ticker = resolve_symbol(body.symbol)
    if not ticker:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"No symbol matches {body.symbol!r}")
    db.add_to_watchlist(user["user_id"], ticker)


@router.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(symbol: str, user: CurrentUser):
    db.remove_from_watchlist(user["user_id"], symbol)


# ── Journal ───────────────────────────────────────────────────────────────────

@router.get("/journal", response_model=list[JournalEntry])
def get_journal(user: CurrentUser):
    return [JournalEntry(**to_jsonable(e)) for e in db.get_journal(user["user_id"])]


@router.post("/journal", status_code=status.HTTP_201_CREATED, response_model=JournalEntry)
def add_journal_entry(body: JournalWrite, user: CurrentUser):
    pnl = (body.exit - body.entry) * body.shares
    pnl_pct = (body.exit - body.entry) / body.entry * 100
    entry = {
        "date": body.date, "symbol": body.symbol.upper(), "strategy": body.strategy,
        "entry": body.entry, "exit": body.exit, "shares": body.shares,
        "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 1), "note": body.note or "",
    }
    db.add_journal_entry(user["user_id"], entry)
    return JournalEntry(**entry, win=pnl > 0)


@router.get("/journal/stats", response_model=JournalStats)
def journal_stats(user: CurrentUser):
    """
    Win rate computed from the user's own logged trades. Returns null rather
    than a placeholder when nothing is logged — a hardcoded '68%' shown to
    every user is the bug this replaced.
    """
    return JournalStats(**db.journal_stats(user["user_id"]))


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=Settings)
def get_settings(user: CurrentUser):
    return Settings(theme=db.get_theme(user["user_id"]))


@router.put("/settings", response_model=Settings)
def put_settings(body: Settings, user: CurrentUser):
    db.set_theme(user["user_id"], body.theme)
    return body
