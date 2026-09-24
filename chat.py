# ─────────────────────────────────────────────
#  chat.py — Claude AI Chat + offline fallback
# ─────────────────────────────────────────────

import json
import re

from config import ANTHROPIC_API_KEY, SCAN_UNIVERSE

_anthropic_client = None

SYSTEM_PROMPT = """You are APEX, an elite trading intelligence assistant for intermediate stock traders.
Personality: Confident, sharp, data-driven but approachable — like a seasoned Wall Street analyst who is also a great teacher.

CRITICAL — Respond ONLY in valid JSON:
{
  "text": "conversational message with \\n for line breaks",
  "card": null | { card object },
  "suggestions": ["follow-up 1", "follow-up 2", "follow-up 3", "follow-up 4"]
}

Card types:
1. STOCK — for any stock analysis:
{"type":"stock","sym":"NVDA","name":"NVIDIA Corporation","price":"$921","change":"+3.4%","direction":"up","confidence":87,"confidenceLevel":"high","move":"+14-22%","horizon":"7-10 days","signals":[{"label":"News Catalyst","strength":5},{"label":"Options Activity","strength":4},{"label":"Technical Setup","strength":5},{"label":"Short Interest","strength":2},{"label":"Sentiment","strength":4}],"entry":"$921","target":"$1050","stop":"$870","bull":["reason1","reason2","reason3"],"bear":["risk1","risk2","risk3"]}

2. MARKET — for market/macro questions:
{"type":"market","condition":"BULLISH","rows":[{"sym":"SPY","val":"558","chg":"+1.2%","up":true},{"sym":"QQQ","val":"472","chg":"+1.8%","up":true},{"sym":"VIX","val":"14.3","chg":"LOW FEAR","up":false}]}

3. CONCEPT — for education/strategy questions:
{"type":"concept","emoji":"📊","title":"RSI Explained","body":"Plain English explanation with analogy","example":"Practical example with numbers"}

Rules:
- Always show BOTH bull and bear case for any stock recommendation
- Watch for emotional language (need to make this back, going all in, can't keep dropping) — respond with empathy, no card, gently redirect
- Use live prices from context when provided
- Always include entry, target, stop loss on every stock recommendation
- Return null card for casual chat, greetings, or simple questions
- Suggestions should be natural contextual follow-ups, max 4 words each
- ALWAYS return valid JSON — never plain text outside JSON
"""


KNOWN_SYMBOLS = (
    set(SCAN_UNIVERSE)
    | {"SPY", "QQQ", "VIX", "IWM", "DIA"}
)


def _get_anthropic_client():
    global _anthropic_client
    if not ANTHROPIC_API_KEY:
        return None
    if _anthropic_client is None:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _extract_symbols(message: str) -> list[str]:
    found = re.findall(r"\b[A-Z]{1,5}\b", message.upper())
    ordered: list[str] = []
    for s in found:
        if s in KNOWN_SYMBOLS and s not in ordered:
            ordered.append(s)
    return ordered[:3]


def _wants_market_overview(message: str) -> bool:
    m = message.lower()
    keys = (
        "market",
        "indices",
        "macro",
        "how's the",
        "hows the",
        "how is the",
        "economy",
        "sentiment",
        "breadth",
        "risk on",
        "risk-off",
        "risk off",
        "overall tape",
        "tape look",
        "everything doing",
        "what's moving",
        "whats moving",
        "vix",
    )
    if any(k in m for k in keys):
        return True
    # "spy" alone often means indices in casual chat
    if re.search(r"\bspy\b", m) and "chart" not in m and len(m) < 80:
        return True
    return False


def _concept_reply(message: str) -> dict | None:
    m = message.lower()
    if "rsi" in m or "relative strength" in m:
        return {
            "text": (
                "**RSI** measures how aggressively a stock has rallied or sold off over "
                "the past ~14 sessions.\n\n"
                "Rough guide: Below 30 is often oversold (bounce risk higher). "
                "Above 70 is often overbought (pullback risk higher). RSI is NOT a timing "
                "button—use it with trend and volume."
            ),
            "card": {
                "type": "concept",
                "emoji": "📊",
                "title": "RSI Explained",
                "body": (
                    "RSI is like a speedometer for price momentum—not whether the "
                    "'speed' is sensible, just how stretched it currently is versus "
                    "recent history."
                ),
                "example": (
                    "If a stock RSI is ~25 after a cliff drop, bounce setups get more plausible "
                    "(still need a plan: entry / stop / target)."
                ),
            },
            "suggestions": ["Analyze NVDA", "What's MACD?", "How's the market?", "Show SPY pulse"],
        }
    if "macd" in m:
        return {
            "text": (
                "**MACD** tracks the relationship between two moving averages of price and "
                "a histogram of their difference.\n\n"
                "A common shorthand: histogram rising while positive suggests bullish momentum "
                "building; falling while negative suggests bearish pressure."
            ),
            "card": {
                "type": "concept",
                "emoji": "📈",
                "title": "MACD in one minute",
                "body": (
                    "MACD is a trend + momentum gauge. It reacts slower than RSI, "
                    "so many traders combine them."
                ),
                "example": (
                    "Price above key MAs + MACD histogram improving from negative territory "
                    "is a frequent 'reset' storyline—still validate with volatility and stops."
                ),
            },
            "suggestions": ["What is RSI?", "Analyze SOFI", "How's QQQ?", "Risk management basics"],
        }
    if "stop" in m and ("loss" in m or "risk" in m):
        return {
            "text": (
                "**Stop placement** should answer: 'Where is my thesis wrong?'\n\n"
                "Stops anchored only to arbitrary % rarely survive real volatility regimes. "
                "Consider structure (swing lows/highs), ATR multiples, or max acceptable loss "
                "as a fraction of equity."
            ),
            "card": {
                "type": "concept",
                "emoji": "🛑",
                "title": "Stop losses (actually useful framing)",
                "body": (
                    "A stop is insurance against being wrong—not a prediction that you will lose."
                ),
                "example": (
                    "Long swing trade: invalidation below the prior higher low zone, sized so "
                    "a hit loses ≤1% of account (example rule of thumb—not advice)."
                ),
            },
            "suggestions": ["Position sizing?", "Analyze PLTR", "Backtest NVDA", "Journal my trade"],
        }
    return None


def _market_card_from_quotes(live_prices: dict) -> dict:
    rows = []
    condition = "MIXED"
    spy = live_prices.get("SPY")
    if spy:
        condition = "BULLISH" if spy["pct_change"] >= 0 else "BEARISH"

    def row(sym: str):
        q = live_prices.get(sym)
        if not q:
            return None
        chg_txt = (
            "LOW FEAR"
            if sym == "VIX" and q["price"] < 20
            else (f"{q['pct_change']:+.2f}%")
        )
        return {
            "sym": sym,
            "val": f"{q['price']}",
            "chg": chg_txt,
            "up": q["pct_change"] >= 0,
        }

    for sym in ("SPY", "QQQ", "VIX"):
        r = row(sym)
        if r:
            rows.append(r)

    if not rows:
        return {
            "text": (
                "I'd show a live market pulse card, but I don't have refreshed quotes yet. "
                "Open the Dashboard tab briefly or wait for the banner to populate, then ask again."
            ),
            "card": None,
            "suggestions": ["Refresh dashboard", "Analyze NVDA", "Explain RSI", "Backtest SPY"],
        }

    headline = (
        f"Breadth leans {'positive' if condition == 'BULLISH' else 'negative'} off SPY tape."
        if condition != "MIXED"
        else "Tape mixed—check majors and volatility."
    )
    return {
        "text": f"Quick pulse: {headline}\n\n(Offline assistant — powered by live quote context.)",
        "card": {"type": "market", "condition": condition, "rows": rows},
        "suggestions": ["Analyze NVDA", "Scan opportunities", "What is RSI?", "Portfolio risks"],
    }


def _signals_to_card_signals(signals: dict) -> list[dict]:
    order = (
        ("volume", "Volume"),
        ("rsi", "RSI"),
        ("macd", "MACD"),
        ("ma", "Trend"),
        ("bb", "Bollinger"),
    )
    out: list[dict] = []
    for key, label in order:
        if key not in signals:
            continue
        out.append({"label": label, "strength": int(signals[key].get("score", 3))})
    while len(out) < 5:
        out.append({"label": "Setup quality", "strength": 3})
    return out[:5]


def _offline_stock(symbol: str, live_prices: dict | None) -> dict:
    from scanner import score_opportunity

    opp = score_opportunity(symbol)
    if not opp:
        # Quote-only consolation
        quote = live_prices.get(symbol) if live_prices else None
        if quote:
            pc = quote["pct_change"]
            txt = (
                f"I pulled a live quote for **{symbol}** (${quote['price']:.2f}, "
                f"{pc:+.2f}%), but fuller technical scoring needs recent history "
                f"right now.\n\nTry again in a moment or verify the ticker."
            )
        else:
            txt = (
                f"I couldn't fetch enough reliable data for **{symbol}** just yet "
                "(check the symbol spelling / market hours)."
            )
        return {
            "text": txt,
            "card": None,
            "suggestions": ["Try NVDA", "How's the market?", "What is RSI?", "Open Analysis tab"],
        }

    price = opp["price"]
    pc = opp["pct_change"]
    direction = "up" if pc >= 0 else "down"
    conf = max(42, min(92, int(opp["score"])))
    lvl = "high" if conf >= 72 else ("medium" if conf >= 58 else "low")
    rsi = opp.get("rsi")
    macdh = opp.get("macd_hist")
    bull: list[str] = []
    bear: list[str] = []

    bull.append(f"Scanner score **{opp['score']}/100** ({opp['confidence']}).")
    if rsi is not None:
        if rsi < 35:
            bull.append(f"RSI ~{rsi} leans oversold (bounce setups get more plausible—still need a clear plan).")
            bear.append("Oversold can stay oversold; wait for confirmation or honor a tight thesis.")
        elif rsi > 70:
            bull.append(f"RSI ~{rsi} reflects strong momentum—but extension raises pullback risk.")
            bear.append(f"RSI ~{rsi} is stretched; stalls and mean-reversion become more likely.")
        else:
            bull.append(f"RSI ~{rsi} is mid-range (context from trend/volume matters more here).")

    if macdh is not None:
        if macdh >= 0:
            bull.append(f"MACD histogram positive (~{macdh:+.4f}).")
        else:
            bear.append(f"MACD histogram negative (~{macdh:+.4f})—upside may need time to repair.")

    bull.append(f"Tags: {', '.join(opp.get('tags', [])[:3]) or '—'}")
    bear.append(f"Liquidity/events can overwhelm technicals.")
    bear.append(f"Honor your stop near **${opp['stop']:.2f}** if you trade this idea.")

    chg_txt = f"+{pc}%" if pc >= 0 else f"{pc}%"
    txt = (
        f"Here's a **offline** structured read on **{symbol}** (no Claude API).\n\n"
        f"It's built from price + TA already in your app—not discretionary narrative.\n\n"
        f"Direction lean: {'bullish tilt' if opp['score'] >= 58 else 'cautious / mixed'}."
    )

    return {
        "text": txt,
        "card": {
            "type": "stock",
            "sym": symbol,
            "name": opp["name"],
            "price": f"${price:.2f}",
            "change": chg_txt,
            "direction": direction,
            "confidence": conf,
            "confidenceLevel": lvl,
            "move": str(opp.get("est_move", "+8–16%")),
            "horizon": str(opp.get("horizon", "7–14 days")),
            "signals": _signals_to_card_signals(opp.get("signals") or {}),
            "entry": f"${opp['entry']:.2f}",
            "target": f"${opp['target']:.2f}",
            "stop": f"${opp['stop']:.2f}",
            "bull": bull[:3],
            "bear": bear[:3],
        },
        "suggestions": ["How's QQQ?", "Explain RSI", "Backtest NVDA", "Portfolio check"],
    }


def _offline_chat(message: str, history: list, live_prices: dict | None) -> dict:
    live_prices = live_prices or {}

    syms = _extract_symbols(message)

    concept = _concept_reply(message)
    if concept:
        return concept

    low_msg = message.lower()
    if ("scan for" in low_msg) or ("scan market" in low_msg) or (low_msg.strip() in {"scan", "scanner"}):
        return {
            "text": (
                "Run **⚡ SCAN MARKET** in the sidebar for a full sweep.\n\n"
                "Offline chat won't silently hammer every symbol (rate limits + time), "
                "but Dashboard cards populate right after you start a scan."
            ),
            "card": None,
            "suggestions": ["How's SPY?", "Analyze NVDA", "Explain RSI", "Open Dashboard"],
        }

    if _wants_market_overview(message):
        return _market_card_from_quotes(live_prices)

    if syms:
        primary = syms[0]
        return _offline_stock(primary, live_prices)

    return {
        "text": (
            "I'm in **offline assistant mode** (no `ANTHROPIC_API_KEY` in your `.env`).\n\n"
            "Ask me:\n"
            "- `Analyze NVDA` (I'll build a structured card using your app's scanner/TAs)\n"
            "- `How's the market?` (pulse card from live banner quotes)\n"
            "- education questions (`What is RSI?`, `MACD?`, `stop loss`)\n\n"
            "Add an Anthropic key to `.env` any time if you want full Claude prose + reasoning."
        ),
        "card": None,
        "suggestions": ["Analyze NVDA", "How's the market?", "What is RSI?", "Scan for picks"],
    }


def get_emotion_warning(message: str) -> bool:
    """Detect emotional trading language in user message."""
    emotional_patterns = [
        "need to make this back",
        "make it back",
        "recover my losses",
        "can't keep dropping",
        "can't keep dropping",
        "going all in",
        "all in",
        "double down",
        "i lost everything",
        "i'm down bad",
        "need to recoup",
        "revenge trade",
    ]
    msg_lower = message.lower()
    return any(p in msg_lower for p in emotional_patterns)


def chat(message: str, history: list, live_prices: dict = None,
         portfolio: dict = None) -> dict:
    """
    Send a message to Claude (if configured) or use offline TA-backed replies.
    history: list of {"role": "user/assistant", "content": "..."}
    live_prices: dict of {symbol: quote} to inject as context
    portfolio: the signed-in user's own {symbol: {shares, avg_cost}}; passed in
        rather than imported so one person's holdings never leak into another
        user's conversation
    Returns parsed dict with text, card, suggestions.
    """
    client = _get_anthropic_client()

    # Inject live prices into message context
    if live_prices:
        price_context = ", ".join(
            [
                f"{sym}: ${q['price']} ({'+' if q['pct_change'] >= 0 else ''}{q['pct_change']}%)"
                for sym, q in live_prices.items()
            ]
        )
        enriched_message = f"{message}\n\n[Live market prices: {price_context}]"
    else:
        enriched_message = message

    # Add portfolio context (empty when the user holds nothing)
    portfolio_context = ", ".join(
        f"{sym} ({pos['shares']} shares @ ${pos['avg_cost']})"
        for sym, pos in (portfolio or {}).items()
    ) or "no positions held"

    messages = history.copy()
    messages.append(
        {"role": "user", "content": f"{enriched_message}\n\n[Portfolio: {portfolio_context}]"}
    )

    if not client:
        return _offline_chat(message, history, live_prices)

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text

        # Parse JSON response
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = json.loads(clean.strip())
        except json.JSONDecodeError:
            parsed = {"text": raw, "card": None, "suggestions": []}

        return parsed

    except Exception as e:
        fb = _offline_chat(message, history, live_prices)
        fb["text"] = f"**(Claude unavailable)** {e}\n\n{fb['text']}"
        return fb
