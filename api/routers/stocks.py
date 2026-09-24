"""
Market data and analysis.

These routes are thin. Each one calls the existing analysis function and
serialises the result — no recomputation, no reshaping of the numbers.
That is what lets the contract tests assert byte-equality between the HTTP
response and a direct call, which is the whole safety net for the migration.
"""

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import Ticker
from api.schemas import (
    Bar,
    HistoryResponse,
    Profile,
    Quote,
    Rating,
    SearchResult,
)
from api.serialization import ohlcv_records, to_jsonable

router = APIRouter(tags=["stocks"])

VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}


@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query("", description="Ticker or company name"),
           limit: int = Query(25, ge=1, le=100)):
    """Search by ticker or company name — 'apple' and 'AAPL' both find AAPL."""
    from symbols import search_symbols

    return [SearchResult(symbol=t, name=n, label=f"{t} · {n}" if n != t else t)
            for t, n in search_symbols(q, limit)]


@router.get("/quotes", response_model=list[Quote])
def quotes(symbols: str = Query(..., description="Comma-separated tickers")):
    from prices import get_multiple_quotes

    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No symbols given")
    if len(wanted) > 50:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At most 50 symbols per request")
    found = get_multiple_quotes(wanted)
    return [Quote(**to_jsonable(q)) for q in found.values() if q]


@router.get("/stocks/{symbol}/quote", response_model=Quote)
def quote(symbol: Ticker):
    from prices import get_live_quote

    q = get_live_quote(symbol)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No quote available for {symbol}")
    return Quote(**to_jsonable(q))


@router.get("/stocks/{symbol}/history", response_model=HistoryResponse)
def history(symbol: Ticker, period: str = Query("1y")):
    from prices import get_historical_data

    if period not in VALID_PERIODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"period must be one of {sorted(VALID_PERIODS)}")
    df = get_historical_data(symbol, period=period)
    if df is None or df.empty:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No history for {symbol}")
    return HistoryResponse(symbol=symbol, period=period,
                           bars=[Bar(**b) for b in ohlcv_records(df)])


@router.get("/stocks/{symbol}/profile", response_model=Profile)
def profile(symbol: Ticker):
    from prices import get_company_profile

    return Profile(**to_jsonable(get_company_profile(symbol)))


@router.get("/stocks/{symbol}/analysis")
def analysis(symbol: Ticker, period: str = Query("1y")):
    """
    Technical analysis: latest indicator values, the signal summary, and
    suggested exit levels. Mirrors the Analysis tab.
    """
    from indicators import calculate_all, calculate_stop_and_target, get_signal_summary
    from prices import get_historical_data

    if period not in VALID_PERIODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"period must be one of {sorted(VALID_PERIODS)}")
    df = get_historical_data(symbol, period=period)
    if df is None or df.empty:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No history for {symbol}")

    enriched = calculate_all(df)
    summary = get_signal_summary(enriched)
    if not summary:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Not enough history to analyse {symbol}")

    latest = enriched.iloc[-1]
    price = float(latest["close"])
    atr = latest.get("atr")
    indicator_cols = ["rsi", "macd", "macd_signal", "macd_hist", "ma20", "ma50",
                      "ma200", "ema9", "ema21", "bb_upper", "bb_lower", "bb_mid",
                      "atr", "vol_ratio", "stoch_k", "stoch_d"]

    return to_jsonable({
        "symbol": symbol,
        "period": period,
        "as_of": enriched.index[-1],
        "price": price,
        "indicators": {c: latest.get(c) for c in indicator_cols if c in enriched.columns},
        "signals": summary["signals"],
        "overall_score": summary["overall_score"],
        "levels": calculate_stop_and_target(price, atr),
    })


@router.get("/stocks/{symbol}/opportunity")
def opportunity(symbol: Ticker):
    """Opportunity score with entry/target/stop — one dashboard card."""
    from scanner import score_opportunity

    result = score_opportunity(symbol)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Could not score {symbol} — no usable price or history")
    return to_jsonable(result)


@router.get("/stocks/{symbol}/forecast")
def forecast(symbol: Ticker):
    """
    ML price-direction forecast.

    `has_skill` is computed here rather than left to the client: a model
    that loses to its majority-class baseline has no demonstrated skill, and
    presenting the direction without that flag invites misreading.
    """
    from ml_predictions import predict_direction

    result = predict_direction(symbol)
    if "error" in result:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])

    acc, base = result.get("model_accuracy"), result.get("baseline_accuracy")
    payload = dict(result)
    payload["has_skill"] = bool(base is not None and acc is not None and acc > base)
    payload["edge_vs_baseline"] = round(acc - base, 1) if (acc is not None and base is not None) else None
    return to_jsonable(payload)


@router.get("/stocks/{symbol}/rating", response_model=Rating | None)
def rating(symbol: Ticker):
    """
    TradingView technical rating. Returns null rather than erroring when the
    unofficial upstream is unavailable — it is display-only.
    """
    from tradingview import get_tv_rating

    r = get_tv_rating(symbol)
    return Rating(**to_jsonable(r)) if r else None
