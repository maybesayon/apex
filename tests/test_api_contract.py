"""
Contract tests: the HTTP layer must not change any number.

This is the safety net for the migration. Each test calls the analysis
function directly and then over HTTP, and asserts the results are equal.
If the API ever reshapes, rounds or drops a value, these fail.

They run offline against the same frozen fixtures as the rest of the suite.
"""

import pytest
from fastapi.testclient import TestClient

from conftest import assert_golden
from api.serialization import to_jsonable


@pytest.fixture
def client(temp_db, offline):
    from api.main import app
    from api import security

    security._tokens.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """A signed-in client, with the token applied to every request."""
    r = client.post("/auth/register",
                    json={"username": "contract", "password": "contract-pass-1"})
    assert r.status_code == 201, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client


# ── The core contract: HTTP output == direct call ─────────────────────────────

def test_analysis_matches_direct_call(auth_client, offline):
    from indicators import calculate_all, get_signal_summary

    direct = get_signal_summary(calculate_all(offline("AAPL")))
    body = auth_client.get("/stocks/AAPL/analysis").json()

    assert body["overall_score"] == direct["overall_score"]
    assert to_jsonable(direct["signals"]) == body["signals"]


def test_opportunity_matches_direct_call(auth_client):
    from scanner import score_opportunity

    direct = to_jsonable(score_opportunity("AAPL"))
    body = auth_client.get("/stocks/AAPL/opportunity").json()
    assert body == direct


def test_forecast_matches_direct_call(auth_client):
    from ml_predictions import predict_direction

    direct = to_jsonable(predict_direction("AAPL"))
    body = auth_client.get("/stocks/AAPL/forecast").json()
    # The API adds two derived fields and changes nothing else.
    for key, value in direct.items():
        assert body[key] == value, f"{key} drifted: {body[key]} != {value}"
    assert set(body) - set(direct) == {"has_skill", "edge_vs_baseline"}


def test_backtest_matches_direct_call(auth_client):
    from backtest import backtest_momentum_strategy

    direct = to_jsonable(backtest_momentum_strategy("AAPL", 1000))
    body = auth_client.post("/backtest", json={"symbol": "AAPL", "capital": 1000}).json()
    assert body == direct


def test_history_matches_direct_call(auth_client, offline):
    df = offline("AAPL")
    body = auth_client.get("/stocks/AAPL/history?period=2y").json()
    assert len(body["bars"]) == len(df)
    assert body["bars"][0]["close"] == pytest.approx(float(df["close"].iloc[0]))
    assert body["bars"][-1]["close"] == pytest.approx(float(df["close"].iloc[-1]))


def test_search_matches_direct_call(auth_client):
    from symbols import search_symbols

    direct = search_symbols("apple", 5)
    body = auth_client.get("/search?q=apple&limit=5").json()
    assert [(r["symbol"], r["name"]) for r in body] == direct


# ── Golden snapshots over HTTP ────────────────────────────────────────────────

def test_analysis_response_golden(auth_client):
    body = auth_client.get("/stocks/AAPL/analysis").json()
    assert_golden("api_analysis_aapl",
                  {k: body[k] for k in ("overall_score", "signals", "levels", "indicators")})


def test_opportunity_response_golden(auth_client):
    body = auth_client.get("/stocks/AAPL/opportunity").json()
    assert_golden("api_opportunity_aapl",
                  {k: body[k] for k in ("score", "confidence", "entry", "target",
                                        "stop", "risk_reward", "est_move")})


# ── Auth and access control ───────────────────────────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("get", "/portfolio"), ("get", "/watchlist"), ("get", "/journal"),
    ("get", "/journal/stats"), ("get", "/settings"), ("get", "/alerts"),
    ("get", "/auth/me"),
])
def test_user_routes_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_invalid_token_rejected(client):
    r = client.get("/portfolio", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_login_returns_token(client):
    client.post("/auth/register", json={"username": "loginuser", "password": "login-pass-1"})
    r = client.post("/auth/login", json={"username": "loginuser", "password": "login-pass-1"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_wrong_password_rejected(client):
    client.post("/auth/register", json={"username": "pw", "password": "correct-pass-1"})
    r = client.post("/auth/login", json={"username": "pw", "password": "wrong-pass-1"})
    assert r.status_code == 401


def test_login_error_does_not_reveal_whether_user_exists(client):
    client.post("/auth/register", json={"username": "known", "password": "known-pass-1"})
    a = client.post("/auth/login", json={"username": "known", "password": "bad-pass-11"})
    b = client.post("/auth/login", json={"username": "ghost", "password": "bad-pass-11"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_duplicate_registration_conflicts(client):
    client.post("/auth/register", json={"username": "dup", "password": "dup-pass-111"})
    r = client.post("/auth/register", json={"username": "dup", "password": "dup-pass-111"})
    assert r.status_code == 409


def test_weak_password_rejected(client):
    r = client.post("/auth/register", json={"username": "weak", "password": "short"})
    assert r.status_code == 422        # caught by the Pydantic min_length


def test_logout_invalidates_token(auth_client):
    assert auth_client.get("/auth/me").status_code == 200
    assert auth_client.post("/auth/logout").status_code == 204
    assert auth_client.get("/auth/me").status_code == 401


# ── Per-user isolation over HTTP ──────────────────────────────────────────────

def test_accounts_cannot_see_each_other(client):
    tokens = {}
    for name in ("iso_a", "iso_b"):
        r = client.post("/auth/register", json={"username": name, "password": f"{name}-pass-1"})
        tokens[name] = {"Authorization": f"Bearer {r.json()['access_token']}"}

    client.put("/portfolio/positions",
               json={"symbol": "AAPL", "shares": 10, "avg_cost": 150.0},
               headers=tokens["iso_a"])

    b = client.get("/portfolio", headers=tokens["iso_b"]).json()
    assert b["positions"] == [], "one account can see another's holdings"


def test_no_route_accepts_a_user_id(auth_client):
    """
    Structural guarantee: user identity comes only from the token, so there
    is no parameter an attacker could tamper with to read another account.
    """
    from api.main import app

    for path in app.openapi()["paths"]:
        assert "{user_id}" not in path and "{uid}" not in path, path


# ── CRUD round-trips ──────────────────────────────────────────────────────────

def test_portfolio_round_trip(auth_client):
    auth_client.put("/portfolio/positions",
                    json={"symbol": "AAPL", "shares": 5, "avg_cost": 100.0})
    body = auth_client.get("/portfolio").json()
    assert body["positions"][0]["symbol"] == "AAPL"
    assert body["total_cost"] == 500.0

    auth_client.delete("/portfolio/positions/AAPL")
    assert auth_client.get("/portfolio").json()["positions"] == []


def test_watchlist_round_trip(auth_client):
    before = {i["symbol"] for i in auth_client.get("/watchlist").json()}
    auth_client.post("/watchlist", json={"symbol": "apple"})   # by name
    after = {i["symbol"] for i in auth_client.get("/watchlist").json()}
    assert "AAPL" in after

    auth_client.delete("/watchlist/AAPL")
    assert "AAPL" not in {i["symbol"] for i in auth_client.get("/watchlist").json()}


def test_journal_round_trip_and_stats(auth_client):
    assert auth_client.get("/journal/stats").json()["win_rate"] is None

    auth_client.post("/journal", json={"date": "2026-01-01", "symbol": "NVDA",
                                       "strategy": "Momentum", "entry": 100,
                                       "exit": 110, "shares": 2, "note": "ok"})
    stats = auth_client.get("/journal/stats").json()
    assert stats["trades"] == 1 and stats["wins"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_pnl"] == 20.0


def test_settings_round_trip(auth_client):
    assert auth_client.get("/settings").json()["theme"] == "light"
    auth_client.put("/settings", json={"theme": "dark"})
    assert auth_client.get("/settings").json()["theme"] == "dark"


# ── Errors ────────────────────────────────────────────────────────────────────

def test_unknown_symbol_is_404(auth_client):
    assert auth_client.get("/stocks/ZZZZQQ/analysis").status_code == 404


def test_invalid_period_is_400(auth_client):
    assert auth_client.get("/stocks/AAPL/history?period=nonsense").status_code == 400


def test_company_name_resolves_in_path(auth_client):
    body = auth_client.get("/stocks/apple/analysis").json()
    assert body["symbol"] == "AAPL"


def test_zero_trade_backtest_is_422_with_reason(auth_client):
    r = auth_client.post("/backtest", json={"symbol": "AAPL", "capital": 1000,
                                            "rsi_entry": 5})
    assert r.status_code == 422
    assert "MACD" in r.json()["detail"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


# ── Serialization safety ──────────────────────────────────────────────────────

def test_responses_contain_no_nan_or_infinity(auth_client):
    """
    NaN and Infinity are not valid JSON — a browser's JSON.parse rejects
    them. Indicators legitimately produce both, so they must become null.
    """
    for path in ("/stocks/AAPL/analysis", "/stocks/AAPL/opportunity",
                 "/stocks/AAPL/forecast"):
        raw = auth_client.get(path).text
        assert "NaN" not in raw, f"{path} emitted NaN"
        assert "Infinity" not in raw, f"{path} emitted Infinity"


def test_openapi_schema_is_valid(client):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "APEX API"
    assert len(spec["paths"]) >= 25
