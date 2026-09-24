"""
Streamlit render smoke tests.

These are the only tests that will be deleted at Phase 10 when Streamlit is
retired. Until then they guard the auth gate and both themes.
"""

import pytest

APP = "app.py"


def _app(theme="light", user=None, username=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=300)
    if user is not None:
        at.session_state["user_id"] = user
        at.session_state["username"] = username or "tester"
    at.session_state["theme"] = theme
    return at


@pytest.fixture
def account(temp_db):
    import auth
    uid = auth.register("render", "r@example.com", "render-password-1")
    temp_db.upsert_position(uid, "AAPL", 10, 150.0)
    return uid


def test_signed_out_shows_only_the_login_gate(temp_db):
    at = _app()
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Sign in" in labels
    assert len(at.tabs) == 2, "app content leaked past the auth gate"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_renders_in_both_themes(offline, account, theme):
    at = _app(theme=theme, user=account)
    at.run()
    assert not at.exception, str(at.exception)
    assert len(at.tabs) == 7


def test_all_symbol_pickers_are_searchable(offline, account):
    """Every symbol input searches the full index, not a short hardcoded list."""
    at = _app(user=account)
    at.run()
    pickers = [s for s in at.selectbox if s.key and s.key.endswith("_sym")]
    assert len(pickers) >= 4, f"expected the analysis/backtest/forecast/chart pickers, got {len(pickers)}"
    for p in pickers:
        assert len(p.options) > 480, f"{p.key} is not searching the full index"


def test_theme_choice_changes_rendered_css(offline, account):
    import theme as design
    light, dark = design.css("light"), design.css("dark")
    assert light != dark
    assert design.LIGHT["bg"] in light
    assert design.DARK["bg"] in dark


def test_no_hardcoded_win_rate_in_source():
    """
    Regression: a literal '68%' / '17 of 25 trades' tile was rendered to
    every user. Comment lines are stripped first — the fix is documented in
    a comment that necessarily quotes the old string.
    """
    code = "\n".join(line for line in open(APP).read().splitlines()
                     if not line.lstrip().startswith("#"))
    assert '"68%"' not in code
    assert "17 of 25" not in code
