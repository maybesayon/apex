# APEX

A stock analysis platform: technical analysis, strategy backtesting, and a
price-direction model that reports honestly on whether it works.

Python · Streamlit · scikit-learn · pandas · SQLite

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

## Architecture

~4,100 lines across 17 modules. The analysis engine is pure Python with no
framework dependency — it neither imports nor knows about Streamlit.

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
python tv_webhook.py      # receiver on :5001
ngrok http 5001           # expose it
```

Point a TradingView alert at
`https://<ngrok-url>/webhook/tradingview?secret=<your-secret>` with body:

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

**Auth is private-beta grade.** No email verification, no password reset, no
rate limiting or lockout. Sessions live in server memory. SQLite suits one
instance, not a scaled one. Serve over HTTPS or credentials cross the wire in
the clear. Documented at the top of [`auth.py`](auth.py).

**Two data sources are unofficial.** `yfinance` scrapes Yahoo and is the sole
source of historical OHLCV; `tradingview-ta` scrapes TradingView. Fine for
personal use, a real ToS question for anything commercial.

**No automated test suite is committed yet.** The regression suite is the
first item in the migration plan.

**It never places trades.** APEX is an analysis tool.

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
