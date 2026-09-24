"""
TradingView alert webhooks.

This replaces tv_webhook.py, which was a whole second Flask service running
on port 5001 to serve one endpoint. Folding it in removes Flask from the
dependency list and means one process to deploy and secure instead of two.
"""

import hmac

from fastapi import APIRouter, HTTPException, Query, Request, status

from api.deps import CurrentUser
from api.serialization import to_jsonable
from config import TV_WEBHOOK_SECRET

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/tradingview")
async def tradingview_webhook(request: Request, secret: str | None = Query(None)):
    """
    Receive a TradingView alert.

    TradingView sends the alert message body verbatim: JSON if the alert was
    written as JSON, otherwise plain text. Both are accepted.
    """
    raw = await request.body()
    try:
        import json
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {"message": str(payload)}
    except Exception:
        payload = {"message": raw.decode("utf-8", "replace").strip()}

    if TV_WEBHOOK_SECRET:
        provided = secret or payload.pop("secret", None)
        # Constant-time compare: a plain == leaks the secret's prefix through
        # response timing to anyone who can post here repeatedly.
        if not provided or not hmac.compare_digest(str(provided), TV_WEBHOOK_SECRET):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid secret")
    # With no secret configured the endpoint is open. That is the operator's
    # choice, but it must be a loud one.

    from tradingview import save_tv_alert

    save_tv_alert(payload)

    symbol = payload.get("symbol", "?")
    event = payload.get("event") or payload.get("message", "TradingView alert")
    try:
        from alerts import send_email_alert
        send_email_alert(
            f"TradingView Alert: {symbol} — {event}",
            "\n".join(f"{k}: {v}" for k, v in payload.items()),
        )
    except Exception:
        pass  # a failed email must not fail the webhook

    return {"status": "ok"}


@router.get("/alerts")
def list_alerts(user: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    from tradingview import load_tv_alerts

    return to_jsonable(load_tv_alerts(limit))


@router.delete("/alerts", status_code=status.HTTP_204_NO_CONTENT)
def clear_alerts(user: CurrentUser):
    from tradingview import clear_tv_alerts

    clear_tv_alerts()
