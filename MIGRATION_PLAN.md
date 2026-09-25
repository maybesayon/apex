# APEX — Streamlit → Next.js Migration Plan

Status: **plan only. No production code changed.**
Inspection date: 2026-09-24 · Codebase: 4,144 LOC across 15 Python modules

---

## 1. Inspection findings

### 1.1 Structure and entry point

Single flat Python package, no sub-packages. Entry point is `app.py`, run via
`streamlit run app.py`. A **second, separate entry point** exists:
`tv_webhook.py`, a standalone Flask server on port 5001 that receives
TradingView alert webhooks.

| Layer | Modules | LOC |
|---|---|---|
| Presentation (Streamlit-bound) | `app.py`, `theme.py`, `login_ui.py` | 1,600 |
| Analysis engine (pure, portable) | `indicators.py`, `scanner.py`, `backtest.py`, `ml_predictions.py`, `universe.py` | 1,058 |
| Data access | `prices.py`, `symbols.py`, `tradingview.py` | 447 |
| Persistence / identity | `db.py`, `auth.py` | 327 |
| Integrations | `chat.py`, `alerts.py` | 594 |
| Config | `config.py` | 65 |
| Second service | `tv_webhook.py` (Flask) | 58 |

**The 1,600 LOC presentation layer is what gets replaced.** The remaining
~2,500 LOC is framework-agnostic and moves unchanged.

### 1.2 Features that exist today

Seven tabs in `app.py`: Overview (market pulse + opportunity cards +
portfolio), Analysis (technical indicators + charts + TradingView rating),
Charts (TradingView embeds), Backtest, Forecast (ML), Journal, Assistant
(Claude chat). Plus sidebar: scan trigger, watchlist CRUD, theme toggle,
sign out. Auth gate in front of everything.

**Confirmed absent: News (zero references in any module) and fundamentals**
beyond `get_company_profile`'s name/industry/market-cap/logo/url — and that
returns `{"name": symbol, "industry": "N/A", "market_cap": 0}` unless a
Finnhub key is configured. No P/E, EPS, revenue, earnings, or financials
anywhere. These are Phase 8 new features, per decision 1.

### 1.3 Public function inventory → API mapping

Every analysis function is already pure and already returns a JSON-shaped
dict. This is the single biggest reason the migration is low-risk.

| Module | Function | Exposed as |
|---|---|---|
| `prices` | `get_live_quote`, `get_multiple_quotes` | `GET /quotes?symbols=` |
| | `get_historical_data` | `GET /stocks/{sym}/history?period=` |
| | `get_company_profile` | `GET /stocks/{sym}/profile` |
| `indicators` | `calculate_all`, `get_signal_summary` | `GET /stocks/{sym}/analysis` |
| | `get_support_resistance`, `estimate_hold_horizon`, `calculate_stop_and_target` | (folded into `/analysis`) |
| `scanner` | `score_opportunity` | `GET /stocks/{sym}/opportunity` |
| | `run_full_scan`, `run_broad_scan` | **job**: `POST /jobs/scan` |
| `backtest` | `backtest_momentum_strategy` | `POST /backtest` |
| `ml_predictions` | `predict_direction` | `GET /stocks/{sym}/forecast` |
| `symbols` | `search_symbols`, `resolve_symbol` | `GET /search?q=` |
| `tradingview` | `get_tv_rating`, `get_tv_ratings` | `GET /stocks/{sym}/rating` |
| | `tv_*_html` | **dropped** — React renders TV widgets directly |
| | `load_tv_alerts`, `save_tv_alert` | `GET /alerts`, webhook `POST /webhooks/tradingview` |
| `db` | positions / watchlist / journal / theme CRUD | `/portfolio`, `/watchlist`, `/journal`, `/settings` |
| `auth` | `register`, `authenticate`, `validate_signup` | `/auth/register`, `/auth/login` |
| `chat` | `chat`, `get_emotion_warning` | `POST /chat` (stream) |
| `alerts` | `send_*` | internal only — not exposed |

`tradingview.tv_*_html` functions are the only data-layer code that dies:
they exist solely to emit HTML strings for `st.iframe`. React embeds the
TradingView widget scripts directly, which is simpler.

### 1.4 Measured latency — this sizes the architecture

Measured on this machine, warm caches, 2026-09-24:

| Operation | Time | Needs a job? |
|---|---|---|
| `get_live_quote` | 0.52s | no |
| `get_historical_data` (1y) | 0.03s | no |
| `calculate_all` + `get_signal_summary` | 0.04s | no |
| `score_opportunity` (1 symbol) | 0.49s | no |
| `predict_direction` (cold train) | **0.83s** | **no** |
| `predict_direction` (cached) | 0.00s | no |
| `search_symbols` | 0.00s | no |
| `get_tv_rating` | 0.00s | no |
| `run_full_scan` (24 symbols) | **21.4s** | yes |
| `prefilter_universe` (503 tickers) | 10.2s | — |
| **`run_broad_scan` (projected)** | **~46s** | **yes** |

**Correction to an earlier estimate:** I previously said the expensive
operations take "minutes." Measured, the broad scan is ~46 seconds and ML
training is under a second. That changes the justification but not the
conclusion:

- 46s still exceeds common defaults — Vercel serverless (10s hobby / 60s pro),
  nginx `proxy_read_timeout` 60s, AWS ALB 60s.
- It grows with cold caches, rate limiting, or a larger universe.
- The requested progress UI requires a job model regardless of duration.

**ML training does not need the job queue.** At 0.83s it is a normal
request. Only the scan needs async. Building the queue generically means
it is there when a future operation does get expensive.

### 1.5 External providers

| Provider | Used by | Official? | Auth | Rate limits | Production concerns | Replacement path |
|---|---|---|---|---|---|---|
| **yfinance** | `prices.get_live_quote` (fallback), `get_historical_data` (**sole source**), `universe.prefilter_universe` | **No** — unofficial scraper of Yahoo endpoints | none | Undocumented; aggressive use gets IP-throttled | Yahoo ToS prohibits commercial redistribution. This is the **only** source of historical OHLCV, so the whole analysis engine depends on an unofficial library | Swap inside `prices.get_historical_data` only — one function. Candidates: Polygon.io, Tiingo, Alpha Vantage, EODHD |
| **Finnhub** | `prices.get_live_quote` (primary when keyed), `get_company_profile` | **Yes** | `FINNHUB_API_KEY`, optional | 60 req/min free | Free tier lacks much fundamental data; US-only coverage on free | Already abstracted behind `_get_finnhub()`. Paid tier also covers Phase 8 news + fundamentals |
| **tradingview-ta** | `tradingview.get_tv_rating` | **No** — unofficial scraper | none | Undocumented | Breaks whenever TradingView changes internals. Already fails soft (returns `None`) | Display-only, non-critical. Drop or replace with own signal aggregation |
| **TradingView embed widgets** | `tv_advanced_chart_html`, etc. | Yes (public embeds) | none | n/a | Attribution requirements in TV's embed ToS; must keep their branding visible | Being replaced by Lightweight Charts for price display; embeds may stay for the Charts tab |
| **Wikipedia** | `universe.get_sp500_tickers` | No (HTML scrape) | none | none | Table markup can change; cached 7 days on disk with stale-cache fallback | Any index constituent API |
| **Anthropic** | `chat.chat` | Yes | `ANTHROPIC_API_KEY`, optional | account-based | Cost per call; falls back to offline analyzer when unkeyed | n/a |
| **SMTP (Gmail)** | `alerts.send_email_alert` | Yes | app password in `config.py` | Gmail sending limits | **Credentials currently hardcoded as empty strings in `config.py`, not env vars** — fix before deploy | Transactional provider (Resend/SES/Postmark) |

Per decision 3, none are replaced in this migration.

**One item I would escalate:** the email credentials in `config.py`
(`ALERT_EMAIL_PASS`) are plain module constants rather than
`os.environ.get(...)` like the other secrets. They are empty today, so
nothing leaks, but the shape invites committing a password. Two-line fix,
worth doing in Phase 2.

### 1.6 Configuration and runtime state

Env vars: `FINNHUB_API_KEY`, `ANTHROPIC_API_KEY`, `TRADINGVIEW_WEBHOOK_SECRET`,
`APEX_DB_PATH`. Non-env config in `config.py`: SMTP settings, `SCAN_UNIVERSE`,
`BROAD_SCAN_TOP_N`, risk defaults, `APP_TITLE`.

Runtime state written to disk — **all three must be shared between the API
process and the worker process**, which rules out container-local storage:

| File | Written by | Migration note |
|---|---|---|
| `apex.db` (SQLite) | `db.py` | → Postgres. Ephemeral filesystems lose it on restart |
| `sp500_cache.json` | `universe.py` | → Redis or Postgres |
| `tv_alerts.json` | `tradingview.py` | → Postgres table |

In-process caches (`ml_predictions._model_cache`, `tradingview._rating_cache`,
`symbols._index_cache`) become per-worker rather than global once there are
multiple processes. Correctness is unaffected — they are pure read caches with
TTLs — but hit rates drop. Move to Redis opportunistically, not urgently.

### 1.7 Testing — resolved in Phase 0

At inspection time there was **no test suite in the repository**, which made
the spec's "run the existing tests" instruction impossible to satisfy and
left Phase 2's contract tests with no baseline to compare against.

**Phase 0 has since closed this.** `tests/` now holds 190 offline,
deterministic tests with golden-output snapshots:

| File | Tests | Covers |
|---|---:|---|
| `test_indicators.py` | 27 | Indicator math, golden snapshots, stop/target |
| `test_backtest.py` | 17 | Strategy output, consistency, look-ahead safety |
| `test_ml.py` | 21 | Validation integrity, label leakage, determinism |
| `test_accounts.py` | 27 | Password hashing, per-user isolation |
| `test_scanner_search.py` | 36 | Opportunity scoring, symbol search |
| `test_app_render.py` | 6 | Auth gate, both themes |
| `test_api_contract.py` | 35 | HTTP output equals direct calls, access control |
| `test_auth_session.py` | 21 | JWT, refresh rotation, CSRF, restart survival |

Properties that matter for the migration:

- **No network.** Verified by running the whole suite with `socket.connect`,
  `create_connection` and `getaddrinfo` patched to raise. All 134 pass.
- **Deterministic.** Frozen OHLCV in `tests/fixtures/`; repeated runs are
  byte-identical.
- **Detects drift.** Verified by injecting a regression — changing the RSI
  window from 14 to 15 failed 6 golden tests across 4 modules.

This is the baseline Phase 2 contract tests compare against.

### 1.8 Incidental cleanup found

- Two virtualenvs: `venv/` (stale, missing `lxml`) and `.venv/` (current).
  Delete `venv/`. *(still outstanding)*
- ~~`tv_webhook.py` is a whole second Flask service for one endpoint.~~
  ✅ Phase 2 — folded into `api/routers/webhooks.py`; Flask removed from
  `requirements.txt` and the old module left as a shim that exits with
  instructions.
- ~~SMTP credentials are plain module constants in `config.py`.~~
  ✅ Phase 2 — now read from the environment like every other secret.
- ~~`requirements.txt` has no dev/test split.~~ ✅ Phase 2 —
  `requirements-dev.txt` added.
- `config.BACKTEST_START_DATE` is imported by `backtest.py` and never used.
  *(still outstanding)*

---

## 2. Target architecture

```
apex/
├── backend/
│   ├── apex/               # analysis engine, moved unchanged
│   │   ├── indicators.py  scanner.py  backtest.py  ml_predictions.py
│   │   ├── prices.py  symbols.py  universe.py  tradingview.py
│   │   ├── chat.py  alerts.py  config.py
│   │   └── db.py  auth.py
│   ├── api/
│   │   ├── main.py         # FastAPI app
│   │   ├── routers/        # stocks, portfolio, watchlist, journal, jobs, auth, chat
│   │   ├── schemas/        # Pydantic models = the frontend contract
│   │   └── deps.py         # auth dependency, db session
│   ├── worker/
│   │   ├── tasks.py        # RQ job functions
│   │   └── worker.py
│   └── tests/              # committed regression + contract tests
├── frontend/               # Next.js App Router, TypeScript, Tailwind, shadcn/ui
│   ├── app/                # /, /markets, /stocks/[ticker], /portfolio,
│   │                       #   /watchlist, /backtest, /journal, /assistant, /settings
│   ├── components/         # AppShell, StockChart, MetricCard, Watchlist, ...
│   └── lib/                # api client, generated types, hooks
└── streamlit_legacy/       # untouched during migration; deleted at Phase 10
```

Processes: **Next.js** · **FastAPI** · **RQ worker** · **Redis** · **Postgres**.
Up from one today. This is the real operational cost of the migration.

### 2.1 Job system: RQ, not ARQ or Celery

**RQ.** The reason is concrete: the entire analysis engine is *synchronous
and blocking* — `yfinance`, `scikit-learn`, `ta`, `requests`, `sqlite3`.
ARQ is asyncio-native, so every call would need wrapping in
`run_in_executor`, adding ceremony that buys nothing. Celery's routing,
chords, and beat scheduling are unused weight here. RQ forks a process per
job, runs plain sync functions with zero modification, and its API is about
four calls. It fits this codebase exactly.

Job contract:

```
POST /jobs/scan   {scope: "universe"|"broad", min_score}  → 202 {job_id}
GET  /jobs/{id}   → {status: queued|running|finished|failed,
                     progress: {done, total, current_symbol},
                     result?, error?}
DELETE /jobs/{id} → cancel
```

Progress comes from `job.meta` updated inside the scan loop — `run_full_scan`
already prints per-symbol, so it needs one callback parameter added, not a
rewrite. Frontend polls every 1.5s (SSE is a later refinement; polling is
adequate for a 46s job and far simpler).

---

## 3. Revised phase order

The submitted order is sound with **two changes**. Phases 6 and 7 as written
are *dependencies* of Phase 5, not follow-ups:

- **Auth (was Phase 7)** — Portfolio, Watchlist, and Journal screens all need
  a signed-in user. Building them against no auth means building them twice.
- **Jobs (was Phase 6)** — The Overview screen's core action is "Scan market."
  Building that screen before the job system means a throwaway synchronous
  version.

Both move before the bulk screen migration.

| Phase | Work | Exit criteria |
|---|---|---|
| **0** | Commit the regression suite with golden snapshots on fixed fixtures | ✅ **complete** — 134 tests, offline, deterministic, drift-detecting |
| **1** | *(this document)* | ✅ complete |
| **2** | FastAPI boundary, contract tests, fold in `tv_webhook.py`, SMTP creds to env | ✅ **complete** — 31 operations, 35 contract tests, Flask removed |
| **3** | Auth rework (JWT, httpOnly cookies, refresh rotation, CSRF) and SQLAlchemy + Alembic | ✅ **complete** — sessions survive restart, reuse detection, Postgres-portable |
| **4** | Job system — Redis + RQ, `/jobs/*`, progress reporting in scan loop | Broad scan runs async with live progress; failures/timeouts surface |
| **5** | Next.js foundation — App Router, TypeScript, Tailwind with tokens ported from `theme.py`, shadcn/ui, theme provider, AppShell, generated API types | Both themes render; type-safe client; auth flow works |
| **6** | **Stock detail screen** (`/stocks/[ticker]`) — Lightweight Charts, indicators, TV rating, watchlist action, Framer Motion | Visually matches current Analysis tab's data exactly |
| **7** | Remaining screens — Overview, Portfolio, Watchlist, Backtest, Forecast, Journal, Assistant | Feature parity with all 7 Streamlit tabs |
| **8** | Fundamentals + News (new). Provider selection documented with pricing/limits | P/E, EPS, revenue, earnings, 52w range, financials; company + market news |
| **9** | Regression + polish — output comparison vs Streamlit, responsive, a11y, loading/error/empty states | Side-by-side outputs match; Lighthouse ≥ 90 |
| **10** | Retire Streamlit | Parity confirmed; `streamlit_legacy/` deleted |

Phases 0–4 are backend-only: **Streamlit keeps running untouched throughout.**
First user-visible change is Phase 5.

---

## 4. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ~~No regression baseline exists~~ | ~~High~~ | ✅ Resolved in Phase 0 — 134 offline tests with golden snapshots |
| Historical data depends entirely on an unofficial scraper | **High** | Isolated to one function; swap is contained. Revisit post-migration per decision 3 |
| ~~Silent numeric drift during port~~ | ~~High~~ | ✅ Resolved in Phase 2 — 35 contract tests assert API output equals direct calls |
| SQLite on ephemeral storage loses all accounts | **High** | ⚠️ Partly resolved — the code is Postgres-portable via `DATABASE_URL`, but Postgres itself is **untested** (no server available locally) and is still the default-off path |
| Ops surface grows 1 → 5 processes | Medium | `docker-compose` for local; single PaaS with managed Redis/Postgres |
| Lightweight Charts has no built-in indicator overlays | Medium | Bollinger/MA are extra line series; RSI is a second pane. Both supported |
| Scan cost grows past 46s | Medium | Already async after Phase 4; add concurrency inside the worker |
| Scope creep from the reference image | Medium | News/fundamentals fenced to Phase 8 by decision 1 |

---

## 5. What I need from you before Phase 0

1. **Postgres now or later?** Phase 3 assumes yes. Staying on SQLite is viable
   for a single always-on VPS but not for any PaaS with ephemeral disk.
2. **Deploy target?** Determines whether the 46s job even needs the queue for
   timeout reasons (it still needs it for progress UI).
3. **Finnhub paid tier?** Their paid plan covers Phase 8 news *and*
   fundamentals in one provider you already integrate. Deciding early avoids
   integrating two.

---

*No production files were modified in producing this plan.*
