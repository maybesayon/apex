"""
Backtesting, scanning and chat.

The scan is synchronous here and should not stay that way — measured at
~46s for the broad scope, it exceeds common proxy and serverless timeouts.
Phase 4 moves it behind the job queue; this router keeps the behaviour
reachable in the meantime so the API has parity with Streamlit today.
"""

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser
from api.schemas import BacktestRequest, ChatRequest, ScanRequest
from api.serialization import to_jsonable

router = APIRouter(tags=["analysis"])


@router.post("/backtest")
def run_backtest(body: BacktestRequest):
    """Backtest the momentum strategy over two years of daily bars."""
    from backtest import backtest_momentum_strategy
    from symbols import resolve_symbol

    ticker = resolve_symbol(body.symbol)
    if not ticker:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No symbol matches {body.symbol!r}")

    result = backtest_momentum_strategy(
        ticker, body.capital,
        stop_loss_pct=body.stop_loss_pct,
        take_profit_pct=body.take_profit_pct,
        rsi_entry=body.rsi_entry,
        rsi_exit=body.rsi_exit,
        vol_ratio_min=body.vol_ratio_min,
        vol_lookback=body.vol_lookback,
    )
    if "error" in result:
        # 422, not 500: a zero-trade run is a valid outcome of the chosen
        # filters, and the message explains which filter bound.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    return to_jsonable(result)


@router.post("/scan", deprecated=True, summary="Run a scan (synchronous — moves to /jobs in Phase 4)")
def scan(body: ScanRequest):
    """
    Synchronous scan.

    Measured: ~21s for the personal universe, ~46s broad. That exceeds
    Vercel's serverless cap and typical nginx/ALB 60s defaults, so clients
    should not rely on this endpoint. Marked deprecated from the day it
    ships; Phase 4 replaces it with POST /jobs/scan returning a job id.
    """
    from scanner import run_broad_scan, run_full_scan

    if body.scope == "broad":
        results = run_broad_scan(min_score=body.min_score)
    else:
        results = run_full_scan(min_score=body.min_score)
    return to_jsonable({"scope": body.scope, "count": len(results), "results": results})


@router.post("/chat")
def chat_endpoint(body: ChatRequest, user: CurrentUser):
    """
    Assistant reply. The user's own holdings are passed in as context —
    never imported from module state, so one account's positions cannot
    appear in another's conversation.
    """
    import db
    from chat import chat as chat_fn, get_emotion_warning

    if get_emotion_warning(body.message):
        return {
            "text": ("I'm noticing some pressure in your message. Emotional trading is "
                     "one of the top causes of losses.\n\nLet's look at this clearly "
                     "before making any moves."),
            "card": None,
            "suggestions": ["Show my journal", "Review positions", "Market overview"],
            "emotion_flagged": True,
        }

    from prices import get_multiple_quotes

    positions = db.get_positions(user["user_id"])
    watch = db.get_watchlist(user["user_id"])
    quotes = get_multiple_quotes(sorted(set(watch) | set(positions))) if (watch or positions) else {}

    reply = chat_fn(body.message, body.history, quotes, portfolio=positions)
    return to_jsonable({**reply, "emotion_flagged": False})
