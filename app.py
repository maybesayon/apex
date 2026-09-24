# ─────────────────────────────────────────────
#  app.py — APEX Trading Intelligence
#  Run with: streamlit run app.py
# ─────────────────────────────────────────────

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import json
import time

from config import SCAN_UNIVERSE, APP_TITLE
import auth
import db
import login_ui
import theme as design
from prices import get_multiple_quotes, get_historical_data, get_live_quote, format_price, format_pct
from indicators import calculate_all, get_signal_summary, calculate_stop_and_target
from scanner import run_full_scan, run_broad_scan, score_opportunity
from backtest import backtest_momentum_strategy, backtest_multiple
from ml_predictions import predict_direction
from chat import chat, get_emotion_warning
from alerts import send_opportunity_alert, send_daily_briefing
from tradingview import (
    tv_advanced_chart_html, tv_technical_analysis_html, tv_ticker_tape_html,
    get_tv_rating, get_tv_ratings, rating_color, load_tv_alerts, clear_tv_alerts,
)
from symbols import get_symbol_index, format_symbol, resolve_symbol

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session & Theme ───────────────────────────────────────────────────────────
db.init_db()

if "user_id"  not in st.session_state: st.session_state.user_id  = None
if "username" not in st.session_state: st.session_state.username = None
if "theme"    not in st.session_state: st.session_state.theme    = "light"

st.markdown(design.css(st.session_state.theme), unsafe_allow_html=True)



# ── Session State Initialization ──────────────────────────────────────────────
if "chat_history"     not in st.session_state: st.session_state.chat_history = []
if "chat_messages"    not in st.session_state: st.session_state.chat_messages = []
if "live_quotes"      not in st.session_state: st.session_state.live_quotes = {}
if "scan_results"     not in st.session_state: st.session_state.scan_results = []
if "last_price_fetch" not in st.session_state: st.session_state.last_price_fetch = 0


# ── Per-user data ─────────────────────────────────────────────────────────────
# These replace the module-level WATCHLIST / PORTFOLIO constants that used to
# live in config.py, where one person's holdings were baked into the app and
# shown to everyone who opened it.

def uid() -> int:
    return st.session_state.user_id


def watchlist() -> list[str]:
    return db.get_watchlist(uid())


def portfolio() -> dict[str, dict]:
    return db.get_positions(uid())


def journal() -> list[dict]:
    return db.get_journal(uid())


# ── Helper: Refresh Prices ────────────────────────────────────────────────────
def refresh_prices():
    now = time.time()
    if now - st.session_state.last_price_fetch > 30:
        symbols = set(watchlist()) | set(portfolio()) | {"SPY", "QQQ", "VIX"}
        st.session_state.live_quotes = get_multiple_quotes(sorted(symbols))
        st.session_state.last_price_fetch = now


# ── Helper: Color for % change ────────────────────────────────────────────────
def pct_color(pct):
    if pct is None: return "gray"
    return "green" if pct >= 0 else "red"


def fmt_money(v, dp=2):
    return f"${v:,.{dp}f}"


def fmt_pct(v):
    return f"{v:+.2f}%"


def logo_chip(sym: str) -> str:
    """Monogram avatar — a logo stand-in that needs no image hosting."""
    return f'<div class="wl-logo">{sym[:2].upper()}</div>'


# ── Helper: Symbol picker with name search ────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _picker_options(mine: tuple[str, ...]) -> list[str]:
    """
    'AAPL · Apple Inc.' labels for every known symbol, with the user's own
    watchlist and holdings floated to the top so the common case is one click.
    Streamlit's selectbox filters this list as the user types, which is what
    gives us name search ("apple", "micro") without a custom widget.

    `mine` is passed in rather than read from session state because this is
    cached — reading per-user data inside would serve one user's ordering
    to everybody.
    """
    index = get_symbol_index()
    first = [s for s in dict.fromkeys(mine) if s in index]
    rest  = sorted(s for s in index if s not in first)
    return [format_symbol(s) for s in first + rest]


def symbol_picker(label: str, key: str, default: str = "NVDA") -> str:
    """Searchable symbol selector. Returns a bare ticker."""
    options = _picker_options(tuple(watchlist()) + tuple(portfolio()))
    try:
        idx = options.index(format_symbol(default))
    except ValueError:
        idx = 0
    choice = st.selectbox(
        label, options, index=idx, key=key,
        help="Type a ticker or a company name — e.g. 'AAPL' or 'apple'.",
        placeholder="Search by ticker or company name",
    )
    return resolve_symbol(choice) or default


# ── Global Ticker Tape ────────────────────────────────────────────────────────
def render_ticker_tape():
    """
    One scrolling tape at the top of every tab. This replaced a second,
    hand-rolled ticker bar — running both stacked two near-identical strips
    on top of each other.
    """
    refresh_prices()
    tape = list(dict.fromkeys(["SPY", "QQQ"] + list(watchlist())))[:12]
    st.iframe(tv_ticker_tape_html(tape), height=52)


# ── Market Pulse (dashboard card) ─────────────────────────────────────────────
def render_market_pulse():
    quotes = st.session_state.live_quotes
    spy = quotes.get("SPY")
    vix = quotes.get("VIX")

    bullish   = bool(spy and spy["pct_change"] >= 0)
    condition = "Bullish" if bullish else "Bearish"
    cls       = "up" if bullish else "down"
    vix_val   = f"{vix['price']:.2f}" if vix else "—"
    vix_label = ("Low fear" if vix["price"] < 20 else "Elevated fear") if vix else "—"
    spy_txt   = fmt_pct(spy["pct_change"]) if spy else "—"

    st.markdown(f"""
    <div class="sec">
      <div class="sec-title">Market</div>
      <div class="sec-sub">Updated {datetime.now().strftime('%I:%M %p')}</div>
    </div>
    <div class="stats">
      <div class="stat">
        <div class="stat-label">Condition</div>
        <div class="stat-value {cls}">{condition}</div>
      </div>
      <div class="stat">
        <div class="stat-label">S&amp;P 500</div>
        <div class="stat-value {cls}">{spy_txt}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Volatility</div>
        <div class="stat-value">{vix_val}</div>
        <div class="stat-sub">VIX</div>
      </div>
      <div class="stat">
        <div class="stat-label">Sentiment</div>
        <div class="stat-value">{vix_label}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(f"""
        <div style="padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:16px">
          <div style="font-size:23px;font-weight:680;letter-spacing:-0.03em">APEX</div>
          <div style="font-size:12.5px;color:var(--text2);margin-top:3px">
            Signed in as <strong style="color:var(--text)">{st.session_state.username}</strong>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Theme + sign out
        col_t, col_o = st.columns([1, 1])
        with col_t:
            is_dark = st.session_state.theme == "dark"
            if st.button("☾  Dark" if not is_dark else "☀  Light", use_container_width=True):
                new_theme = "dark" if not is_dark else "light"
                st.session_state.theme = new_theme
                db.set_theme(uid(), new_theme)
                st.rerun()
        with col_o:
            if st.button("Sign out", use_container_width=True):
                for k in ("user_id", "username", "live_quotes", "scan_results",
                          "chat_messages", "chat_history", "last_price_fetch"):
                    st.session_state.pop(k, None)
                st.rerun()

        st.markdown("---")

        # Scan scope + button
        scan_scope = st.radio(
            "Scan scope",
            ["My universe", "S&P 500 (broad)"],
            key="scan_scope",
            horizontal=True,
            label_visibility="collapsed",
        )
        if st.button("⚡  SCAN MARKET", use_container_width=True):
            if scan_scope == "S&P 500 (broad)":
                with st.spinner("Pre-filtering S&P 500, then scanning top candidates..."):
                    st.session_state.scan_results = run_broad_scan(min_score=55)
            else:
                with st.spinner("Scanning market..."):
                    st.session_state.scan_results = run_full_scan(min_score=55)
            st.success(f"Found {len(st.session_state.scan_results)} opportunities!")

        st.markdown("---")

        # Watchlist
        st.markdown('<div class="stat-label" style="margin-bottom:6px">Watchlist</div>',
                    unsafe_allow_html=True)
        quotes = st.session_state.live_quotes
        names  = get_symbol_index()
        wl     = watchlist()

        if not wl:
            st.caption("Your watchlist is empty. Add a symbol below.")

        rows = []
        for sym in wl:
            q = quotes.get(sym)
            if q:
                cls  = "up" if q["pct_change"] >= 0 else "down"
                px_  = fmt_money(q["price"])
                chg  = fmt_pct(q["pct_change"])
            else:
                cls, px_, chg = "muted", "—", "Loading"
            company = names.get(sym, "")
            rows.append(f"""
            <div class="wl-row">
              {logo_chip(sym)}
              <div class="wl-name">
                <div class="wl-tkr">{sym}</div>
                <div class="wl-co">{company if company != sym else ""}</div>
              </div>
              <div class="wl-right">
                <div class="wl-price">{px_}</div>
                <div class="wl-chg {cls}">{chg}</div>
              </div>
            </div>""")
        if rows:
            st.markdown("<div class='wl-sep'></div>".join(rows), unsafe_allow_html=True)

        st.markdown("---")

        # Manage watchlist
        with st.expander("Manage watchlist"):
            add = symbol_picker("Add a stock", key="wl_add", default="AAPL")
            if st.button("Add to watchlist", use_container_width=True):
                if add in wl:
                    st.info(f"{add} is already on your watchlist.")
                else:
                    db.add_to_watchlist(uid(), add)
                    st.rerun()
            if wl:
                drop = st.selectbox("Remove", wl, key="wl_drop")
                if st.button("Remove", use_container_width=True):
                    db.remove_from_watchlist(uid(), drop)
                    st.rerun()


# ── Dashboard Tab ─────────────────────────────────────────────────────────────
def render_dashboard():
    render_market_pulse()

    st.markdown("## 🔥 Opportunities")

    if not st.session_state.scan_results:
        st.info("Click **⚡ SCAN MARKET** in the sidebar to find opportunities.")
        # Show default watchlist picks
        results = []
        for sym in ["NVDA", "SOFI", "GSAT"]:
            r = score_opportunity(sym)
            if r:
                results.append(r)
        opportunities = results
    else:
        opportunities = st.session_state.scan_results[:6]

    if opportunities:
        cols = st.columns(3)
        for i, opp in enumerate(opportunities[:3]):
            with cols[i % 3]:
                score = opp["score"]
                tone  = "up" if score >= 70 else "warn"
                tags  = "".join(
                    f'<span class="pill">{t}</span>' for t in opp.get("tags", [])[:3]
                )
                bars = "".join(
                    f'<div style="flex:1;height:5px;border-radius:3px;background:'
                    f'{"var(--up)" if j < (score // 20) else "var(--border2)"}"></div>'
                    for j in range(5)
                )
                st.markdown(f"""
                <div class="card rise" style="margin-bottom:14px">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start">
                    <div style="min-width:0">
                      <div style="font-size:18px;font-weight:660;letter-spacing:-0.02em">{opp['symbol']}</div>
                      <div style="font-size:12.5px;color:var(--text2);margin-top:2px;
                                  white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{opp['name']}</div>
                    </div>
                    <div style="text-align:right;flex:none">
                      <div style="font-size:26px;font-weight:680;letter-spacing:-0.03em;
                                  color:var(--{tone})">{score}</div>
                      <div style="font-size:10.5px;color:var(--text3);letter-spacing:.04em">
                        {opp['confidence']}</div>
                    </div>
                  </div>

                  <div style="display:flex;gap:4px;margin:14px 0 16px">{bars}</div>

                  <div style="font-size:21px;font-weight:660;letter-spacing:-0.025em;
                              color:var(--{tone})">{opp['est_move']}</div>
                  <div style="font-size:12.5px;color:var(--text2);margin-top:2px">
                    Estimated move · {opp['horizon']}</div>

                  <div style="display:flex;gap:5px;flex-wrap:wrap;margin:14px 0">{tags}</div>

                  <div style="display:flex;gap:8px;padding-top:14px;
                              border-top:1px solid var(--border)">
                    <div style="flex:1">
                      <div class="stat-label">Entry</div>
                      <div style="font-size:14px;font-weight:620">${opp['entry']}</div>
                    </div>
                    <div style="flex:1">
                      <div class="stat-label">Target</div>
                      <div style="font-size:14px;font-weight:620;color:var(--up)">${opp['target']}</div>
                    </div>
                    <div style="flex:1">
                      <div class="stat-label">Stop</div>
                      <div style="font-size:14px;font-weight:620;color:var(--down)">${opp['stop']}</div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

    # Portfolio performance chart
    st.markdown("---")
    st.markdown("## 💼 Portfolio")
    render_portfolio()


# ── Portfolio Tab ─────────────────────────────────────────────────────────────
def _position_editor():
    """Add, update or remove a holding. Replaces editing config.py by hand."""
    with st.expander("Manage positions"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sym = symbol_picker("Stock", key="pos_sym", default="AAPL")
        with col2:
            shares = st.number_input("Shares", min_value=0.0, step=1.0, key="pos_shares")
        with col3:
            cost = st.number_input("Average cost ($)", min_value=0.0, step=0.01, key="pos_cost")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save position", use_container_width=True, type="primary"):
                if shares <= 0 or cost <= 0:
                    st.error("Shares and average cost must both be greater than zero.")
                else:
                    db.upsert_position(uid(), sym, shares, cost)
                    st.rerun()
        with col_b:
            held = list(portfolio().keys())
            if held:
                drop = st.selectbox("Remove holding", held, key="pos_drop",
                                    label_visibility="collapsed")
                if st.button("Remove position", use_container_width=True):
                    db.delete_position(uid(), drop)
                    st.rerun()


def render_portfolio():
    quotes = st.session_state.live_quotes
    rows   = []
    total_value = 0
    total_cost  = 0
    positions = portfolio()

    if not positions:
        st.markdown("""
        <div class="card rise" style="text-align:center;padding:40px 24px">
          <div style="font-size:17px;font-weight:600;margin-bottom:6px">No holdings yet</div>
          <div style="font-size:14px;color:var(--text2)">
            Add your first position below to track value, P&amp;L and performance.
          </div>
        </div>
        """, unsafe_allow_html=True)
        _position_editor()
        return

    for sym, pos in positions.items():
        q       = quotes.get(sym)
        price   = q["price"] if q else pos["avg_cost"]
        value   = price * pos["shares"]
        cost    = pos["avg_cost"] * pos["shares"]
        pnl     = value - cost
        pnl_pct = (pnl / cost) * 100
        total_value += value
        total_cost  += cost

        exits = calculate_stop_and_target(price)
        rows.append({
            "Symbol":    sym,
            "Shares":    pos["shares"],
            "Avg Cost":  f"${pos['avg_cost']:.2f}",
            "Current":   f"${price:.2f}",
            "P&L":       f"${pnl:+.0f} ({pnl_pct:+.1f}%)",
            "Target":    f"${exits['target']:.2f}",
            "Stop":      f"${exits['stop']:.2f}",
            "R/R":       f"{exits['risk_reward']}:1",
            "_pnl":      pnl,
        })

    total_pnl     = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost else 0

    # Hero: total value and today's move
    stats = db.journal_stats(uid())
    delta_cls = "pos" if total_pnl >= 0 else "neg"
    arrow     = "▲" if total_pnl >= 0 else "▼"

    st.markdown(f"""
    <div class="hero rise">
      <div class="hero-label">Total portfolio value</div>
      <div class="hero-value">{fmt_money(total_value)}</div>
      <div class="hero-delta {delta_cls}">
        {arrow} {fmt_money(abs(total_pnl))} ({total_pnl_pct:+.2f}%)
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Win rate now comes from the user's own logged trades. It used to be a
    # hardcoded "68% · 17 of 25", identical for every user and derived from
    # nothing at all.
    if stats["win_rate"] is None:
        win_value, win_sub = "—", "Log trades in the Journal"
    else:
        win_value = f"{stats['win_rate']:.0f}%"
        win_sub   = f"{stats['wins']} of {stats['trades']} trades"

    st.markdown(f"""
    <div class="stats">
      <div class="stat">
        <div class="stat-label">Cost basis</div>
        <div class="stat-value">{fmt_money(total_cost)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Unrealised P&amp;L</div>
        <div class="stat-value {'up' if total_pnl >= 0 else 'down'}">{total_pnl:+,.2f}</div>
        <div class="stat-sub">{total_pnl_pct:+.2f}%</div>
      </div>
      <div class="stat">
        <div class="stat-label">Positions</div>
        <div class="stat-value">{len(positions)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Realised win rate</div>
        <div class="stat-value">{win_value}</div>
        <div class="stat-sub">{win_sub}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Holdings
    st.markdown('<div class="sec"><div class="sec-title">Holdings</div></div>',
                unsafe_allow_html=True)
    names = get_symbol_index()
    cards = []
    for r in sorted(rows, key=lambda x: -abs(x["_pnl"])):
        sym = r["Symbol"]
        cls = "up" if r["_pnl"] >= 0 else "down"
        cards.append(f"""
        <div class="wl-row">
          {logo_chip(sym)}
          <div class="wl-name">
            <div class="wl-tkr">{sym}</div>
            <div class="wl-co">{r['Shares']:g} shares · avg {r['Avg Cost']}</div>
          </div>
          <div class="wl-right">
            <div class="wl-price">{r['Current']}</div>
            <div class="wl-chg {cls}">{r['P&L']}</div>
          </div>
        </div>""")
    st.markdown(
        f'<div class="card" style="padding:6px">{"<div class=\'wl-sep\'></div>".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Position detail (targets, stops, risk/reward)"):
        df_display = pd.DataFrame(rows).drop(columns=["_pnl"])
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    _position_editor()

    # Portfolio chart
    st.markdown("### Portfolio Value History")
    sym_pick = st.selectbox("Chart symbol", list(portfolio().keys()) + ["SPY"])
    hist = get_historical_data(sym_pick, period="3mo")
    if not hist.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist["close"],
            fill="tozeroy", fillcolor="rgba(5,232,122,0.1)",
            line=dict(color="var(--up)", width=2),
            name=sym_pick
        ))
        fig.update_layout(**design.plotly_layout(st.session_state.theme),
                       height=280)
        st.plotly_chart(fig, use_container_width=True)


# ── Analysis Tab ──────────────────────────────────────────────────────────────
def render_analysis():
    st.markdown("## 🔬 Technical Analysis")

    sym = symbol_picker("Search a stock", key="ana_sym")

    if sym:
        # 1y, not 6mo: a 200-day average needs ~200 trading days of history,
        # so a 6-month window rendered it as "$nan".
        df = get_historical_data(sym, period="1y")
        if not df.empty:
            df = calculate_all(df)
            sig = get_signal_summary(df)
            latest = df.iloc[-1]

            def val(col, default=None):
                """Latest value of a column, or None when it is missing/NaN."""
                v = latest.get(col, default)
                return None if v is None or pd.isna(v) else float(v)

            def money(v):
                return f"${v:,.2f}" if v is not None else "—"

            def vs_price(v):
                if v is None:
                    return "Not enough history"
                return "Above" if latest["close"] > v else "Below"

            # Technical indicator metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            rsi_val   = val("rsi")
            macd_val  = val("macd_hist")
            vol_val   = val("vol_ratio")

            # Standard RSI bands. The previous logic sent anything from 60–70
            # to "Oversold", so an RSI of 63 was labelled the exact opposite
            # of what it means.
            if rsi_val is None:      rsi_label = "—"
            elif rsi_val >= 70:      rsi_label = "Overbought"
            elif rsi_val <= 30:      rsi_label = "Oversold"
            elif rsi_val >= 55:      rsi_label = "Bullish lean"
            elif rsi_val <= 45:      rsi_label = "Bearish lean"
            else:                    rsi_label = "Neutral"

            with col1:
                st.metric("RSI (14)", f"{rsi_val:.1f}" if rsi_val is not None else "—",
                          rsi_label, delta_color="off")
            with col2:
                st.metric("MACD", f"{macd_val:.3f}" if macd_val is not None else "—",
                          ("Bullish" if macd_val > 0 else "Bearish") if macd_val is not None else "—",
                          delta_color="normal" if (macd_val or 0) > 0 else "inverse")
            with col3:
                st.metric("50-Day MA", money(val("ma50")), vs_price(val("ma50")), delta_color="off")
            with col4:
                st.metric("200-Day MA", money(val("ma200")), vs_price(val("ma200")), delta_color="off")
            with col5:
                st.metric("Vol Ratio", f"{vol_val:.1f}x" if vol_val is not None else "—",
                          ("Unusual" if vol_val > 2 else "Normal") if vol_val is not None else "—",
                          delta_color="off")

            # Price chart with MAs
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df["close"], name="Price", line=dict(color="var(--text)", width=2)))
            fig.add_trace(go.Scatter(x=df.index, y=df["ma20"],  name="20 MA", line=dict(color="var(--warn)", width=1, dash="dot")))
            fig.add_trace(go.Scatter(x=df.index, y=df["ma50"],  name="50 MA", line=dict(color="var(--accent)", width=1, dash="dot")))

            # Bollinger bands
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"], name="BB Upper", line=dict(color="var(--text3)", width=1, dash="dash")))
            fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"], name="BB Lower", line=dict(color="var(--text3)", width=1, dash="dash"),
                                     fill="tonexty", fillcolor="rgba(74,158,255,0.05)"))

            fig.update_layout(**design.plotly_layout(st.session_state.theme),
                       height=340)
            st.plotly_chart(fig, use_container_width=True)

            # RSI subplot
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI", line=dict(color="var(--accent)", width=2)))
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="var(--down)", annotation_text="Overbought")
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="var(--up)", annotation_text="Oversold")
            _rsi_layout = design.plotly_layout(st.session_state.theme)
            _rsi_layout["yaxis"] = {**_rsi_layout["yaxis"], "range": [0, 100]}
            fig_rsi.update_layout(**_rsi_layout, height=160)
            st.plotly_chart(fig_rsi, use_container_width=True)

            # TradingView rating alongside APEX's own signals
            tv = get_tv_rating(sym)
            if tv:
                rec   = tv["recommendation"].replace("_", " ")
                color = rating_color(tv["recommendation"])
                st.markdown(
                    f'<span style="color:var(--text2);font-family:monospace;font-size:12px">TRADINGVIEW&nbsp;&nbsp;</span>'
                    f'<span style="color:{color};font-family:monospace;font-weight:700">{rec}</span> '
                    f'<span style="color:var(--text3);font-size:11px">({tv["buy"]} buy / {tv["neutral"]} neutral / {tv["sell"]} sell · 1D)</span>',
                    unsafe_allow_html=True,
                )

            # Signal summary
            if sig:
                st.markdown(f"**Overall Signal Score: {sig['overall_score']}/100**")
                for name, s in sig["signals"].items():
                    strength = s["score"]
                    bar = "█" * strength + "░" * (5 - strength)
                    color = "var(--up)" if strength >= 4 else ("var(--warn)" if strength == 3 else "var(--down)")
                    st.markdown(f'<span style="color:var(--text2);font-family:monospace;font-size:12px">{name.upper():<12}</span> <span style="color:{color};font-family:monospace">{bar}</span> <span style="color:var(--text3);font-size:11px">{s["label"]}</span>', unsafe_allow_html=True)


# ── TradingView Tab ───────────────────────────────────────────────────────────
def render_tradingview():
    st.markdown("## 📺 TradingView")

    sym = symbol_picker("Search a stock", key="tv_sym")

    col_chart, col_gauge = st.columns([2.2, 1])
    with col_chart:
        st.iframe(tv_advanced_chart_html(sym, height=520), height=530)
    with col_gauge:
        st.iframe(tv_technical_analysis_html(sym, height=400), height=410)
        rating = get_tv_rating(sym)
        if rating:
            rec   = rating["recommendation"].replace("_", " ")
            color = rating_color(rating["recommendation"])
            st.markdown(f"""
            <div style="background:var(--surface);border:1px solid var(--border);border-top:2px solid {color};
                        border-radius:12px;padding:14px;text-align:center">
              <div style="font-family:'Space Mono',monospace;font-size:9px;color:var(--text3);letter-spacing:.15em;margin-bottom:6px">
                TRADINGVIEW RATING · 1D
              </div>
              <div style="font-family:'Space Mono',monospace;font-size:20px;font-weight:700;color:{color}">{rec}</div>
              <div style="font-size:11px;color:var(--text2);margin-top:6px">
                <span style="color:var(--up)">{rating['buy']} buy</span> ·
                <span style="color:var(--warn)">{rating['neutral']} neutral</span> ·
                <span style="color:var(--down)">{rating['sell']} sell</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # Watchlist ratings
    st.markdown("---")
    st.markdown("### 📋 Watchlist Ratings")
    if st.button("Fetch TradingView ratings for watchlist"):
        with st.spinner("Fetching ratings..."):
            st.session_state.tv_ratings = get_tv_ratings(watchlist())
    if st.session_state.get("tv_ratings"):
        rows = []
        for s, r in st.session_state.tv_ratings.items():
            if r:
                rows.append({
                    "Symbol":  s,
                    "Rating":  r["recommendation"].replace("_", " "),
                    "Buy":     r["buy"],
                    "Neutral": r["neutral"],
                    "Sell":    r["sell"],
                })
            else:
                rows.append({"Symbol": s, "Rating": "—", "Buy": "—", "Neutral": "—", "Sell": "—"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Webhook alerts
    st.markdown("---")
    st.markdown("### 🔔 TradingView Alerts (webhook)")
    tv_alerts = load_tv_alerts()
    if tv_alerts:
        col1, col2 = st.columns([5, 1])
        with col2:
            if st.button("Clear alerts"):
                clear_tv_alerts()
                st.rerun()
        st.dataframe(pd.DataFrame(tv_alerts), use_container_width=True, hide_index=True)
    else:
        st.info("No TradingView alerts received yet.")
        with st.expander("⚙️ How to set up TradingView alert webhooks"):
            st.markdown("""
1. **Start the webhook receiver** (in a second terminal):
   ```
   python tv_webhook.py
   ```
2. **Expose it publicly** — TradingView must reach it over the internet:
   ```
   ngrok http 5001
   ```
3. **Set a secret** in your `.env` so only TradingView alerts are accepted:
   ```
   TRADINGVIEW_WEBHOOK_SECRET=pick-a-random-string
   ```
4. **In TradingView** (paid plan required for webhooks): create an alert →
   check **Webhook URL** → paste
   `https://<your-ngrok-url>/webhook/tradingview?secret=<your-secret>`
5. **Alert message** — use JSON so APEX can parse it:
   ```json
   {"symbol": "{{ticker}}", "price": {{close}}, "event": "RSI oversold", "interval": "{{interval}}"}
   ```

Alerts land in `tv_alerts.json`, show up here, and are forwarded by email if email alerts are configured.
            """)


# ── Backtest Tab ──────────────────────────────────────────────────────────────
def render_backtest():
    st.markdown("## 📈 Strategy Backtester")
    st.markdown("Test the momentum strategy on historical data to see how it would have performed.")

    col1, col2, col3 = st.columns(3)
    with col1: sym      = symbol_picker("Symbol", key="bt_sym")
    with col2: capital  = st.number_input("Starting Capital ($)", value=1000, step=100)
    with col3: stop_pct = st.slider("Stop Loss %", 5, 30, 17) / 100

    with st.expander("⚙️ Entry filters"):
        col1, col2 = st.columns(2)
        with col1:
            rsi_entry = st.slider(
                "RSI entry ceiling", 40, 90, 65,
                help="Skip entries when RSI is already above this. It is an "
                     "overbought guard, not an oversold requirement — set it "
                     "too low and no trade can ever fire, because a bullish "
                     "MACD cross means RSI has already recovered.",
            )
        with col2:
            vol_min = st.slider(
                "Min volume ratio", 1.0, 3.0, 1.2, step=0.1,
                help="Volume must exceed this multiple of its 20-day average "
                     "at some point in the 3 bars up to entry.",
            )

    if st.button("▶ Run Backtest", use_container_width=True):
        with st.spinner(f"Backtesting {sym}..."):
            result = backtest_momentum_strategy(
                sym, capital, stop_pct, rsi_entry=rsi_entry, vol_ratio_min=vol_min
            )

        if "error" in result:
            st.error(result["error"])
        else:
            # Summary metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            ret_color = "normal" if result["total_return_pct"] > 0 else "inverse"
            with col1: st.metric("Total Return",  f"{result['total_return_pct']:+.1f}%")
            with col2: st.metric("Final Capital", f"${result['final_capital']:,.0f}")
            with col3: st.metric("Win Rate",       f"{result['win_rate']}%")
            with col4: st.metric("Total Trades",   result["total_trades"])
            with col5: st.metric("Max Drawdown",   f"-{result['max_drawdown_pct']}%")

            # Equity curve
            st.markdown("### Equity Curve")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=result["equity_curve"],
                fill="tozeroy",
                fillcolor="rgba(5,232,122,0.08)",
                line=dict(color="var(--up)", width=2),
                name="Portfolio Value"
            ))
            fig.add_hline(y=capital, line_dash="dash", line_color="var(--text3)", annotation_text="Starting Capital")
            fig.update_layout(**design.plotly_layout(st.session_state.theme),
                       height=300)
            st.plotly_chart(fig, use_container_width=True)

            # Trade log
            if result["trades"]:
                st.markdown("### Trade Log")
                trades_df = pd.DataFrame(result["trades"])
                trades_df = trades_df.drop(columns=["symbol", "win"])
                trades_df.columns = ["Entry Date", "Exit Date", "Entry $", "Exit $", "Shares", "P&L $", "P&L %", "Exit Reason"]
                st.dataframe(trades_df, use_container_width=True, hide_index=True)


# ── ML Predictions Tab ────────────────────────────────────────────────────────
def render_ml():
    st.markdown("## 🤖 ML Price Predictions")
    st.markdown("Machine learning model trained on technical indicators to predict 10-day price direction.")

    sym = symbol_picker("Symbol to predict", key="ml_sym")

    if st.button("🧠 Run Prediction", use_container_width=True):
        with st.spinner(f"Training model on {sym} historical data..."):
            result = predict_direction(sym)

        if "error" in result:
            st.error(result["error"])
        else:
            direction = result["direction"]
            conf      = result["confidence"]
            acc       = result["model_accuracy"]
            base      = result.get("baseline_accuracy")
            # A model that cannot beat "always guess the majority class" has
            # no demonstrated skill. Saying so up front matters more than the
            # headline number: accuracy alone looks respectable either way.
            has_skill = base is not None and acc > base
            edge      = (acc - base) if base is not None else None

            if not has_skill:
                st.error(
                    f"**No demonstrated skill on {sym}.** Walk-forward accuracy "
                    f"{acc}% is {abs(edge):.1f} points *below* the "
                    f"{base}% you would get by always guessing the majority class. "
                    "Treat the direction below as unreliable for this symbol."
                )

            dir_color = "var(--up)" if direction == "BULLISH" else "var(--down)"

            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Direction", direction.title())
            with col2: st.metric("Class probability", f"{conf}%",
                                 help="How confident the classifier is in its own label. "
                                      "This is NOT a measure of model skill.")
            with col3: st.metric("Walk-forward accuracy", f"{acc}%")
            with col4: st.metric("Majority baseline",
                                 f"{base}%" if base is not None else "—",
                                 f"{edge:+.1f} pts" if edge is not None else None,
                                 delta_color="normal" if has_skill else "inverse",
                                 help="Accuracy of always predicting the more common outcome. "
                                      "The model must beat this to be useful.")

            st.markdown(f"""
            <div class="card" style="margin-top:16px">
              <div style="font-size:20px;font-weight:660;color:{dir_color if has_skill else 'var(--text2)'};
                          margin-bottom:8px">{sym} — {direction.title()}</div>
              <div style="color:var(--text2);font-size:14px;margin-bottom:12px">{result['note']}</div>
              <div style="color:var(--text3);font-size:12.5px">
                Top predictive factors: {', '.join(result['top_factors'])}
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.caption(
                "Validation uses expanding-window walk-forward splits with a "
                f"{result.get('horizon', '10 days')} embargo, so no training label "
                "depends on a price inside its own test window. Past performance "
                "does not guarantee future results. Not financial advice."
            )


# ── Trade Journal Tab ─────────────────────────────────────────────────────────
def render_journal():
    st.markdown("## 📓 Trade Journal")

    # Add trade form
    with st.expander("➕ Log a Trade"):
        col1, col2, col3 = st.columns(3)
        with col1:
            j_sym    = st.text_input("Symbol", key="j_sym").upper()
            j_entry  = st.number_input("Entry Price", key="j_entry", min_value=0.0, step=0.01)
            j_shares = st.number_input("Shares", key="j_shares", min_value=1)
        with col2:
            j_exit   = st.number_input("Exit Price", key="j_exit", min_value=0.0, step=0.01)
            j_date   = st.date_input("Trade Date", key="j_date")
            j_strat  = st.selectbox("Strategy", ["Momentum", "Short Squeeze", "Earnings", "Breakout", "Mean Reversion"])
        with col3:
            j_note   = st.text_area("Notes / Lessons", key="j_note", height=120)

        if st.button("Save Trade", type="primary"):
            if not j_sym:
                st.error("Pick a stock.")
            elif j_entry <= 0 or j_exit <= 0:
                st.error("Entry and exit prices must both be greater than zero.")
            elif j_shares <= 0:
                st.error("Shares must be greater than zero.")
            else:
                pnl     = (j_exit - j_entry) * j_shares
                pnl_pct = ((j_exit - j_entry) / j_entry) * 100
                db.add_journal_entry(uid(), {
                    "date":     str(j_date),
                    "symbol":   j_sym,
                    "strategy": j_strat,
                    "entry":    j_entry,
                    "exit":     j_exit,
                    "shares":   j_shares,
                    "pnl":      round(pnl, 2),
                    "pnl_pct":  round(pnl_pct, 1),
                    "note":     j_note,
                })
                st.success(f"Trade logged: {j_sym} {'WIN' if pnl > 0 else 'LOSS'} ${pnl:+.2f}")
                st.rerun()

    # Journal entries — persisted per user, so they survive a refresh
    entries = journal()
    if entries:
        stats = db.journal_stats(uid())
        pnl_cls = "up" if stats["total_pnl"] >= 0 else "down"
        st.markdown(f"""
        <div class="stats">
          <div class="stat"><div class="stat-label">Trades</div>
            <div class="stat-value">{stats['trades']}</div></div>
          <div class="stat"><div class="stat-label">Win rate</div>
            <div class="stat-value">{stats['win_rate']:.0f}%</div>
            <div class="stat-sub">{stats['wins']} won · {stats['losses']} lost</div></div>
          <div class="stat"><div class="stat-label">Realised P&amp;L</div>
            <div class="stat-value {pnl_cls}">{stats['total_pnl']:+,.2f}</div></div>
        </div>
        """, unsafe_allow_html=True)

        df_j = pd.DataFrame(entries).drop(columns=["win"])
        df_j.columns = ["Date", "Symbol", "Strategy", "Entry $", "Exit $", "Shares",
                        "P&L $", "P&L %", "Notes"]
        st.dataframe(df_j, use_container_width=True, hide_index=True)
    else:
        st.info("No trades logged yet. Add your first trade above.")


# ── Chat Tab ──────────────────────────────────────────────────────────────────
def render_chat():
    st.markdown("## 💬 APEX Assistant")

    # Display chat history
    for msg in st.session_state.chat_messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-msg-user">👤 {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            parsed = msg.get("parsed", {})
            text   = parsed.get("text", msg["content"]).replace("\n", "<br>")
            st.markdown(f'<div class="chat-msg-bot">🤖 {text}</div>', unsafe_allow_html=True)

            # Render card if present
            card = parsed.get("card")
            if card:
                render_chat_card(card)

    # Quick prompts
    suggestions = []
    if st.session_state.chat_messages:
        last = st.session_state.chat_messages[-1]
        if last["role"] == "assistant":
            suggestions = last.get("parsed", {}).get("suggestions", [])

    if not suggestions:
        suggestions = ["Analyze NVDA", "How's the market?", "What is RSI?", "Scan for picks"]

    cols = st.columns(len(suggestions))
    for i, sug in enumerate(suggestions):
        with cols[i]:
            if st.button(sug, key=f"sug_{i}_{sug}"):
                process_chat_message(sug)
                st.rerun()

    # Input
    user_input = st.chat_input("Ask anything about markets, strategies, positions...")
    if user_input:
        process_chat_message(user_input)
        st.rerun()


def process_chat_message(message: str):
    """Process a chat message and get AI response."""
    # Check for emotional language
    if get_emotion_warning(message):
        parsed = {
            "text": "🧘 I'm noticing some pressure in your message. Emotional trading is one of the top causes of losses.\n\nLet's take a breath and look at this clearly before making any moves. Want to review your journal first?",
            "card": None,
            "suggestions": ["Show my journal", "Review positions", "Take a break", "Market overview"],
        }
        st.session_state.chat_messages.append({"role": "user", "content": message})
        st.session_state.chat_history.append({"role": "user", "content": message})
        st.session_state.chat_messages.append(
            {"role": "assistant", "content": parsed.get("text", ""), "parsed": parsed}
        )
        st.session_state.chat_history.append({"role": "assistant", "content": json.dumps(parsed)})
        return

    # Add user message
    st.session_state.chat_messages.append({"role": "user", "content": message})
    st.session_state.chat_history.append({"role": "user", "content": message})

    # Get AI response
    response = chat(message, st.session_state.chat_history, st.session_state.live_quotes,
                    portfolio=portfolio())

    # Store assistant message
    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": response.get("text", ""),
        "parsed": response,
    })
    st.session_state.chat_history.append({
        "role": "assistant",
        "content": json.dumps(response),
    })


def render_chat_card(card: dict):
    """Render a rich card from the AI response."""
    if card["type"] == "stock":
        dir_color = "var(--up)" if card.get("direction") == "up" else "var(--down)"
        conf      = card.get("confidence", 0)
        lvl       = card.get("confidenceLevel", "medium")
        conf_color = "var(--up)" if lvl == "high" else "var(--warn)"

        bull_points = "".join([f'<div style="margin-bottom:3px;font-size:11px;color:var(--text2)">→ {b}</div>' for b in card.get("bull", [])])
        bear_points = "".join([f'<div style="margin-bottom:3px;font-size:11px;color:var(--text2)">→ {b}</div>' for b in card.get("bear", [])])
        sig_rows    = ""
        for sig in card.get("signals", []):
            dots = "".join([f'<div style="width:6px;height:6px;border-radius:50%;background:{"var(--up)" if i <= sig["strength"] else "var(--border)"};display:inline-block;margin-right:2px"></div>' for i in range(1, 6)])
            sig_rows += f'<div style="display:flex;align-items:center;gap:8px;font-size:10px;color:var(--text2);margin-bottom:3px"><span style="flex:1">{sig["label"]}</span><div>{dots}</div></div>'

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,var(--surface),var(--surface2));border:1px solid var(--border);
                    border-top:2px solid {dir_color};border-radius:12px;padding:14px;margin:8px 0">
          <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <div>
              <div style="font-family:'Space Mono',monospace;font-size:16px;font-weight:700">{card['sym']}</div>
              <div style="font-size:10px;color:var(--text2)">{card.get('name','')}</div>
            </div>
            <div style="text-align:right">
              <div style="font-family:'Space Mono',monospace;font-size:14px;font-weight:700">{card.get('price','')}</div>
              <div style="font-family:'Space Mono',monospace;font-size:10px;color:{dir_color}">{card.get('change','')}</div>
            </div>
          </div>
          <div style="background:var(--border);height:4px;border-radius:3px;margin-bottom:8px;overflow:hidden">
            <div style="background:linear-gradient(90deg,var(--up),var(--up));height:100%;width:{conf}%;border-radius:3px"></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span style="font-family:'Space Mono',monospace;font-size:9px;color:var(--text3)">CONFIDENCE</span>
            <span style="font-family:'Space Mono',monospace;font-size:11px;font-weight:700;color:{conf_color}">{conf}/100</span>
          </div>
          <div style="font-family:'Space Mono',monospace;font-size:18px;font-weight:700;color:var(--up);margin:4px 0 2px">{card.get('move','')}</div>
          <div style="font-size:10px;color:var(--text2);margin-bottom:8px">Est. move · {card.get('horizon','')}</div>
          <div style="margin-bottom:10px">{sig_rows}</div>
          <div style="display:flex;gap:6px;margin-bottom:10px">
            <div style="flex:1;text-align:center;background:rgba(74,158,255,0.08);border:1px solid rgba(74,158,255,0.2);border-radius:7px;padding:7px">
              <div style="font-size:7px;color:var(--text3);font-family:monospace;letter-spacing:.1em;margin-bottom:3px">ENTRY</div>
              <div style="font-family:monospace;font-size:11px;font-weight:700;color:var(--accent)">{card.get('entry','')}</div>
            </div>
            <div style="flex:1;text-align:center;background:rgba(5,232,122,0.08);border:1px solid rgba(5,232,122,0.2);border-radius:7px;padding:7px">
              <div style="font-size:7px;color:var(--text3);font-family:monospace;letter-spacing:.1em;margin-bottom:3px">TARGET</div>
              <div style="font-family:monospace;font-size:11px;font-weight:700;color:var(--up)">{card.get('target','')}</div>
            </div>
            <div style="flex:1;text-align:center;background:rgba(255,67,101,0.08);border:1px solid rgba(255,67,101,0.2);border-radius:7px;padding:7px">
              <div style="font-size:7px;color:var(--text3);font-family:monospace;letter-spacing:.1em;margin-bottom:3px">STOP</div>
              <div style="font-family:monospace;font-size:11px;font-weight:700;color:var(--down)">{card.get('stop','')}</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
            <div style="background:rgba(5,232,122,0.04);border:1px solid rgba(5,232,122,0.12);border-radius:6px;padding:8px">
              <div style="font-family:'Space Mono',monospace;font-size:8px;color:var(--up);margin-bottom:4px">🐂 BULL</div>
              {bull_points}
            </div>
            <div style="background:rgba(255,67,101,0.04);border:1px solid rgba(255,67,101,0.12);border-radius:6px;padding:8px">
              <div style="font-family:'Space Mono',monospace;font-size:8px;color:var(--down);margin-bottom:4px">🐻 BEAR</div>
              {bear_points}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    elif card["type"] == "market":
        rows_html = ""
        for row in card.get("rows", []):
            color = "var(--up)" if row.get("up") else "var(--down)"
            rows_html += f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(26,42,58,0.5);font-size:11px"><span style="font-family:monospace;font-weight:700">{row["sym"]}</span><span style="color:var(--text2);font-family:monospace">{row["val"]}</span><span style="color:{color};font-family:monospace">{row["chg"]}</span></div>'
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,var(--surface),var(--surface2));border:1px solid var(--border);border-radius:12px;padding:14px;margin:8px 0;max-width:300px">
          <div style="font-family:'Space Mono',monospace;font-size:9px;color:var(--text3);letter-spacing:.15em;margin-bottom:10px">📡 MARKET PULSE · {card.get('condition','')}</div>
          {rows_html}
        </div>
        """, unsafe_allow_html=True)

    elif card["type"] == "concept":
        example_html = f'<div style="margin-top:8px;padding:8px 10px;background:rgba(74,158,255,0.07);border-radius:6px;font-family:monospace;font-size:10px;color:var(--accent);line-height:1.6">{card.get("example","").replace(chr(10),"<br>")}</div>' if card.get("example") else ""
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,rgba(74,158,255,0.05),rgba(176,106,255,0.05));border:1px solid rgba(74,158,255,0.18);border-radius:12px;padding:14px;margin:8px 0">
          <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px">{card.get('emoji','')} {card.get('title','')}</div>
          <div style="font-size:11px;color:var(--text2);line-height:1.5">{card.get('body','')}</div>
          {example_html}
        </div>
        """, unsafe_allow_html=True)


# ── Main App ──────────────────────────────────────────────────────────────────
def main():
    # Auth gate: everything past this point belongs to a signed-in user.
    if not st.session_state.get("user_id"):
        login_ui.render_login()
        return

    render_ticker_tape()
    render_sidebar()

    # Main navigation tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Overview",
        "Analysis",
        "Charts",
        "Backtest",
        "Forecast",
        "Journal",
        "Assistant",
    ])

    with tab1: render_dashboard()
    with tab2: render_analysis()
    with tab3: render_tradingview()
    with tab4: render_backtest()
    with tab5: render_ml()
    with tab6: render_journal()
    with tab7: render_chat()


if __name__ == "__main__":
    main()
