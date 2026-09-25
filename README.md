# APEX

A stock analysis platform: technical analysis, strategy backtesting, and a
price-direction model that reports honestly on whether it works.

Python · FastAPI · Streamlit · scikit-learn · pandas · SQLAlchemy

---

## What it does

Multi-user accounts, each with their own watchlist, holdings and trade
journal. Seven screens:

| Screen | What it does |
|---|---|
| **Overview** | Market condition, opportunity cards with entry/target/stop, portfolio value |
| **Analysis** | RSI, MACD, Bollinger Bands, moving averages, volume — charted, with a signal score |
| **Charts** | Embedded TradingView charts, technical-rating gauge, alert feed |
| **Backtest** | RSI + MACD momentum strategy over 2 years, with equity curve and trade log |
| **Forecast** | Gradient-boosting model predicting a >5% move over 10 trading days |
| **Journal** | Log trades; win rate and realised P&L computed from what you log |
| **Assistant** | Claude-backed chat with live quote context, or an offline analyzer without a key |

---

## The part worth reading

If you only look at one thing in this repo, make it
[`ml_predictions.py`](ml_predictions.py).

**Financial time series break the usual train/test split.** Shuffling lets a
model train on October and test on August — it sees the future, and accuracy
comes back inflated. So validation here uses expanding-window walk-forward
splits: every fold trains only on data preceding its test slice.

That alone is still not enough. The label at row *i* is built from the price
at *i + 10*, so the last 10 training rows of each fold carry labels computed
from prices inside the test window. Ten leaked rows at every fold boundary.
The fix is an embargo — drop those rows before fitting:

```python
train_idx = train_idx[train_idx < test_idx[0] - PREDICT_HORIZON_DAYS]
```

Accuracy is then reported next to the **majority-class baseline**, because
60% accuracy means nothing if 60% of windows are one-sided. Probabilities are
calibrated with Platt scaling, since raw gradient-boosting scores are not
probabilities.

**The result, measured across ten large-cap tickers (2026-09-24):**

```
mean walk-forward accuracy   63.3%
majority-class baseline      70.3%
                             −7.0 points — lost on 10 of 10
```

The model does not beat "always guess no." The app says so directly — the
Forecast screen leads with a **"No demonstrated skill"** banner and shows the
baseline as a first-class metric whenever the model fails to clear it.

That negative result is the point. A shuffled split would have reported
something in the eighties and it would have been believed. The measurement is
supposed to be true, not flattering.

---

## Quick start

Runs with **no API keys at all**.

```bash
git clone https://github.com/maybesayon/apex.git
cd apex
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. Create an account on first launch — your
watchlist, holdings and journal are stored locally in `apex.db`.

Optional keys in `.env` (copy from `.env.example`):

| Key | Without it |
|---|---|
| `FINNHUB_API_KEY` | Quotes fall back to yfinance |
| `ANTHROPIC_API_KEY` | Assistant uses a built-in offline analyzer |
| `TRADINGVIEW_WEBHOOK_SECRET` | Alert webhook runs unauthenticated (don't expose it) |

---

## API

A FastAPI layer exposes the analysis engine over HTTP. It runs alongside
Streamlit — both import the same modules, so there is one implementation of
every calculation.

```bash
uvicorn api.main:app --reload --port 8000
```

Interactive docs at `/docs`, OpenAPI schema at `/openapi.json`.
31 operations:

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `/auth/login` · `/auth/logout` · `GET /auth/me` |
| Market | `GET /search` · `/quotes` · `/stocks/{sym}/quote` · `/history` · `/profile` |
| Analysis | `GET /stocks/{sym}/analysis` · `/opportunity` · `/forecast` · `/rating` |
| Portfolio | `GET /portfolio` · `PUT/DELETE /portfolio/positions` |
| Watchlist | `GET/POST /watchlist` · `DELETE /watchlist/{sym}` |
| Journal | `GET/POST /journal` · `GET /journal/stats` |
| Operations | `POST /backtest` · `POST /chat` |
| Jobs | `POST /jobs/scan` · `GET /jobs` · `GET/DELETE /jobs/{id}` |
| Webhooks | `POST /webhooks/tradingview` · `GET/DELETE /alerts` |

Symbol paths accept company names, so `/stocks/apple/analysis` and
`/stocks/AAPL/analysis` are equivalent.

**Contract tests** assert the HTTP response equals a direct function call, so
the API layer cannot silently change a number. NaN and Infinity — which
indicators legitimately produce and JSON cannot represent — are serialised as
`null` rather than emitted as invalid JSON.

**Long scans run as jobs.** A scan takes 21–46 seconds, past most proxy and
serverless timeouts, so `POST /jobs/scan` returns a job id immediately and the
client polls for progress:

```
POST /jobs/scan        -> 202 {"id": "...", "status": "queued"}
GET  /jobs/{id}        -> {"status": "running", "progress": {"done": 11, "total": 24,
                            "pct": 45.8, "label": "AMZN"}}
GET  /jobs/{id}        -> {"status": "finished", "result": {...}}
DELETE /jobs/{id}      -> request cancellation
```

Jobs run on a thread pool inside the API process, with their state in the
database so progress is readable from any process and survives a restart.
Redis and RQ were the original plan; they are a paid add-on almost
everywhere, and one ~46s task an hour does not justify a message broker yet.
The executor is swappable without touching the schema or the API.

The older synchronous `POST /scan` still exists but is marked deprecated —
no client should build against it.

---

## Architecture

~4,100 lines of analysis code across 17 modules, plus the API layer. The
analysis engine is pure Python with no framework dependency — it neither
imports nor knows about Streamlit or FastAPI.

```
Data        prices.py       Finnhub → yfinance fallback
            symbols.py      518-symbol search index (ticker + company name)
            universe.py     S&P 500 constituents, cached 7 days on disk

Analysis    indicators.py   RSI, MACD, Bollinger, ATR, stochastic, signal scoring
            scanner.py      opportunity scoring, two-stage S&P 500 scan
            backtest.py     momentum strategy, equity curve, trade log
            ml_predictions.py  walk-forward validated gradient boosting

Platform    db.py           per-user positions, watchlist, journal (SQLite)
            auth.py         scrypt password hashing, timing-safe compare
            theme.py        light/dark design system

Integration tradingview.py  widgets, technical ratings, alert storage
            chat.py         Claude assistant with offline fallback
            alerts.py       email alerts

API         api/            FastAPI boundary: routers, schemas, auth
UI          app.py          Streamlit (being replaced — see MIGRATION_PLAN.md)
```

### Design decisions

**Every external dependency degrades gracefully.** Quotes try Finnhub then
yfinance. The assistant uses Claude if keyed, otherwise a local analyzer.
TradingView ratings return `None` rather than raising when the unofficial
library breaks. The S&P list falls back from Wikipedia to a stale cache to a
hardcoded universe. `pip install && streamlit run` works with zero
configuration.

**The broad scan is two-stage.** Running full technical analysis on 500
tickers is slow and hammers the API. A cheap batched pre-filter drops anything
under $3 or under $5M average daily dollar volume, then only the ~40 liveliest
names get the expensive pass. Measured: 10s pre-filter, ~46s total.

**Cache TTLs are reasoned, not guessed.** Trained models cache for an hour
because daily bars only update once a day. Prices 30s, TradingView ratings
5min, index constituents 7 days.

**Search accepts company names.** `symbols.py` ranks matches — exact ticker,
then ticker prefix, then name — so "apple" finds AAPL and "micro" finds MU,
MCHP, MSFT and AMD.

---

## TradingView integration

**Charts and ratings** work out of the box, no account needed. Ratings come
from the unofficial `tradingview-ta` library and are display-only.

**Alert webhooks** need a paid TradingView plan:

```bash
uvicorn api.main:app --port 8000
ngrok http 8000
```

Point a TradingView alert at
`https://<ngrok-url>/webhooks/tradingview?secret=<your-secret>` with body:

```json
{"symbol": "{{ticker}}", "price": {{close}}, "event": "RSI oversold", "interval": "{{interval}}"}
```

---

## Known limitations

Stated plainly, because they affect how much you should trust the output.

**Backtest is optimistic.** It transacts at the same closing price that
generated the signal, models no commissions or slippage, checks stops only
against daily closes (so intraday stop-outs are missed), and allocates full
capital to one position at a time.

**Auth has real session handling but is not finished.** Access tokens are
short-lived JWTs in httpOnly cookies; refresh tokens are hashed in the
database, rotated on every use, and a replayed token revokes its whole
family. Sessions survive a restart. Still missing: email verification,
password reset, and rate limiting or lockout on login. Serve over HTTPS.

**Postgres support is untested.** The storage layer is SQLAlchemy and
switches with one environment variable, and every table compiles for the
Postgres dialect — but no Postgres server was available to run it against,
so treat that path as unverified until someone does.

**Two data sources are unofficial.** `yfinance` scrapes Yahoo and is the sole
source of historical OHLCV; `tradingview-ta` scrapes TradingView. Fine for
personal use, a real ToS question for anything commercial.

**It never places trades.** APEX is an analysis tool.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

206 tests, **fully offline and deterministic** — they read frozen OHLCV from
`tests/fixtures/` rather than calling any API, so they produce identical
numbers on any machine and run in CI without network.

| File | Tests | Covers |
|---|---:|---|
| `test_indicators.py` | 27 | Indicator math, golden snapshots, stop/target levels |
| `test_backtest.py` | 17 | Strategy output, consistency, look-ahead safety |
| `test_ml.py` | 21 | Validation integrity, label-leakage, determinism |
| `test_accounts.py` | 27 | Password hashing, per-user isolation |
| `test_scanner_search.py` | 36 | Opportunity scoring, symbol search |
| `test_app_render.py` | 6 | Auth gate, both themes |
| `test_api_contract.py` | 35 | HTTP output equals direct calls, access control |
| `test_auth_session.py` | 21 | JWT, refresh rotation, CSRF, restart survival |
| `test_jobs.py` | 16 | Job lifecycle, progress, cancellation, isolation |

**Golden snapshots** pin the exact numbers the analysis engine produces
today, so any numeric drift during the Next.js migration fails the build.
Verified by injecting a deliberate regression — changing the RSI window from
14 to 15 failed 6 tests across 4 modules.

Regenerate snapshots only after reviewing the diff:

```bash
APEX_UPDATE_GOLDEN=1 pytest
```

Many tests are regression guards for specific bugs found in QA: NaN
indicators scored as bearish, risk/reward hardcoded to 2.0, a zero price
producing `+inf` estimated moves, ATR rounding to zero on penny stocks, and
label leakage at walk-forward fold boundaries.

---

## Roadmap

[`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) documents a phased migration of the
presentation layer to Next.js + TypeScript + FastAPI, keeping the Python
analysis engine intact. It includes a full inspection of the current
architecture, measured latencies, a provider-dependency audit, and a
risk register.

Also planned: fundamentals (P/E, EPS, revenue, earnings) and news, both of
which are genuinely absent today rather than partially built.

---

## Disclaimer

Educational project. Not financial advice, and not a recommendation to buy or
sell anything. Backtest and model results are simulations over historical
data — past performance does not guarantee future results. Do your own
research.
