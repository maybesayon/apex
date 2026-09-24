# ─────────────────────────────────────────────
#  tradingview.py — TradingView Integration
#  Embeddable widgets, analyst-style ratings,
#  and webhook alert storage.
# ─────────────────────────────────────────────

import json
import os
import time
from datetime import datetime

from config import TV_ALERTS_FILE

# Exchanges tried in order when resolving a US symbol for ratings
_TV_EXCHANGES = ["NASDAQ", "NYSE", "AMEX"]

# In-memory rating cache: {symbol: (timestamp, rating_dict)}
_rating_cache: dict = {}
RATING_CACHE_SECS = 300


# ── Embeddable Widgets ────────────────────────────────────────────────────────
# These return HTML snippets for streamlit.components.v1.html().
# Free TradingView embeds — no API key or account required.

def tv_advanced_chart_html(symbol: str, height: int = 520) -> str:
    """Full interactive TradingView chart (candles, indicators, drawing tools)."""
    config = {
        "autosize": True,
        "symbol": symbol,
        "interval": "D",
        "timezone": "America/New_York",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#101620",
        "backgroundColor": "#060810",
        "gridColor": "#1a2a3a",
        "enable_publishing": False,
        "hide_side_toolbar": False,
        "allow_symbol_change": True,
        "studies": ["RSI@tv-basicstudies", "MASimple@tv-basicstudies"],
        "container_id": "tv_advanced_chart",
    }
    return f"""
    <div class="tradingview-widget-container" style="height:{height}px">
      <div id="tv_advanced_chart" style="height:{height}px"></div>
      <script src="https://s3.tradingview.com/tv.js"></script>
      <script>new TradingView.widget({json.dumps(config)});</script>
    </div>
    """


def tv_technical_analysis_html(symbol: str, height: int = 380) -> str:
    """TradingView's Buy/Sell/Neutral gauge widget."""
    config = {
        "interval": "1D",
        "width": "100%",
        "height": height,
        "isTransparent": True,
        "symbol": symbol,
        "showIntervalTabs": True,
        "displayMode": "single",
        "locale": "en",
        "colorTheme": "dark",
    }
    return f"""
    <div class="tradingview-widget-container">
      <script src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js" async>
      {json.dumps(config)}
      </script>
    </div>
    """


def tv_ticker_tape_html(symbols: list) -> str:
    """Scrolling ticker tape for a list of symbols."""
    config = {
        "symbols": [{"proName": s, "title": s} for s in symbols],
        "showSymbolLogo": True,
        "isTransparent": True,
        "displayMode": "adaptive",
        "colorTheme": "dark",
        "locale": "en",
    }
    return f"""
    <div class="tradingview-widget-container">
      <script src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {json.dumps(config)}
      </script>
    </div>
    """


# ── Ratings (unofficial tradingview-ta library) ───────────────────────────────

def get_tv_rating(symbol: str) -> dict | None:
    """
    Fetch TradingView's technical rating (STRONG_BUY..STRONG_SELL) for a symbol.
    Uses the unofficial tradingview-ta library; returns None if unavailable.
    Results cached for RATING_CACHE_SECS.
    """
    cached = _rating_cache.get(symbol)
    if cached and time.time() - cached[0] < RATING_CACHE_SECS:
        return cached[1]

    try:
        from tradingview_ta import TA_Handler, Interval
    except Exception:
        return None

    for exchange in _TV_EXCHANGES:
        try:
            handler = TA_Handler(
                symbol=symbol,
                screener="america",
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY,
            )
            summary = handler.get_analysis().summary
            rating = {
                "symbol":         symbol,
                "exchange":       exchange,
                "recommendation": summary["RECOMMENDATION"],
                "buy":            summary["BUY"],
                "sell":           summary["SELL"],
                "neutral":        summary["NEUTRAL"],
            }
            _rating_cache[symbol] = (time.time(), rating)
            return rating
        except Exception:
            continue

    # Cache the miss so a bad symbol doesn't get retried every rerun
    _rating_cache[symbol] = (time.time(), None)
    return None


def get_tv_ratings(symbols: list) -> dict:
    """Fetch ratings for multiple symbols. Returns {symbol: rating_or_None}."""
    return {sym: get_tv_rating(sym) for sym in symbols}


def rating_color(recommendation: str) -> str:
    if "BUY" in recommendation:
        return "#05e87a"
    if "SELL" in recommendation:
        return "#ff4365"
    return "#ffb020"


# ── Webhook Alert Storage ─────────────────────────────────────────────────────
# tv_webhook.py appends incoming TradingView alerts to TV_ALERTS_FILE;
# the Streamlit app reads them here.

def load_tv_alerts(limit: int = 50) -> list:
    """Load stored TradingView webhook alerts, newest first."""
    if not os.path.exists(TV_ALERTS_FILE):
        return []
    try:
        with open(TV_ALERTS_FILE) as f:
            alerts = json.load(f)
        return list(reversed(alerts))[:limit]
    except Exception:
        return []


def save_tv_alert(alert: dict, max_alerts: int = 200) -> None:
    """Append a webhook alert to the alerts file, keeping the most recent."""
    alerts = []
    if os.path.exists(TV_ALERTS_FILE):
        try:
            with open(TV_ALERTS_FILE) as f:
                alerts = json.load(f)
        except Exception:
            alerts = []
    alert.setdefault("received_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    alerts.append(alert)
    with open(TV_ALERTS_FILE, "w") as f:
        json.dump(alerts[-max_alerts:], f, indent=2)


def clear_tv_alerts() -> None:
    if os.path.exists(TV_ALERTS_FILE):
        os.remove(TV_ALERTS_FILE)
