"""
APEX API — the boundary between the Python analysis engine and any frontend.

Run it:
    uvicorn api.main:app --reload --port 8000

Docs at /docs, OpenAPI schema at /openapi.json. The Next.js client's
TypeScript types are generated from that schema.

This runs alongside the Streamlit app, which is untouched. Both import the
same analysis modules, so there is one implementation of every calculation.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
from api.routers import analysis_ops, auth, stocks, user_data, webhooks

API_VERSION = "0.1.0"

app = FastAPI(
    title="APEX API",
    version=API_VERSION,
    description=(
        "Stock analysis: technical indicators, opportunity scoring, strategy "
        "backtesting and walk-forward-validated price-direction forecasting.\n\n"
        "**This API never places trades.** It is an analysis tool, and nothing "
        "it returns is financial advice."
    ),
    openapi_tags=[
        {"name": "auth", "description": "Account creation and sign-in."},
        {"name": "stocks", "description": "Market data and per-symbol analysis."},
        {"name": "user", "description": "Portfolio, watchlist, journal, settings."},
        {"name": "analysis", "description": "Backtesting, scanning, assistant."},
        {"name": "webhooks", "description": "Inbound TradingView alerts."},
    ],
)

# Dev origins for the Next.js frontend. Tighten via APEX_CORS_ORIGINS in
# any deployment — a wildcard here would let any site call the API with a
# user's bearer token.
_origins = os.environ.get(
    "APEX_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stocks.router)
app.include_router(user_data.router)
app.include_router(analysis_ops.router)
app.include_router(webhooks.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/health", tags=["meta"])
def health():
    """
    Liveness plus the auth configuration, so a deployment serving cookies
    without Secure, or running on a generated dev key, is visible rather
    than silently insecure.
    """
    from api import security

    report = security.config_report()
    warnings = []
    if report["env"] in {"production", "prod"}:
        if not report["cookie_secure"]:
            warnings.append("cookies are not Secure in production")
        if not report["secret_key_from_env"]:
            warnings.append("APEX_SECRET_KEY is not set from the environment")
    return {"status": "ok", "version": API_VERSION, "auth": report,
            "warnings": warnings}
