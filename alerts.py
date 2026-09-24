# ─────────────────────────────────────────────
#  alerts.py — Email Alert System
# ─────────────────────────────────────────────

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import (
    ALERT_EMAIL_FROM, ALERT_EMAIL_TO,
    ALERT_EMAIL_PASS, SMTP_HOST, SMTP_PORT,
    SCAN_ALERT_THRESHOLD
)


def send_email_alert(subject: str, body: str) -> bool:
    """
    Send an email alert. Returns True if successful.
    Requires Gmail credentials in config.py.
    """
    if not ALERT_EMAIL_FROM or not ALERT_EMAIL_PASS:
        print("Email alerts not configured. Add credentials to config.py")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = ALERT_EMAIL_FROM
        msg["To"]      = ALERT_EMAIL_TO

        html_body = f"""
        <html><body style="font-family:monospace;background:#070a0f;color:#e8f0fe;padding:20px">
        <h2 style="color:#00ff88">⚡ APEX Trading Alert</h2>
        <pre style="background:#111820;padding:16px;border-radius:8px;border:1px solid #1e2d3d">
{body}
        </pre>
        <p style="color:#7a9ab8;font-size:12px">
        This is an automated alert from APEX Trading Intelligence.<br>
        Not financial advice. Always do your own research.
        </p>
        </body></html>
        """

        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASS)
            server.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO, msg.as_string())

        print(f"Alert sent: {subject}")
        return True

    except Exception as e:
        print(f"Email alert failed: {e}")
        return False


def send_opportunity_alert(opportunity: dict) -> bool:
    """Send alert for a high-confidence opportunity."""
    sym   = opportunity["symbol"]
    score = opportunity["score"]
    price = opportunity["price"]
    move  = opportunity["est_move"]

    subject = f"🔥 APEX Alert: {sym} — {score}/100 Confidence"
    body = f"""
HIGH CONFIDENCE OPPORTUNITY DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Symbol:     {sym} — {opportunity.get('name', '')}
Score:      {score}/100 ({opportunity['confidence']})
Price:      ${price}
Est. Move:  {move}
Horizon:    {opportunity.get('horizon', '7-14 days')}

EXIT LEVELS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry:      ${opportunity['entry']}
Target:     ${opportunity['target']}
Stop Loss:  ${opportunity['stop']}
Risk/Reward: {opportunity['risk_reward']}:1

SIGNALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(f"• {tag}" for tag in opportunity.get('tags', []))}

Detected at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    return send_email_alert(subject, body)


def send_price_alert(symbol: str, price: float, trigger: str, note: str = "") -> bool:
    """Send alert when a stock hits a target or stop loss price."""
    subject = f"⚠️ APEX Price Alert: {symbol} hit {trigger}"
    body = f"""
PRICE ALERT TRIGGERED
━━━━━━━━━━━━━━━━━━━━━
Symbol:   {symbol}
Trigger:  {trigger}
Price:    ${price}
Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{f'Note: {note}' if note else ''}

Review your position immediately.
    """
    return send_email_alert(subject, body)


def send_daily_briefing(opportunities: list, portfolio_pnl: float) -> bool:
    """Send daily morning briefing with top picks and portfolio status."""
    top = opportunities[:3] if opportunities else []

    picks_text = ""
    for i, opp in enumerate(top, 1):
        picks_text += f"""
{i}. {opp['symbol']} — {opp['score']}/100 · {opp['confidence']}
   Price: ${opp['price']} | Est. Move: {opp['est_move']}
   Entry: ${opp['entry']} | Target: ${opp['target']} | Stop: ${opp['stop']}
"""

    subject = f"📊 APEX Daily Briefing — {datetime.now().strftime('%b %d, %Y')}"
    body = f"""
APEX DAILY BRIEFING
{datetime.now().strftime('%A, %B %d, %Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PORTFOLIO P&L TODAY
Total: ${portfolio_pnl:+.2f}

TOP OPPORTUNITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{picks_text if picks_text else "No high-confidence picks today."}

Have a great trading day!
APEX Trading Intelligence
    """
    return send_email_alert(subject, body)
