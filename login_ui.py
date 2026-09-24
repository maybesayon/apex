# ─────────────────────────────────────────────
#  login_ui.py — Sign-in / sign-up screen
# ─────────────────────────────────────────────

import streamlit as st

import auth
import db


def _brand():
    st.markdown("""
    <div style="text-align:center;margin:6vh 0 26px">
      <div style="font-size:40px;font-weight:680;letter-spacing:-0.035em">APEX</div>
      <div style="font-size:15px;color:var(--text2);margin-top:6px">
        Markets, measured honestly.
      </div>
    </div>
    """, unsafe_allow_html=True)


def _sign_in_tab():
    with st.form("sign_in", border=False):
        username = st.text_input("Username", key="li_user", autocomplete="username")
        password = st.text_input("Password", type="password", key="li_pass",
                                 autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")

    if submitted:
        user = auth.authenticate(username.strip(), password)
        if user:
            st.session_state.user_id  = user["id"]
            st.session_state.username = user["username"]
            st.session_state.theme    = db.get_theme(user["id"])
            st.rerun()
        else:
            # Deliberately vague: never reveal whether the username exists.
            st.error("Incorrect username or password.")


def _sign_up_tab():
    with st.form("sign_up", border=False):
        username = st.text_input("Username", key="su_user",
                                 help="3–32 characters: letters, numbers, dot, dash, underscore.")
        email    = st.text_input("Email (optional)", key="su_email")
        password = st.text_input("Password", type="password", key="su_pass",
                                 help=f"At least {auth.MIN_PASSWORD_LEN} characters.",
                                 autocomplete="new-password")
        confirm  = st.text_input("Confirm password", type="password", key="su_confirm",
                                 autocomplete="new-password")
        submitted = st.form_submit_button("Create account", use_container_width=True,
                                          type="primary")

    if submitted:
        username = username.strip()
        error = auth.validate_signup(username, email.strip(), password, confirm)
        if error:
            st.error(error)
            return
        try:
            user_id = auth.register(username, email.strip(), password)
        except Exception:
            st.error("Could not create that account. The username may already be taken.")
            return
        st.session_state.user_id  = user_id
        st.session_state.username = username
        st.session_state.theme    = "light"
        st.rerun()


def render_login() -> None:
    """Full-page gate. Returns only by rerunning once signed in."""
    _brand()
    left, mid, right = st.columns([1, 1.25, 1])
    with mid:
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in: _sign_in_tab()
        with tab_up: _sign_up_tab()

        st.markdown("""
        <div style="text-align:center;margin-top:22px;font-size:12.5px;color:var(--text3);
                    line-height:1.6">
          APEX is an analysis tool. It does not place trades and is not financial advice.
        </div>
        """, unsafe_allow_html=True)
