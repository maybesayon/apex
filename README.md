# ⚡ APEX — Trading Intelligence (Python Edition)

A professional-grade trading assistant built with Python + Streamlit.

---

## 🚀 Setup (5 minutes)

### Step 1 — Install Python
Make sure you have Python 3.10+ installed.
Download from: https://python.org

### Step 2 — Install dependencies
Open a terminal in this folder and run:
```
pip install -r requirements.txt
```

### Step 3 — Add your API keys (optional)
Copy the example env file and edit it:
```
cp .env.example .env
```

- `FINNHUB_API_KEY` — optional; if unset, live quotes fall back to **yfinance** (no Finnhub signup required).
- `ANTHROPIC_API_KEY` — optional; if unset, **Chat** uses an offline assistant (scanner + indicators + your live quote context). Add a key later for full Claude replies.

### Step 4 — Run APEX
```
streamlit run app.py
```

Your browser will open automatically at http://localhost:8501

---

## 📁 File Structure

```
apex/
├── app.py              ← Main Streamlit app (run this)
├── config.py           ← API keys, portfolio, settings
├── prices.py           ← Live prices via Finnhub + yfinance
├── indicators.py       ← Technical analysis (RSI, MACD, MAs, etc.)
├── scanner.py          ← Opportunity scanner
├── backtest.py         ← Strategy backtesting engine
├── ml_predictions.py   ← ML price direction predictions
├── chat.py             ← Claude AI chat integration
├── alerts.py           ← Email alert system
├── tradingview.py      ← TradingView widgets, ratings, alert storage
├── tv_webhook.py       ← TradingView alert webhook receiver (run separately)
└── requirements.txt    ← Python dependencies
```

---

## 📺 TradingView Integration

APEX integrates with TradingView three ways:

**1. Embedded charts (free, works out of the box)**
The **📺 TradingView** tab embeds the full interactive TradingView chart,
technical-analysis gauge, and a watchlist ticker tape. No account needed.

**2. Technical ratings (free, unofficial)**
TradingView's Buy/Sell/Neutral ratings appear in the Analysis tab, the
TradingView tab, and as scanner tags (e.g. `TV Strong Buy`). Uses the
unofficial `tradingview-ta` library — display only, and may occasionally
break if TradingView changes their internals.

**3. Alert webhooks (requires a paid TradingView plan)**
Receive your TradingView alerts inside APEX (and by email, if configured):

```
# Terminal 1 — the app
streamlit run app.py

# Terminal 2 — the webhook receiver
python tv_webhook.py

# Terminal 3 — expose it to the internet
ngrok http 5001
```

Add a secret to your `.env`:
```
TRADINGVIEW_WEBHOOK_SECRET=pick-a-random-string
```

In TradingView, create an alert with **Webhook URL** set to
`https://<your-ngrok-url>/webhook/tradingview?secret=<your-secret>`
and this alert message:
```json
{"symbol": "{{ticker}}", "price": {{close}}, "event": "RSI oversold", "interval": "{{interval}}"}
```

Alerts are stored in `tv_alerts.json` and shown in the 📺 TradingView tab.

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| 📊 Dashboard | Live opportunity cards with confidence scores, entry/target/stop |
| 🔬 Analysis | Full technical analysis — RSI, MACD, Bollinger Bands, MAs |
| 📈 Backtest | Test momentum strategy on 2 years of historical data |
| 🤖 ML Predict | Gradient Boosting model predicts 10-day price direction |
| 📓 Journal | Log and track every trade, see patterns in your behavior |
| 💬 Chat | Full AI trading assistant with graphical stock cards |
| 🔔 Alerts | Email alerts for high-confidence opportunities |
| 💰 Portfolio | Live P&L tracking with real Finnhub prices |

---

## ⚙️ Customization

**Add stocks to your watchlist** — edit `WATCHLIST` in `config.py`

**Change portfolio positions** — edit `PORTFOLIO` in `config.py`

**Set up email alerts** — add Gmail credentials to `config.py`:
```python
ALERT_EMAIL_FROM = "youremail@gmail.com"
ALERT_EMAIL_TO   = "youremail@gmail.com"
ALERT_EMAIL_PASS = "your_app_password"  # Gmail app password
```
Note: Use Gmail App Password, not your regular password.
Create one at: https://myaccount.google.com/apppasswords

---

## ⚠️ Disclaimer

This tool is for educational purposes only.
Not financial advice. Always do your own research before investing.
Past performance does not guarantee future results.
