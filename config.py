# ─────────────────────────────────────────────
#  APEX Trading Intelligence — Configuration
# ─────────────────────────────────────────────
#  Prefer a local `.env` file (copy from `.env.example`) — never commit real keys.
# ─────────────────────────────────────────────

import os

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# ── API Keys ──────────────────────────────────
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

# ── TradingView Integration ───────────────────
TV_WEBHOOK_SECRET = os.environ.get("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
TV_WEBHOOK_PORT = 5001
TV_ALERTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tv_alerts.json")

# ── Email Alerts (optional) ───────────────────
ALERT_EMAIL_FROM = ""  # Your Gmail address
ALERT_EMAIL_TO = ""  # Where to send alerts
ALERT_EMAIL_PASS = ""  # Gmail app password (not regular password)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ── Portfolio & Watchlist ─────────────────────
# These are NOT configured here any more. Holdings, watchlists and trade
# journals belong to individual accounts and live in the database (db.py),
# so each user sees only their own. New accounts start from
# db.DEFAULT_WATCHLIST.

# ── Scanner Universe ──────────────────────────
# Stocks the scanner will analyze for opportunities
SCAN_UNIVERSE = [
    "NVDA", "SOFI", "GSAT", "PLTR", "AMD", "TSLA", "META", "AMPX",
    "AAPL", "MSFT", "AMZN", "GOOGL", "NFLX", "CRM", "SHOP", "SQ",
    "COIN", "HOOD", "RBLX", "SNAP", "UBER", "LYFT", "RIVN", "LCID",
]

# ── Broad Scan (S&P 500) ──────────────────────
SP500_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp500_cache.json")
BROAD_SCAN_TOP_N = 40  # how many pre-filtered names get the full TA scan

# ── App Settings ──────────────────────────────
APP_TITLE = "APEX — Trading Intelligence"
PRICE_REFRESH_SECS = 30  # How often to refresh prices
SCAN_ALERT_THRESHOLD = 70  # Min confidence score to trigger alert
BACKTEST_START_DATE = "2023-01-01"

# ── Risk Management Defaults ──────────────────
DEFAULT_STOP_LOSS_PCT = 0.17  # 17% below entry
DEFAULT_TARGET_PCT = 0.25  # 25% above entry
MAX_POSITION_SIZE_PCT = 0.40  # Max 40% of portfolio in one stock
