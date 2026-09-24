"""
Accounts: password handling and per-user isolation.

Isolation is the security property that replaced a hardcoded portfolio
shown identically to every visitor. It must not regress.
"""

import pytest


@pytest.fixture
def users(temp_db):
    import auth
    a = auth.register("alice", "alice@example.com", "alice-password-1")
    b = auth.register("bob", "bob@example.com", "alice-password-1")  # same password
    return temp_db, auth, a, b


# ── Passwords ─────────────────────────────────────────────────────────────────

def test_password_is_never_stored_in_plaintext(users):
    db, _, _, _ = users
    row = db.get_user("alice")
    assert "alice-password-1" not in str(dict(row))
    assert len(row["password_hash"]) == 128        # scrypt, 64-byte digest
    assert len(row["salt"]) == 32                  # 16 random bytes, hex


def test_identical_passwords_get_different_hashes(users):
    db, _, _, _ = users
    a, b = db.get_user("alice"), db.get_user("bob")
    assert a["salt"] != b["salt"]
    assert a["password_hash"] != b["password_hash"]


def test_correct_password_authenticates(users):
    _, auth, _, _ = users
    assert auth.authenticate("alice", "alice-password-1")


@pytest.mark.parametrize("bad", ["wrong", "", "alice-password-2", "ALICE-PASSWORD-1"])
def test_wrong_password_rejected(users, bad):
    _, auth, _, _ = users
    assert auth.authenticate("alice", bad) is None


def test_unknown_user_rejected(users):
    _, auth, _, _ = users
    assert auth.authenticate("nobody", "anything") is None


def test_username_is_case_insensitive(users):
    _, auth, _, _ = users
    assert auth.authenticate("ALICE", "alice-password-1")


def test_duplicate_username_blocked(users):
    _, auth, _, _ = users
    with pytest.raises(Exception):
        auth.register("alice", "other@example.com", "another-password")


@pytest.mark.parametrize("user,email,pw,confirm", [
    ("ab", "a@b.co", "longenough1", "longenough1"),          # username too short
    ("has space", "a@b.co", "longenough1", "longenough1"),   # illegal character
    ("valid", "a@b.co", "short", "short"),                   # password too short
    ("valid", "a@b.co", "longenough1", "different11"),       # mismatch
    ("valid", "not-an-email", "longenough1", "longenough1"), # bad email
])
def test_signup_validation_rejects(temp_db, user, email, pw, confirm):
    import auth
    assert auth.validate_signup(user, email, pw, confirm) is not None


def test_signup_validation_accepts_good_input(temp_db):
    import auth
    assert auth.validate_signup("new.user-1", "a@b.co", "longenough1", "longenough1") is None


# ── Isolation ─────────────────────────────────────────────────────────────────

def test_positions_are_per_user(users):
    db, _, a, b = users
    db.upsert_position(a, "AAPL", 10, 150.0)
    db.upsert_position(b, "TSLA", 3, 200.0)
    assert set(db.get_positions(a)) == {"AAPL"}
    assert set(db.get_positions(b)) == {"TSLA"}


def test_watchlists_are_per_user(users):
    db, _, a, b = users
    db.add_to_watchlist(a, "GSAT")
    assert "GSAT" in db.get_watchlist(a)
    assert "GSAT" not in db.get_watchlist(b)


def test_journals_are_per_user(users):
    db, _, a, b = users
    db.add_journal_entry(a, {"date": "2026-01-01", "symbol": "NVDA", "strategy": "M",
                             "entry": 10, "exit": 12, "shares": 1,
                             "pnl": 2, "pnl_pct": 20, "note": ""})
    assert len(db.get_journal(a)) == 1
    assert len(db.get_journal(b)) == 0


def test_themes_are_per_user(users):
    db, _, a, b = users
    db.set_theme(a, "dark")
    assert db.get_theme(a) == "dark"
    assert db.get_theme(b) == "light"


# ── Derived statistics ────────────────────────────────────────────────────────

def test_win_rate_is_computed_not_hardcoded(users):
    """Regression: a literal '68% - 17 of 25 trades' was shown to everyone."""
    db, _, a, _ = users
    for pnl in (100, 50, -30):
        db.add_journal_entry(a, {"date": "2026-01-01", "symbol": "X", "strategy": "M",
                                 "entry": 10, "exit": 11, "shares": 1,
                                 "pnl": pnl, "pnl_pct": 1, "note": ""})
    s = db.journal_stats(a)
    assert s["trades"] == 3 and s["wins"] == 2 and s["losses"] == 1
    assert s["win_rate"] == pytest.approx(66.7, abs=0.1)
    assert s["total_pnl"] == pytest.approx(120.0)


def test_win_rate_is_none_without_trades(users):
    db, _, _, b = users
    s = db.journal_stats(b)
    assert s["win_rate"] is None and s["trades"] == 0


def test_no_personal_data_left_in_config():
    """Regression: one person's holdings were module constants in config.py."""
    import config
    assert not hasattr(config, "PORTFOLIO")
    assert not hasattr(config, "WATCHLIST")


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_position_upsert_overwrites(users):
    db, _, a, _ = users
    db.upsert_position(a, "AAPL", 10, 150.0)
    db.upsert_position(a, "AAPL", 12, 155.0)
    assert db.get_positions(a)["AAPL"] == {"shares": 12.0, "avg_cost": 155.0}


def test_position_delete(users):
    db, _, a, _ = users
    db.upsert_position(a, "AAPL", 1, 1.0)
    db.delete_position(a, "AAPL")
    assert "AAPL" not in db.get_positions(a)


def test_watchlist_add_is_idempotent(users):
    db, _, a, _ = users
    before = len(db.get_watchlist(a))
    db.add_to_watchlist(a, "ZZZ")
    db.add_to_watchlist(a, "ZZZ")
    assert len(db.get_watchlist(a)) == before + 1


def test_new_user_gets_default_watchlist(users):
    db, _, a, _ = users
    assert db.get_watchlist(a), "new accounts should not start empty"
