# ─────────────────────────────────────────────
#  tv_webhook.py — DEPRECATED
#
#  This standalone Flask service has been folded into the FastAPI app.
#  The endpoint now lives at:
#
#      POST /webhooks/tradingview        (api/routers/webhooks.py)
#
#  Running one service instead of two means one process to deploy, one
#  place to configure TLS, and one auth story. Flask is no longer a
#  dependency.
#
#  Point TradingView at:
#      https://<your-host>/webhooks/tradingview?secret=<TV_WEBHOOK_SECRET>
#
#  Start the API with:
#      uvicorn api.main:app --port 8000
#
#  This shim remains only so an existing deployment fails loudly with
#  instructions rather than silently serving a stale copy. It will be
#  deleted when Streamlit is retired in Phase 10.
# ─────────────────────────────────────────────

import sys

MESSAGE = """
tv_webhook.py has been replaced by the FastAPI application.

  Run instead:   uvicorn api.main:app --port 8000
  New endpoint:  POST /webhooks/tradingview?secret=<TV_WEBHOOK_SECRET>

Update the Webhook URL in your TradingView alert to point at the new path.
"""

if __name__ == "__main__":
    print(MESSAGE, file=sys.stderr)
    sys.exit(1)
