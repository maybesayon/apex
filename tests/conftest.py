"""
Shared fixtures.

The whole point of this suite is to be a regression baseline for the
Next.js migration: it must produce identical numbers on any machine, with
no network. Everything therefore reads frozen OHLCV from tests/fixtures/.

Note on patching: the analysis modules do `from prices import
get_historical_data`, which binds the function into their own namespace at
import time. Patching `prices.get_historical_data` would not affect them,
so each patch targets the *consuming* module.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden"

sys.path.insert(0, str(Path(__file__).parent.parent))

# Point the app database at a throwaway file before any module imports it.
os.environ.setdefault("APEX_DB_PATH", "/tmp/apex-test-placeholder.db")


def load_fixture(name: str) -> pd.DataFrame:
    """Frozen OHLCV, indexed by date, exactly as get_historical_data returns."""
    df = pd.read_csv(FIXTURES / f"{name}.csv", index_col=0)
    # pandas 3.x no longer infers datetimes from parse_dates=True on the index,
    # and downstream code calls .date()/.strftime() on it, so convert explicitly.
    # utc=True is required because the real fixtures were saved tz-aware and
    # span a DST change, which otherwise raises "Mixed timezones". Dropping the
    # tz afterwards keeps real and synthetic fixtures uniform.
    df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    df.index.name = None
    return df


@pytest.fixture
def aapl():
    return load_fixture("AAPL_2y")


@pytest.fixture
def nvda():
    return load_fixture("NVDA_2y")


@pytest.fixture
def flat():
    """Constant price — historically caused divide-by-zero in Bollinger %."""
    return load_fixture("FLAT")


@pytest.fixture
def short_rising():
    """25 bars, monotonically rising — shorter than the MACD warm-up."""
    return load_fixture("SHORT_RISING")


@pytest.fixture
def penny():
    """Sub-$0.20 prices — historically rounded ATR to 0 and produced inf."""
    return load_fixture("PENNY")


@pytest.fixture
def offline(monkeypatch):
    """
    Cut every network path. Analysis modules read fixtures instead.
    Any test using this fixture is fully deterministic.
    """
    def fake_history(symbol, period="1y", interval="1d"):
        name = f"{symbol.upper()}_2y"
        path = FIXTURES / f"{name}.csv"
        if not path.exists():
            path = FIXTURES / f"{symbol.upper()}.csv"
        if not path.exists():
            return pd.DataFrame()
        return load_fixture(path.stem)

    def fake_quote(symbol):
        df = fake_history(symbol)
        if df.empty:
            return None
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        return {
            "symbol": symbol, "price": round(last, 2),
            "change": round(last - prev, 2),
            "pct_change": round((last - prev) / prev * 100, 2),
            "high": round(float(df["high"].iloc[-1]), 2),
            "low": round(float(df["low"].iloc[-1]), 2),
            "open": round(float(df["open"].iloc[-1]), 2),
            "prev_close": round(prev, 2), "source": "fixture",
        }

    import backtest, ml_predictions, scanner

    for mod in (backtest, ml_predictions, scanner):
        monkeypatch.setattr(mod, "get_historical_data", fake_history, raising=False)
    monkeypatch.setattr(scanner, "get_live_quote", fake_quote, raising=False)
    monkeypatch.setattr(scanner, "get_company_profile",
                        lambda s: {"name": s, "industry": "Test", "market_cap": 0},
                        raising=False)
    # TradingView ratings are a live scrape and display-only
    monkeypatch.setattr(scanner, "get_tv_rating", lambda s: None, raising=False)
    # Model cache would otherwise leak results between tests
    monkeypatch.setattr(ml_predictions, "_model_cache", {}, raising=False)
    return fake_history


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """A fresh database per test, so account tests never share state."""
    import importlib
    db_path = tmp_path / "apex_test.db"
    monkeypatch.setenv("APEX_DB_PATH", str(db_path))
    import db as db_module
    importlib.reload(db_module)
    db_module.init_db()
    import auth as auth_module
    importlib.reload(auth_module)
    return db_module


# ── Golden-snapshot helpers ───────────────────────────────────────────────────

def _canon(obj, ndigits=6):
    """Round floats recursively so snapshots do not churn on FP noise."""
    import math
    if isinstance(obj, dict):
        return {k: _canon(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canon(v, ndigits) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return round(obj, ndigits)
    if hasattr(obj, "item"):          # numpy scalar
        return _canon(obj.item(), ndigits)
    return obj


def assert_golden(name: str, value, ndigits=6):
    """
    Compare against a stored snapshot. Regenerate deliberately with
    APEX_UPDATE_GOLDEN=1 pytest — never automatically, or a regression
    would silently rewrite its own baseline.
    """
    GOLDEN.mkdir(parents=True, exist_ok=True)
    path = GOLDEN / f"{name}.json"
    actual = _canon(value, ndigits)

    if os.environ.get("APEX_UPDATE_GOLDEN") == "1":
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        return

    if not path.exists():
        raise AssertionError(
            f"No golden file for '{name}'. Create it with:\n"
            f"  APEX_UPDATE_GOLDEN=1 pytest tests/ -k {name}"
        )

    expected = json.loads(path.read_text())
    assert actual == expected, (
        f"Output drifted from tests/fixtures/golden/{name}.json.\n"
        f"If the change is intentional, review the diff and regenerate:\n"
        f"  APEX_UPDATE_GOLDEN=1 pytest tests/ -k {name}"
    )
