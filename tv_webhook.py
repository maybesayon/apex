# ─────────────────────────────────────────────
#  tv_webhook.py — TradingView Alert Webhook Receiver
#  Run alongside the Streamlit app:
#      python tv_webhook.py
#
#  Then point TradingView alerts (paid plan required) at:
#      https://<your-public-url>/webhook/tradingview?secret=<TV_WEBHOOK_SECRET>
#
#  For local testing, expose the port with e.g.:
#      ngrok http 5001
#
#  Recommended alert message body (TradingView alert dialog):
#  {"symbol": "{{ticker}}", "price": {{close}}, "event": "Your alert name", "interval": "{{interval}}"}
# ─────────────────────────────────────────────

from flask import Flask, jsonify, request

from alerts import send_email_alert
from config import TV_WEBHOOK_PORT, TV_WEBHOOK_SECRET
from tradingview import save_tv_alert

app = Flask(__name__)


@app.post("/webhook/tradingview")
def tradingview_webhook():
    payload = request.get_json(silent=True)
    if payload is None:
        # TradingView sends plain text unless the alert message is valid JSON
        payload = {"message": request.get_data(as_text=True).strip()}

    # Secret via ?secret= query param or a "secret" field in the JSON payload
    if TV_WEBHOOK_SECRET:
        provided = request.args.get("secret") or payload.pop("secret", None)
        if provided != TV_WEBHOOK_SECRET:
            return jsonify({"error": "invalid secret"}), 403

    save_tv_alert(payload)

    # Forward by email if email alerts are configured (no-op otherwise)
    symbol = payload.get("symbol", "?")
    event = payload.get("event") or payload.get("message", "TradingView alert")
    body = "\n".join(f"{k}: {v}" for k, v in payload.items())
    send_email_alert(f"📺 TradingView Alert: {symbol} — {event}", body)

    return jsonify({"status": "ok"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print(f"APEX TradingView webhook listening on port {TV_WEBHOOK_PORT}")
    if not TV_WEBHOOK_SECRET:
        print("WARNING: TRADINGVIEW_WEBHOOK_SECRET not set — webhook is unauthenticated.")
    app.run(host="0.0.0.0", port=TV_WEBHOOK_PORT)
