# ─────────────────────────────────────────────
#  symbols.py — Symbol search index
#  Lets the user type "apple" or "aapl" instead of
#  needing the exact ticker.
# ─────────────────────────────────────────────

import time

from config import SCAN_UNIVERSE

# Common names outside the S&P 500 that the app references directly.
EXTRA_NAMES = {
    "SPY":  "SPDR S&P 500 ETF",
    "QQQ":  "Invesco QQQ Trust",
    "IWM":  "iShares Russell 2000 ETF",
    "DIA":  "SPDR Dow Jones Industrial Average ETF",
    "VIX":  "CBOE Volatility Index",
    "SOFI": "SoFi Technologies",
    "GSAT": "Globalstar",
    "AMPX": "Amprius Technologies",
    "HOOD": "Robinhood Markets",
    "COIN": "Coinbase Global",
    "RBLX": "Roblox",
    "SNAP": "Snap Inc.",
    "RIVN": "Rivian Automotive",
    "LCID": "Lucid Group",
    "SHOP": "Shopify",
    "SQ":   "Block Inc.",
    "LYFT": "Lyft Inc.",
}

_index_cache: tuple[float, dict] | None = None
INDEX_CACHE_SECS = 24 * 3600


def get_symbol_index() -> dict[str, str]:
    """
    {ticker: company name} across the S&P 500 plus the app's own symbols.
    Cached in-process for a day; the underlying S&P list is cached on disk.
    """
    global _index_cache
    if _index_cache and time.time() - _index_cache[0] < INDEX_CACHE_SECS:
        return _index_cache[1]

    index: dict[str, str] = {}
    try:
        from universe import get_sp500_names
        index.update(get_sp500_names())
    except Exception as e:
        print(f"Symbol index: S&P names unavailable ({e})")

    index.update(EXTRA_NAMES)
    # Anything the app references but we have no name for maps to itself
    for sym in SCAN_UNIVERSE:
        index.setdefault(sym, sym)

    _index_cache = (time.time(), index)
    return index


def search_symbols(query: str, limit: int = 25) -> list[tuple[str, str]]:
    """
    Search tickers and company names. Returns [(ticker, name)] ranked by
    how directly the match lands: exact ticker, ticker prefix, name start,
    then anywhere in the name.
    """
    index = get_symbol_index()
    q = (query or "").strip().upper()
    if not q:
        return [(s, index[s]) for s in sorted(index)][:limit]

    scored: list[tuple[int, str, str]] = []
    for ticker, name in index.items():
        upper_name = name.upper()
        if ticker == q:
            rank = 0
        elif ticker.startswith(q):
            rank = 1
        elif upper_name.startswith(q):
            rank = 2
        elif q in ticker:
            rank = 3
        elif q in upper_name:
            rank = 4
        else:
            continue
        scored.append((rank, ticker, name))

    scored.sort(key=lambda r: (r[0], len(r[1]), r[1]))
    return [(t, n) for _, t, n in scored[:limit]]


def format_symbol(ticker: str) -> str:
    """'AAPL · Apple Inc.' — the label shown in pickers."""
    name = get_symbol_index().get(ticker, "")
    return f"{ticker} · {name}" if name and name != ticker else ticker


def resolve_symbol(text: str) -> str | None:
    """
    Turn free text into a ticker. Accepts a ticker, a company name, or a
    'TICKER · Name' label. Returns None when nothing matches.
    """
    raw = (text or "").strip()
    if not raw:
        return None  # whitespace-only used to fall through and return "A"
    if "·" in raw:
        ticker = raw.split("·")[0].strip().upper()
        return ticker or None

    upper = raw.upper()
    index = get_symbol_index()
    if upper in index:
        return upper

    hits = search_symbols(raw, limit=1)
    return hits[0][0] if hits else None
