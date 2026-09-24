# ─────────────────────────────────────────────
#  theme.py — APEX design system
#
#  One set of components, two themes. Every colour is a CSS custom
#  property defined on :root, so light and dark are the same layout
#  with a different palette rather than two separate stylesheets.
#
#  Light is the default. Dark is a deliberate palette (deep charcoal,
#  lifted surfaces), not an inversion.
# ─────────────────────────────────────────────

FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', "
    "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)

# Numerals only — tabular figures stop prices jittering as they tick.
MONO_STACK = "'SF Mono', ui-monospace, 'JetBrains Mono', Menlo, monospace"

LIGHT = {
    "bg":        "#F5F5F7",
    "surface":   "#FFFFFF",
    "surface2":  "#FAFAFC",
    "border":    "rgba(0,0,0,0.07)",
    "border2":   "rgba(0,0,0,0.12)",
    "text":      "#1D1D1F",
    "text2":     "#6E6E73",
    "text3":     "#8E8E93",
    "up":        "#00A862",
    "upsoft":    "rgba(0,168,98,0.10)",
    "down":      "#E0334B",
    "downsoft":  "rgba(224,51,75,0.09)",
    "accent":    "#0A84FF",
    "accentsoft":"rgba(10,132,255,0.10)",
    "warn":      "#C77700",
    "shadow":    "0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.05)",
    "shadowlg":  "0 2px 6px rgba(0,0,0,0.05), 0 16px 40px rgba(0,0,0,0.08)",
    "chartgrid": "rgba(0,0,0,0.05)",
    "plotbg":    "#FFFFFF",
}

DARK = {
    "bg":        "#0C0D11",
    "surface":   "#17191F",
    "surface2":  "#1E212A",
    "border":    "rgba(255,255,255,0.08)",
    "border2":   "rgba(255,255,255,0.14)",
    "text":      "#F2F3F7",
    "text2":     "#9BA1AC",
    "text3":     "#6E7683",
    "up":        "#2FD48A",
    "upsoft":    "rgba(47,212,138,0.13)",
    "down":      "#FF5C6E",
    "downsoft":  "rgba(255,92,110,0.13)",
    "accent":    "#4A9EFF",
    "accentsoft":"rgba(74,158,255,0.14)",
    "warn":      "#FFB020",
    "shadow":    "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.35)",
    "shadowlg":  "0 2px 8px rgba(0,0,0,0.45), 0 20px 48px rgba(0,0,0,0.5)",
    "chartgrid": "rgba(255,255,255,0.06)",
    "plotbg":    "#17191F",
}


def palette(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def _vars(p: dict) -> str:
    return "\n".join(f"    --{k}: {v};" for k, v in p.items())


def css(theme: str = "light") -> str:
    """The whole stylesheet for the chosen theme."""
    p = palette(theme)
    return f"""
<style>
  :root {{
{_vars(p)}
    --r-sm: 10px;
    --r:    16px;
    --r-lg: 22px;
    --ease: cubic-bezier(0.32, 0.72, 0, 1);
  }}

  /* ── Foundation ───────────────────────────────────────────── */
  .stApp {{
    background: var(--bg);
    transition: background-color .35s var(--ease);
  }}
  html, body, [class*="st-"], .stMarkdown, p, div, span, label, input, button, li, td, th {{
    font-family: {FONT_STACK};
    color: var(--text);
    -webkit-font-smoothing: antialiased;
  }}
  /* Material icons are ligature fonts — never override their family. */
  [data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {{
    font-family: 'Material Symbols Rounded' !important;
  }}

  .block-container {{
    padding-top: 1.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 1240px;
  }}

  h1, h2, h3, h4 {{ color: var(--text); letter-spacing: -0.021em; }}
  .stMarkdown h2 {{ font-size: 27px; font-weight: 640; margin: 6px 0 2px; }}
  .stMarkdown h3 {{ font-size: 18px; font-weight: 600; margin: 26px 0 10px; }}
  .stMarkdown p, .stMarkdown li {{ color: var(--text2); font-size: 15px; line-height: 1.55; }}
  hr {{ border-color: var(--border); margin: 30px 0; }}

  .num {{ font-family: {MONO_STACK}; font-variant-numeric: tabular-nums; }}
  .up   {{ color: var(--up); }}
  .down {{ color: var(--down); }}
  .muted {{ color: var(--text2); }}

  /* ── Section heading ──────────────────────────────────────── */
  .sec {{
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 30px 0 14px;
  }}
  .sec-title {{ font-size: 20px; font-weight: 640; letter-spacing: -0.02em; }}
  .sec-sub   {{ font-size: 13px; color: var(--text3); }}

  /* ── Cards ────────────────────────────────────────────────── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r);
    box-shadow: var(--shadow);
    padding: 20px 22px;
    transition: box-shadow .3s var(--ease), transform .3s var(--ease),
                border-color .3s var(--ease);
  }}
  .card:hover {{ box-shadow: var(--shadowlg); transform: translateY(-2px); }}

  /* ── Hero (portfolio value) ───────────────────────────────── */
  .hero {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--shadow);
    padding: 28px 30px;
    margin-bottom: 8px;
  }}
  .hero-label {{
    font-size: 13px; color: var(--text2); font-weight: 500;
    letter-spacing: -0.01em; margin-bottom: 8px;
  }}
  .hero-value {{
    font-size: 44px; font-weight: 660; letter-spacing: -0.032em;
    font-variant-numeric: tabular-nums; line-height: 1.05;
    animation: rise .5s var(--ease) both;
  }}
  .hero-delta {{
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 15px; font-weight: 560; margin-top: 10px;
    padding: 5px 12px; border-radius: 999px;
    font-variant-numeric: tabular-nums;
  }}
  .hero-delta.pos {{ color: var(--up);   background: var(--upsoft); }}
  .hero-delta.neg {{ color: var(--down); background: var(--downsoft); }}

  /* ── Stat row ─────────────────────────────────────────────── */
  .stats {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 6px 0 4px; }}
  .stat {{
    flex: 1 1 130px; background: var(--surface);
    border: 1px solid var(--border); border-radius: var(--r);
    padding: 15px 17px; box-shadow: var(--shadow);
    transition: transform .3s var(--ease), box-shadow .3s var(--ease);
  }}
  .stat:hover {{ transform: translateY(-2px); box-shadow: var(--shadowlg); }}
  .stat-label {{
    font-size: 11px; color: var(--text3); font-weight: 560;
    text-transform: uppercase; letter-spacing: .055em; margin-bottom: 7px;
  }}
  .stat-value {{
    font-size: 21px; font-weight: 640; letter-spacing: -0.022em;
    font-variant-numeric: tabular-nums;
  }}
  .stat-sub {{ font-size: 12px; color: var(--text2); margin-top: 4px; }}

  /* ── Watchlist rows ───────────────────────────────────────── */
  .wl-row {{
    display: flex; align-items: center; gap: 14px;
    padding: 13px 16px; border-radius: 14px;
    transition: background .2s var(--ease);
  }}
  .wl-row:hover {{ background: var(--surface2); }}
  .wl-logo {{
    width: 38px; height: 38px; border-radius: 50%; flex: none;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 680; letter-spacing: -0.02em;
    background: var(--accentsoft); color: var(--accent);
  }}
  .wl-name {{ flex: 1; min-width: 0; }}
  .wl-tkr  {{ font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }}
  .wl-co   {{
    font-size: 12.5px; color: var(--text2); margin-top: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .wl-right {{ text-align: right; flex: none; }}
  .wl-price {{ font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }}
  .wl-chg   {{ font-size: 12.5px; font-weight: 560; margin-top: 2px;
               font-variant-numeric: tabular-nums; }}
  .wl-sep {{ height: 1px; background: var(--border); margin: 0 16px; }}

  /* ── Pills / chips ────────────────────────────────────────── */
  .pill {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 11px; border-radius: 999px;
    font-size: 11.5px; font-weight: 560;
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text2);
  }}
  .pill.pos {{ background: var(--upsoft);   color: var(--up);   border-color: transparent; }}
  .pill.neg {{ background: var(--downsoft); color: var(--down); border-color: transparent; }}
  .pill.acc {{ background: var(--accentsoft); color: var(--accent); border-color: transparent; }}

  .dot {{ width: 7px; height: 7px; border-radius: 50%; flex: none; }}

  /* ── Streamlit widgets ────────────────────────────────────── */
  [data-testid="stMetric"] {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--r); padding: 16px 18px; box-shadow: var(--shadow);
    transition: transform .3s var(--ease), box-shadow .3s var(--ease);
  }}
  [data-testid="stMetric"]:hover {{ transform: translateY(-2px); box-shadow: var(--shadowlg); }}
  [data-testid="stMetricValue"] {{
    font-size: 23px !important; font-weight: 640 !important;
    letter-spacing: -0.022em; color: var(--text) !important;
    font-variant-numeric: tabular-nums;
  }}
  [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    color: var(--text3) !important; font-size: 11px !important;
    font-weight: 560 !important; text-transform: uppercase;
    letter-spacing: .05em;
    white-space: normal !important; overflow: visible !important;
    text-overflow: clip !important;
  }}

  .stButton > button {{
    background: var(--surface); color: var(--text);
    border: 1px solid var(--border2); border-radius: 999px;
    font-size: 14.5px; font-weight: 560; letter-spacing: -0.01em;
    padding: 10px 20px; box-shadow: var(--shadow);
    transition: transform .18s var(--ease), box-shadow .25s var(--ease),
                background .25s var(--ease);
  }}
  .stButton > button:hover {{ transform: translateY(-1px); box-shadow: var(--shadowlg); }}
  .stButton > button:active {{ transform: scale(0.975); box-shadow: var(--shadow); }}
  .stButton > button[kind="primary"],
  .stFormSubmitButton > button {{
    background: var(--up); color: #fff; border-color: transparent;
  }}
  .stButton > button[kind="primary"]:hover,
  .stFormSubmitButton > button:hover {{ filter: brightness(1.05); }}

  [data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 2px; background: transparent;
    border-bottom: 1px solid var(--border); padding: 0;
  }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent; border: none; border-radius: 10px 10px 0 0;
    padding: 11px 15px; font-size: 14.5px; font-weight: 520;
    color: var(--text2); transition: color .2s var(--ease), background .2s var(--ease);
  }}
  [data-testid="stTabs"] [data-baseweb="tab"]:hover {{ color: var(--text); }}
  [data-testid="stTabs"] [aria-selected="true"] {{
    color: var(--text) !important; font-weight: 600;
  }}
  [data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background: var(--up); height: 2px; }}

  [data-baseweb="select"] > div, .stTextInput input, .stNumberInput input,
  .stTextArea textarea, .stDateInput input {{
    background: var(--surface) !important;
    border: 1px solid var(--border2) !important;
    border-radius: 12px !important;
    color: var(--text) !important;
    font-size: 14.5px !important;
    transition: border-color .2s var(--ease), box-shadow .2s var(--ease);
  }}
  [data-baseweb="select"] > div:focus-within, .stTextInput input:focus,
  .stNumberInput input:focus, .stTextArea textarea:focus {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3.5px var(--accentsoft) !important;
  }}
  [data-baseweb="popover"] {{ border-radius: 14px !important; }}
  [data-baseweb="popover"] li {{ font-size: 14px; }}
  [data-baseweb="popover"] li:hover {{ background: var(--accentsoft) !important; }}
  label, .stSelectbox label, .stTextInput label {{
    color: var(--text2) !important; font-size: 13.5px !important; font-weight: 520 !important;
  }}

  [data-testid="stSidebar"] {{
    background: var(--surface);
    border-right: 1px solid var(--border);
  }}
  [data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem !important; }}

  [data-testid="stDataFrame"] {{
    border: 1px solid var(--border); border-radius: var(--r);
    overflow: hidden; box-shadow: var(--shadow);
  }}
  [data-testid="stExpander"] {{
    border: 1px solid var(--border) !important; border-radius: 14px !important;
    background: var(--surface); box-shadow: var(--shadow);
  }}
  [data-testid="stExpander"] summary {{ font-size: 14.5px; font-weight: 540; }}
  [data-testid="stAlert"] {{
    border-radius: 14px; border: 1px solid var(--border);
    background: var(--surface2); box-shadow: var(--shadow);
  }}
  [data-testid="stAlert"] * {{ color: var(--text2); }}

  /* Branding hidden — but never the header itself, which holds the
     sidebar toggle. Hiding it strands the user with no way back. */
  footer {{ visibility: hidden; }}
  [data-testid="stDecoration"] {{ display: none; }}
  [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {{ display: none !important; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  [data-testid="stExpandSidebarButton"] span,
  [data-testid="stSidebarCollapseButton"] span {{ color: var(--text2) !important; }}

  /* ── Motion ───────────────────────────────────────────────── */
  @keyframes rise {{
    from {{ opacity: 0; transform: translateY(7px); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  @keyframes fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  .block-container > div {{ animation: fade .4s var(--ease) both; }}
  .rise {{ animation: rise .45s var(--ease) both; }}

  @media (prefers-reduced-motion: reduce) {{
    *, .card, .stat, .stButton > button {{
      animation: none !important; transition: none !important;
    }}
  }}

  /* ── Responsive ───────────────────────────────────────────── */
  @media (max-width: 640px) {{
    .block-container {{ padding-left: 1rem !important; padding-right: 1rem !important; }}
    .hero {{ padding: 22px 20px; }}
    .hero-value {{ font-size: 34px; }}
    .stat {{ flex: 1 1 calc(50% - 10px); }}
    .stMarkdown h2 {{ font-size: 23px; }}
    [data-testid="stTabs"] [data-baseweb="tab"] {{ padding: 10px 11px; font-size: 13.5px; }}
  }}
</style>
"""


def plotly_layout(theme: str = "light") -> dict:
    """Chart styling that matches the active theme."""
    p = palette(theme)
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=p["plotbg"],
        font=dict(color=p["text2"], family=FONT_STACK.split(",")[0].strip(), size=12),
        margin=dict(l=8, r=8, t=18, b=8),
        xaxis=dict(gridcolor=p["chartgrid"], zeroline=False, showline=False,
                   tickfont=dict(color=p["text3"], size=11)),
        yaxis=dict(gridcolor=p["chartgrid"], zeroline=False, showline=False,
                   tickfont=dict(color=p["text3"], size=11)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11, color=p["text2"])),
        hoverlabel=dict(bgcolor=p["surface"], font=dict(color=p["text"], size=12),
                        bordercolor=p["border2"]),
        transition=dict(duration=380, easing="cubic-in-out"),
    )
